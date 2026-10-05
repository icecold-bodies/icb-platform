#!/usr/bin/env bash
# RT5 — Burt's two body rules as the CHILLER and FREEZER families' rule notes, on PROD, in the v1.60.2 window
# (RT5_RULING_1: the wording approved exactly; dry-run -> apply -> journal -> revert). Over v1.60.2 only (alembic
# 0052: trailer_groups.rule_note). The operator runs, on the VM, ONE step at a time and sends the CA the output
# folder name before the next:
#
#     sudo bash /tmp/icb-rt5-notes/rt5_notes.sh dryrun      read only: the two families, before -> after, and the
#                                                          bodies each note will show on
#     sudo bash /tmp/icb-rt5-notes/rt5_notes.sh apply
#     sudo bash /tmp/icb-rt5-notes/rt5_notes.sh show        read only: every family's note, exactly — the window's
#                                                          read-back after the apply, the admin edit and its set-back
#     sudo bash /tmp/icb-rt5-notes/rt5_notes.sh revert /var/backups/icb-rt5-2026-10/<journal>.json
#
# What each step touches on prod:
#   dryrun / show  ops/prod-rt5/rt5_notes.py inside a READ ONLY session — writes nothing
#   apply          the dry-run again (it must be exactly the reviewed plan: 2 to apply), a data-only pg_dump of
#                  trailer_groups, then the tool's apply: ONE transaction, every row re-read FOR UPDATE and re-checked
#                  before the commit; journal + backup + provenance kept in /var/backups/icb-rt5-2026-10/; a second
#                  dry-run must find nothing left to apply
#   revert         puts every journaled row back; the tool refuses if a row moved since
# Nothing under /opt/icb-platform changes; no service is touched; nothing is a deploy; no price, formula, BOM row,
# option, draft or quote document moves (the notes are trailer_groups.rule_note only). Staged by the CA's
# mkstage_notes.sh (committed bytes, LF); SHA256SUMS covers this script, expected.env and the tool.
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u

MODE=${1:-}; ARG=${2:-}
BASE=/tmp/icb-rt5-notes
KEEP=/var/backups/icb-rt5-2026-10
PY=/opt/icb-platform/.venv/bin/python
TS=$(date -u +%Y%m%dT%H%M%SZ)
USAGE="usage: sudo bash $0 dryrun | apply | show | revert <journal.json>"
case "$MODE" in
  dryrun|apply|show) [ -z "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
  revert) [ -n "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
  *) echo "$USAGE"; exit 1 ;;
esac
OUT=$BASE/out-$MODE-$TS

