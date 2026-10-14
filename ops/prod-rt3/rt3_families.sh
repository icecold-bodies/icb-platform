#!/usr/bin/env bash
# ── RETIRED (RT6, 6 Oct 2026 — RT6_RULING_1 Q7) ─────────────────────────────────────────────────────────────────────
# This kit's reviewed plan is applied on prod, and later releases and data steps build on what it wrote. It no longer
# runs: its apply backed up with a bare `pg_dump … | gzip` (gzip's exit status only — a failed dump passed), and its
# revert would now undo work done since. The file stays as the record its runbook cites. A new data step uses
# ops/lib/icb_backup.sh (checked backup) and ops/lib/icb_where.sh (the safe-paste first line).
echo "RETIRED (RT6, 2026-10-06): $(basename "$0") no longer runs — see its header. Nothing was done." >&2; exit 3
# RT3 — the six body families on PROD, in the v1.60.0 window (RT3_RULING_1 Q7: dry-run -> apply -> journal ->
# revert). Over v1.60.0 only (alembic 0051: the colour and order columns, and the fixed startup bootstrap). The
# operator runs, on the VM, ONE step at a time and sends the CA the output folder name before the next:
#
#     sudo bash /tmp/icb-rt3-families/rt3_families.sh dryrun      read only: the 41 bodies, family and template
#                                                                  before -> after, and the template guard
#     sudo bash /tmp/icb-rt3-families/rt3_families.sh apply
#     sudo bash /tmp/icb-rt3-families/rt3_families.sh revert /var/backups/icb-rt3-2026-10/<journal>.json
#
# What each step touches on prod:
#   dryrun  ops/prod-rt3/rt3_families.py's dry-run inside a READ ONLY transaction — writes nothing
#   apply   the dry-run again (it must be exactly the reviewed plan: PLAN_TODO changes), a data-only pg_dump of the
#           two tables the tool writes (trailer_groups, trailer_types), then the tool's apply: ONE transaction,
#           every guard checked before any write and the template guard checked AGAIN from the database before the
#           commit (one mismatch rolls everything back); journal + backup + provenance kept in
#           /var/backups/icb-rt3-2026-10/; a second dry-run must find nothing left to apply
#   revert  puts every journaled row back column for column (the deleted group with its own id); the tool refuses if
#           a row moved since
# Nothing under /opt/icb-platform changes; no service is touched; nothing is a deploy; no price, formula, BOM row or
# quote document moves (the families are trailer_groups + trailer_types.group_id / override only). The tool is staged
# by the CA's mkstage_window.sh (committed bytes, LF); SHA256SUMS covers this script, expected.env and the tool.
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u

MODE=${1:-}; ARG=${2:-}
BASE=/tmp/icb-rt3-families
KEEP=/var/backups/icb-rt3-2026-10
PY=/opt/icb-platform/.venv/bin/python
TS=$(date -u +%Y%m%dT%H%M%SZ)
USAGE="usage: sudo bash $0 dryrun | apply | revert <journal.json>"
case "$MODE" in
  dryrun|apply) [ -z "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
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
TOOL="$BASE/rt3_families.py"
[ "$(sha256sum "$TOOL" | cut -d' ' -f1)" = "$TOOL_SHA" ] || stop KIT "rt3_families.py is not the reviewed bytes"
[ -r /etc/icb/backend.env ] || stop KIT "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
q() { PGOPTIONS='-c default_transaction_read_only=on' psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "$1" 2>&1; }
export PYTHONDONTWRITEBYTECODE=1

DBNAME=$(q "select current_database()") || stop DB "cannot reach the database: $DBNAME"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"
ALEMBIC=$(q "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC (the families go over v1.60.0 only)"
# Under sudo git refuses the icb-owned repo as "dubious ownership" unless the path is trusted (read-only).
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD 2>/dev/null || echo '?')
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} mode=$MODE  $(date -Is)"
[ "$HEAD" = "$EXPECT_HEAD" ] || stop CODE "prod's code is ${HEAD:0:7}; the families go only over the v1.60.0 release ${EXPECT_HEAD:0:7}"
$PY -c "import psycopg" || stop IMPORT "psycopg does not import in prod's venv"

plan_line() { grep -E '^[0-9]+ to apply, [0-9]+ already applied\.$' "$1" | tail -n1; }
dry() { $PY "$TOOL" --target prod > "$1" 2>&1; }       # exit 2 = a guard refused (prod is not where the plan says)
GUARD_LINE='^TEMPLATE GUARD: 16 of 16 active bodies keep their resolved template; changed: \[11, 22, 23, 28, 29, 30, 31, 32, 33, 35\]'

