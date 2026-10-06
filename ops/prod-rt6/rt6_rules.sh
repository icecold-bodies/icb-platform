#!/usr/bin/env bash
# RT6 — Burt's two insulation rules as the CHILLER and FREEZER families' machine-readable rule, on PROD, in the
# v1.61.0 window (dry-run -> apply -> journal -> revert). Over v1.61.0 only (alembic 0053:
# trailer_groups.insulation_rule). The operator runs ONE step at a time, on the VM (or through run_window.ps1):
#
#     sudo bash /tmp/icb-rt6-rules/rt6_rules.sh dryrun      read only: the two families, before -> after, and the
#                                                          bodies each rule is enforced on (expected: 2 to apply)
#     sudo bash /tmp/icb-rt6-rules/rt6_rules.sh apply
#     sudo bash /tmp/icb-rt6-rules/rt6_rules.sh show        read only: every family's rule exactly; per ruled body the
#                                                          greyed masters; "live breaching costings: N" (quote
#                                                          numbers only) and the soft-deleted count
#     sudo bash /tmp/icb-rt6-rules/rt6_rules.sh revert /var/backups/icb-rt6-2026-10/<journal>.json
#
# Its FIRST output line names the machine, the database (name and host) and the git HEAD, and it refuses unless they
# are prod's (ops/lib/icb_where.sh — RT6 safe pastes).
#
# What each step touches on prod:
#   dryrun / show  ops/prod-rt6/rt6_rules.py inside a READ ONLY session — writes nothing
#   apply          the dry-run again (it must be exactly the reviewed plan: 2 to apply), a CHECKED data-only backup of
#                  trailer_groups (ops/lib/icb_backup.sh), then the tool's apply: ONE transaction, every row re-read FOR
#                  UPDATE and re-checked before the commit; journal + backup + provenance kept in
#                  /var/backups/icb-rt6-2026-10/; a second dry-run must find nothing left to apply
#   revert         puts every journaled row back; the tool refuses if a row moved since
# Nothing under /opt/icb-platform changes; no service is touched; nothing is a deploy; no price, formula, BOM row,
# option, draft, draft backup or saved costing moves (the rules are trailer_groups.insulation_rule only).
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u

MODE=${1:-}; ARG=${2:-}
BASE=/tmp/icb-rt6-rules
KEEP=/var/backups/icb-rt6-2026-10
PY=/opt/icb-platform/.venv/bin/python
TS=$(date -u +%Y%m%dT%H%M%SZ)
USAGE="usage: sudo bash $0 dryrun | apply | show | revert <journal.json>"
case "$MODE" in
  dryrun|apply|show) [ -z "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
  revert) [ -n "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
  *) echo "$USAGE"; exit 1 ;;
esac
OUT=$BASE/out-$MODE-$TS
stop() { echo; echo "######## STOP [$1]: $2"; [ -d "$OUT" ] && chmod -R a+rX "$OUT"; echo "######## tell the CA${OUT:+: $OUT}"; exit 1; }
say()  { echo "== $*"; }

# ---- where am I? (the first line, before anything else) ----------------------------------------------------------
URL=''
if [ "$(id -u)" = 0 ] && [ -r /etc/icb/backend.env ]; then
  URL=$( set -a; . /etc/icb/backend.env >/dev/null 2>&1; printf '%s' "${DATABASE_URL:-}" )
  URL=${URL/postgresql+psycopg:/postgresql:}