[ -e "$OUT" ] && { echo "STOP: $OUT already exists (two runs in one second?): run again"; exit 1; }
mkdir -p "$OUT" || { echo "STOP: cannot create $OUT"; exit 1; }
chmod 700 "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
stop() { echo; echo "######## STOP [$1]: $2"; echo "######## tell the CA: $OUT"; chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEAD EXPECT_ALEMBIC PLAN_TODO TOOL_SHA STAGED_FROM; do
  [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
done
TOOL="$BASE/rt5_notes.py"
[ "$(sha256sum "$TOOL" | cut -d' ' -f1)" = "$TOOL_SHA" ] || stop KIT "rt5_notes.py is not the reviewed bytes"
[ -r /etc/icb/backend.env ] || stop KIT "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
q() { PGOPTIONS='-c default_transaction_read_only=on' psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "$1" 2>&1; }
export PYTHONDONTWRITEBYTECODE=1

DBNAME=$(q "select current_database()") || stop DB "cannot reach the database: $DBNAME"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"
ALEMBIC=$(q "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC (the notes go over v1.60.2 only)"
# Under sudo git refuses the icb-owned repo as "dubious ownership" unless the path is trusted (read-only).
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD 2>/dev/null || echo '?')
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} mode=$MODE  $(date -Is)"
[ "$HEAD" = "$EXPECT_HEAD" ] || stop CODE "prod's code is ${HEAD:0:7}; the notes go only over the v1.60.2 release ${EXPECT_HEAD:0:7}"
$PY -c "import psycopg" || stop IMPORT "psycopg does not import in prod's venv"

plan_line() { grep -E '^[0-9]+ to apply, [0-9]+ already applied\.$' "$1" | tail -n1; }
# dry-run and show also run under a server-enforced read-only session (belt and braces: the tool sets its own)
RO='-c default_transaction_read_only=on'
dry() { PGOPTIONS="$RO" $PY "$TOOL" --target prod > "$1" 2>&1; }   # exit 2 = a guard refused (prod is not where the plan says)
show() { PGOPTIONS="$RO" $PY "$TOOL" --target prod --show; }

if [ "$MODE" = show ]; then
  say "every family's rule note (READ ONLY)"
  show > "$OUT/show.txt" 2>&1; rc=$?
  cat "$OUT/show.txt"
  [ $rc = 0 ] || stop SHOW "the read-back failed (exit $rc)"
  chmod -R a+rX "$OUT"; echo; echo "######## DONE (show) — tell the CA: $OUT"; exit 0
fi

if [ "$MODE" = dryrun ] || [ "$MODE" = apply ]; then
  say "dry-run (READ ONLY)"
  dry "$OUT/dryrun.txt"; rc=$?
  cat "$OUT/dryrun.txt"
  [ $rc = 0 ] || stop GUARD "the dry-run refused (exit $rc): a family is not where the plan says; nothing written"
  P=$(plan_line "$OUT/dryrun.txt")
  if [ "$P" = "0 to apply, $PLAN_TODO already applied." ]; then
    say "the notes are ALREADY on prod ($P) — nothing to do"; chmod -R a+rX "$OUT"
    echo; echo "######## DONE ($MODE: already applied) — tell the CA: $OUT"; exit 0
  fi
  [ "$P" = "$PLAN_TODO to apply, 0 already applied." ] || stop PLAN "the plan is '$P', the reviewed plan is '$PLAN_TODO to apply, 0 already applied.'"
  if [ "$MODE" = dryrun ]; then
    chmod -R a+rX "$OUT"; echo; echo "######## DONE (dryrun: $P) — tell the CA: $OUT"; exit 0
  fi

  mkdir -p "$KEEP" && chmod 700 "$KEEP" || stop BACKUP "cannot create $KEEP"
  BK="$KEEP/pre_apply_notes_$TS.sql.gz"
  say "pre-apply backup (data only): trailer_groups"
  pg_dump "$URL" --data-only -t icb_costings.trailer_groups | gzip > "$BK" || stop BACKUP "pg_dump failed — nothing applied"
  [ -s "$BK" ] && gzip -t "$BK" || stop BACKUP "$BK is empty or not gzip — nothing applied"
  echo "   ok   $BK $(stat -c %s "$BK") bytes sha256 $(sha256sum "$BK" | cut -d' ' -f1)"

  say "apply — one transaction"
  $PY "$TOOL" --target prod --apply --out-dir "$OUT" > "$OUT/apply.txt" 2>&1; rc=$?
  cat "$OUT/apply.txt"
  [ $rc = 0 ] || stop APPLY "apply refused or failed (exit $rc): the transaction rolled back; nothing changed"
  J=$(ls "$OUT"/rt5_notes_journal_prod_*.json 2>/dev/null | head -n1)
  [ -n "$J" ] || stop JOURNAL "applied but no journal in $OUT — tell the CA NOW"
  JN="journal_notes_$(basename "$J")"
  cp "$J" "$KEEP/$JN" || stop JOURNAL "journal not copied to $KEEP (it is still in $OUT) — tell the CA"
  { echo "journal      $JN (the tool's own file, unchanged)"
    echo "tool         rt5_notes.py sha256 $TOOL_SHA"
    echo "staged_from  $STAGED_FROM"
    echo "prod_code    $HEAD"
    echo "alembic      $ALEMBIC"
    echo "backup       $(basename "$BK")"
    echo "run_folder   $OUT"
  } > "$KEEP/${JN%.json}.provenance.txt" || stop JOURNAL "provenance note not written — tell the CA"
  echo "   ok   journal $KEEP/$JN  sha256 $(sha256sum "$KEEP/$JN" | cut -d' ' -f1)"

  say "second dry-run (must find nothing left to apply)"
  dry "$OUT/after.txt"; rc=$?
  cat "$OUT/after.txt"
  [ $rc = 0 ] && [ "$(plan_line "$OUT/after.txt")" = "0 to apply, $PLAN_TODO already applied." ] \
    || stop AFTER "the second dry-run is not '0 to apply, $PLAN_TODO already applied.' — tell the CA"
  say "the read-back (every family's note, exactly)"
  show | tee "$OUT/show.txt"
  chmod -R a+rX "$OUT"
  echo; echo "######## DONE (apply) — tell the CA: $OUT  (undo: sudo bash $0 revert $KEEP/$JN)"; exit 0
fi

# revert
[ -f "$ARG" ] || stop REVERT "no journal at $ARG"
say "revert from $ARG"
$PY "$TOOL" --target prod --revert "$ARG" --out-dir "$OUT" > "$OUT/revert.txt" 2>&1; rc=$?
cat "$OUT/revert.txt"
[ $rc = 0 ] || stop REVERT "revert refused or failed (exit $rc): nothing changed"
show | tee "$OUT/show.txt"
chmod -R a+rX "$OUT"
echo; echo "######## DONE (revert) — tell the CA: $OUT"