if [ "$MODE" = dryrun ] || [ "$MODE" = apply ]; then
  say "dry-run (READ ONLY)"
  dry "$OUT/dryrun.txt"; rc=$?
  cat "$OUT/dryrun.txt"
  [ $rc = 0 ] || stop GUARD "the dry-run refused (exit $rc): a guard mismatch means prod moved since the 2 Oct discovery; nothing written"
  P=$(plan_line "$OUT/dryrun.txt")
  if [ "$P" = "0 to apply, $PLAN_TODO already applied." ]; then
    say "the families are ALREADY on prod ($P) — nothing to do"; chmod -R a+rX "$OUT"
    echo; echo "######## DONE ($MODE: already applied) — tell the CA: $OUT"; exit 0
  fi
  [ "$P" = "$PLAN_TODO to apply, 0 already applied." ] || stop PLAN "the plan is '$P', the reviewed plan is '$PLAN_TODO to apply, 0 already applied.'"
  grep -qE "$GUARD_LINE" "$OUT/dryrun.txt" || stop GUARD "the template guard line is not the reviewed one (16 of 16 active, the 10 Q5 copies)"
  if [ "$MODE" = dryrun ]; then
    chmod -R a+rX "$OUT"; echo; echo "######## DONE (dryrun: $P) — tell the CA: $OUT"; exit 0
  fi

  mkdir -p "$KEEP" && chmod 700 "$KEEP" || stop BACKUP "cannot create $KEEP"
  BK="$KEEP/pre_apply_families_$TS.sql.gz"
  say "pre-apply backup (data only): trailer_groups + trailer_types"
  pg_dump "$URL" --data-only -t icb_costings.trailer_groups -t icb_costings.trailer_types | gzip > "$BK" \
    || stop BACKUP "pg_dump failed — nothing applied"
  [ -s "$BK" ] && gzip -t "$BK" || stop BACKUP "$BK is empty or not gzip — nothing applied"
  echo "   ok   $BK $(stat -c %s "$BK") bytes sha256 $(sha256sum "$BK" | cut -d' ' -f1)"

  say "apply — one transaction"
  $PY "$TOOL" --target prod --apply --out-dir "$OUT" > "$OUT/apply.txt" 2>&1; rc=$?
  cat "$OUT/apply.txt"
  [ $rc = 0 ] || stop APPLY "apply refused or failed (exit $rc): the transaction rolled back; nothing changed"
  J=$(ls "$OUT"/rt3_families_journal_prod_*.json 2>/dev/null | head -n1)
  [ -n "$J" ] || stop JOURNAL "applied but no journal in $OUT — tell the CA NOW"
  JN="journal_families_$(basename "$J")"
  cp "$J" "$KEEP/$JN" || stop JOURNAL "journal not copied to $KEEP (it is still in $OUT) — tell the CA"
  { echo "journal      $JN (the tool's own file, unchanged)"
    echo "tool         rt3_families.py sha256 $TOOL_SHA"
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
    || stop AFTER "the second dry-run still finds work — tell the CA"
  chmod -R a+rX "$OUT"
  echo; echo "######## DONE (apply) — journal $KEEP/$JN — tell the CA: $OUT"; exit 0
fi

# revert
JR=$ARG
[ -f "$JR" ] || stop USAGE "no such journal: $JR (see $KEEP)"
$PY -c 'import json,sys; j=json.load(open(sys.argv[1])); sys.exit(0 if j.get("tool") == "rt3_families" else 1)' "$JR" 2>/dev/null \
  || stop USAGE "not an RT3 families journal: $JR"
say "revert the families from $(basename "$JR")"
$PY "$TOOL" --target prod --revert "$JR" --out-dir "$OUT" > "$OUT/revert.txt" 2>&1; rc=$?
cat "$OUT/revert.txt"
[ $rc = 0 ] || stop REVERT "revert refused (exit $rc): nothing changed"
cp "$OUT"/rt3_families_revert_prod_*.json "$KEEP/" 2>/dev/null || true
dry "$OUT/after.txt"; rc=$?
[ $rc = 0 ] && [ "$(plan_line "$OUT/after.txt")" = "$PLAN_TODO to apply, 0 already applied." ] \
  || { cat "$OUT/after.txt"; stop AFTER "after the revert the dry-run is not back to the reviewed plan — tell the CA"; }
chmod -R a+rX "$OUT"
echo; echo "######## DONE (revert: prod is back to the before-state) — tell the CA: $OUT"