fi
# shellcheck disable=SC1091
. "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT6 rules $MODE · machine $(hostname -s) · db ? · head ?"; OUT=''; stop KIT "lib/icb_where.sh missing: re-stage"; }
# shellcheck disable=SC1091
. "$BASE/expected.env" 2>/dev/null || true
export PGOPTIONS='-c default_transaction_read_only=on'    # the identity read only; unset before any write
icb_where "rules $MODE" /opt/icb-platform "$URL"
unset PGOPTIONS
OUT_TMP=$OUT; OUT=''
[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
[ -n "$URL" ] || stop KIT "DATABASE_URL not found in /etc/icb/backend.env"
for v in EXPECT_MACHINE EXPECT_DB EXPECT_DBHOST EXPECT_HEADS EXPECT_ALEMBIC PLAN_TODO TOOL_SHA STAGED_FROM; do
  [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
done
icb_where_check || stop WHERE "$WHERE_WHY"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
TOOL="$BASE/rt6_rules.py"
[ "$(sha256sum "$TOOL" | cut -d' ' -f1)" = "$TOOL_SHA" ] || stop KIT "rt6_rules.py is not the reviewed bytes"
# shellcheck disable=SC1091
. "$BASE/lib/icb_backup.sh" || stop KIT "lib/icb_backup.sh missing: re-stage"
OUT=$OUT_TMP
[ -e "$OUT" ] && { OUT=''; stop KIT "$OUT_TMP already exists (two runs in one second?): run again"; }
mkdir -p "$OUT" && chmod 700 "$OUT" || { OUT=''; stop KIT "cannot create $OUT_TMP"; }
exec > >(tee -a "$OUT/run.txt") 2>&1
echo "(the line above, as run: machine $WHERE_MACHINE, db $WHERE_DB @ $WHERE_DBHOST, head $WHERE_HEAD, mode $MODE)"
q() { PGOPTIONS='-c default_transaction_read_only=on' psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "$1" 2>&1; }
export PYTHONDONTWRITEBYTECODE=1
ALEMBIC=$(q "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC (the rules go over v1.61.0 only)"
say "prod: alembic=$ALEMBIC staged=${STAGED_FROM:0:7} mode=$MODE  $(date -Is)"
$PY -c "import psycopg" || stop IMPORT "psycopg does not import in prod's venv"

plan_line() { grep -E '^[0-9]+ to apply, [0-9]+ already applied\.$' "$1" | tail -n1; }
RO='-c default_transaction_read_only=on'
dry()  { PGOPTIONS="$RO" $PY "$TOOL" --target prod > "$1" 2>&1; }   # exit 2 = a guard refused
show() { PGOPTIONS="$RO" $PY "$TOOL" --target prod --show; }

if [ "$MODE" = show ]; then
  say "every family's insulation rule, the greyed masters and the breach count (READ ONLY)"
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
    say "the rules are ALREADY on prod ($P) — nothing to do"; chmod -R a+rX "$OUT"
    echo; echo "######## DONE ($MODE: already applied) — tell the CA: $OUT"; exit 0
  fi
  [ "$P" = "$PLAN_TODO to apply, 0 already applied." ] || stop PLAN "the plan is '$P', the reviewed plan is '$PLAN_TODO to apply, 0 already applied.'"
  if [ "$MODE" = dryrun ]; then
    chmod -R a+rX "$OUT"; echo; echo "######## DONE (dryrun: $P) — tell the CA: $OUT"; exit 0
  fi

  mkdir -p "$KEEP" && chmod 700 "$KEEP" || stop BACKUP "cannot create $KEEP"
  BK="$KEEP/pre_apply_rules_$TS.sql.gz"
  say "pre-apply backup (data only, checked): trailer_groups"
  icb_backup "$BK" data-gz "$URL" icb_costings.trailer_groups || stop BACKUP "$ICB_BACKUP_WHY — nothing applied"

  say "apply — one transaction"
  $PY "$TOOL" --target prod --apply --out-dir "$OUT" > "$OUT/apply.txt" 2>&1; rc=$?
  cat "$OUT/apply.txt"
  [ $rc = 0 ] || stop APPLY "apply refused or failed (exit $rc): the transaction rolled back; nothing changed"
  J=$(ls "$OUT"/rt6_rules_journal_prod_*.json 2>/dev/null | head -n1)
  [ -n "$J" ] || stop JOURNAL "applied but no journal in $OUT — tell the CA NOW"
  JN="journal_rules_$(basename "$J")"
  cp "$J" "$KEEP/$JN" || stop JOURNAL "journal not copied to $KEEP (it is still in $OUT) — tell the CA"
  { echo "journal      $JN (the tool's own file, unchanged)"
    echo "tool         rt6_rules.py sha256 $TOOL_SHA"
    echo "staged_from  $STAGED_FROM"
    echo "prod_code    $WHERE_HEAD"
    echo "alembic      $ALEMBIC"
    echo "backup       $(basename "$BK") sha256 $ICB_BACKUP_SHA"
    echo "run_folder   $OUT"
  } > "$KEEP/${JN%.json}.provenance.txt" || stop JOURNAL "provenance note not written — tell the CA"
  echo "   ok   journal $KEEP/$JN  sha256 $(sha256sum "$KEEP/$JN" | cut -d' ' -f1)"

  say "second dry-run (must find nothing left to apply)"
  dry "$OUT/after.txt"; rc=$?
  cat "$OUT/after.txt"
  [ $rc = 0 ] && [ "$(plan_line "$OUT/after.txt")" = "0 to apply, $PLAN_TODO already applied." ] \
    || stop AFTER "the second dry-run is not '0 to apply, $PLAN_TODO already applied.' — tell the CA"
  say "the read-back (every family's rule, exactly)"
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
