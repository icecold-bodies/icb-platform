#!/usr/bin/env bash
# RT1 — Manifest F on PROD: the stored PU 4G factor (RT1 ruling 2 §2a), one admin setting:
#   admin_settings['costings.pu_foam_4g_factor']  1.3170731707317074 (5 400 / 4 100)  ->  1.362881562881563 (5 581 / 4 095)
# The operator runs, on the VM, ONE step at a time and sends the CA the output folder name before the next:
#
#     sudo bash /tmp/icb-rt1-factor/rt1_factor.sh dryrun       read only
#     sudo bash /tmp/icb-rt1-factor/rt1_factor.sh apply        on the BA's GO — over v1.59.0 or v1.59.2, no order with A / M
#     sudo bash /tmp/icb-rt1-factor/rt1_factor.sh revert /var/backups/icb-rt1-2026-09/<journal_F_…>.json
#
# What each step touches on prod:
#   dryrun  the tool's dry-run in a READ ONLY session — writes nothing; it also lists the saved costings graded 4G
#           (quote numbers only)
#   apply   the dry-run again (must be exactly the reviewed plan), a data-only pg_dump of admin_settings, then ONE
#           transaction: the row locked, its exact value checked, one UPDATE; journal + backup + provenance kept in
#           /var/backups/icb-rt1-2026-09/; a second dry-run must find nothing left to apply
#   revert  value AND updated_at back byte for byte (the tool refuses if the row moved since F)
# The calculator reads the factor on every calculation: F takes effect on the next one. No restart, no deploy;
# nothing under /opt/icb-platform changes. The tool is staged by the CA's mkstage_factor.sh (committed bytes, LF);
# SHA256SUMS covers this script, the tool and expected.env.
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u

MODE=${1:-}; ARG=${2:-}
BASE=/tmp/icb-rt1-factor
KEEP=/var/backups/icb-rt1-2026-09
PY=/opt/icb-platform/.venv/bin/python
TS=$(date -u +%Y%m%dT%H%M%SZ)
USAGE="usage: sudo bash $0 dryrun | apply | revert <journal.json>"
case "$MODE" in
  dryrun|apply) [ -z "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
  revert) [ -n "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
  *) echo "$USAGE"; exit 1 ;;
esac
OUT=$BASE/out-$MODE-F-$TS

mkdir -p "$OUT" || { echo "STOP: cannot create $OUT"; exit 1; }
chmod 700 "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
stop() { echo; echo "######## STOP [$1]: $2"; echo "######## tell the CA: $OUT"; chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEADS EXPECT_ALEMBIC F_BEFORE F_AFTER TOOL_SHA STAGED_FROM; do
  [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
done
[ "$(sha256sum "$BASE/rt1_factor.py" | cut -d' ' -f1)" = "$TOOL_SHA" ] || stop KIT "rt1_factor.py is not the reviewed bytes"
[ -r /etc/icb/backend.env ] || stop KIT "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
q() { PGOPTIONS='-c default_transaction_read_only=on' psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "$1" 2>&1; }
export PYTHONDONTWRITEBYTECODE=1

DBNAME=$(q "select current_database()") || stop DB "cannot reach the database: $DBNAME"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"
ALEMBIC=$(q "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC"
# Under sudo git refuses the icb-owned repo as "dubious ownership" unless the path is trusted (read-only).
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD 2>/dev/null || echo '?')
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} mode=$MODE F  $(date -Is)"
# F is one admin setting the calculator reads the same way on v1.59.0 and v1.59.2: either code, no order with A or M.
case " $EXPECT_HEADS " in *" $HEAD "*) ;; *) stop CODE "prod's code is ${HEAD:0:7}; Manifest F goes only over: $EXPECT_HEADS" ;; esac
$PY -c "import psycopg" || stop IMPORT "psycopg does not import in prod's venv"

tool() { $PY "$BASE/rt1_factor.py" --target prod "$@"; }
plan_line() { grep -E '^[0-9]+ to apply, [0-9]+ already applied\.$' "$1" | tail -n1; }
factor_now() { q "select value from icb_costings.admin_settings where key = 'costings.pu_foam_4g_factor'"; }
TODO="1 to apply, 0 already applied."
DONE_PLAN="0 to apply, 1 already applied."

if [ "$MODE" = dryrun ] || [ "$MODE" = apply ]; then
  CUR=$(factor_now) || stop DB "cannot read the factor: $CUR"
  echo "   psql: the stored 4G factor is '$CUR'"
  say "dry-run F (READ ONLY)"
  tool > "$OUT/dryrun.txt" 2>&1; rc=$?
  cat "$OUT/dryrun.txt"
  [ $rc = 0 ] || stop GUARD "the dry-run refused (exit $rc): the factor is not where F says; nothing written"
  P=$(plan_line "$OUT/dryrun.txt")
  if [ "$P" = "$DONE_PLAN" ]; then
    [ "$CUR" = "$F_AFTER" ] || stop GUARD "the tool says applied but psql reads '$CUR'"
    say "Manifest F is ALREADY on prod ($P) — nothing to do"; chmod -R a+rX "$OUT"
    echo; echo "######## DONE ($MODE F: already applied) — tell the CA: $OUT"; exit 0
  fi
  [ "$P" = "$TODO" ] || stop PLAN "the plan is '$P', the reviewed plan is '$TODO'"
  [ "$CUR" = "$F_BEFORE" ] || stop GUARD "psql reads '$CUR', F expects '$F_BEFORE'"
  if [ "$MODE" = dryrun ]; then
    chmod -R a+rX "$OUT"; echo; echo "######## DONE (dryrun F: $P) — tell the CA: $OUT"; exit 0
  fi

  say "pre-apply backup (data only): admin_settings"
  mkdir -p "$KEEP" && chmod 700 "$KEEP" || stop BACKUP "cannot create $KEEP"
  BK="$KEEP/pre_apply_F_$TS.sql.gz"
  pg_dump "$URL" --data-only -t icb_costings.admin_settings | gzip > "$BK" || stop BACKUP "pg_dump failed — nothing applied"
  [ -s "$BK" ] && gzip -t "$BK" || stop BACKUP "$BK is empty or not gzip — nothing applied"
  echo "   ok   $BK $(stat -c %s "$BK") bytes sha256 $(sha256sum "$BK" | cut -d' ' -f1)"

  say "apply F — one transaction"
  tool --apply --out-dir "$OUT" > "$OUT/apply.txt" 2>&1; rc=$?
  cat "$OUT/apply.txt"
  [ $rc = 0 ] || stop APPLY "apply refused or failed (exit $rc): the transaction rolled back; nothing changed"
  J=$(ls "$OUT"/rt1_factor_journal_prod_*.json 2>/dev/null | head -n1)
  [ -n "$J" ] || stop JOURNAL "applied but no journal in $OUT — tell the CA NOW"
  JN="journal_F_$(basename "$J")"
  cp "$J" "$KEEP/$JN" || stop JOURNAL "journal not copied to $KEEP (it is still in $OUT) — tell the CA"
  { echo "journal      $JN (the tool's own file, unchanged)"
    echo "manifest     F  admin_settings['costings.pu_foam_4g_factor'] '$F_BEFORE' -> '$F_AFTER'"
    echo "tool         sha256 $TOOL_SHA"
    echo "staged_from  $STAGED_FROM"
    echo "prod_code    $HEAD"
    echo "alembic      $ALEMBIC"
    echo "backup       $(basename "$BK")"
    echo "run_folder   $OUT"
  } > "$KEEP/${JN%.json}.provenance.txt" || stop JOURNAL "provenance note not written — tell the CA"
  echo "   ok   journal $KEEP/$JN  sha256 $(sha256sum "$KEEP/$JN" | cut -d' ' -f1)"

  say "second dry-run (must find nothing left to apply)"
  tool > "$OUT/after.txt" 2>&1; rc=$?
  cat "$OUT/after.txt"
  CUR=$(factor_now)
  echo "   psql: the stored 4G factor is '$CUR'"
  [ $rc = 0 ] && [ "$(plan_line "$OUT/after.txt")" = "$DONE_PLAN" ] && [ "$CUR" = "$F_AFTER" ] \
    || stop AFTER "the second dry-run still finds work, or psql does not read '$F_AFTER' — tell the CA"
  chmod -R a+rX "$OUT"
  echo; echo "######## DONE (apply F) — journal $KEEP/$JN — tell the CA: $OUT"; exit 0
fi

# revert
JR=$ARG
[ -f "$JR" ] || stop USAGE "no such journal: $JR (see $KEEP)"
KIND=$($PY -c 'import json,sys; j=json.load(open(sys.argv[1])); print(j["tool"], j["manifest"])' "$JR" 2>/dev/null) \
  || stop USAGE "not a Manifest F journal: $JR"
[ "$KIND" = "rt1_factor F" ] || stop USAGE "not a Manifest F journal: $JR ($KIND)"
say "revert Manifest F from $(basename "$JR")"
tool --revert "$JR" --out-dir "$OUT" > "$OUT/revert.txt" 2>&1; rc=$?
cat "$OUT/revert.txt"
[ $rc = 0 ] || stop REVERT "revert refused (exit $rc): nothing changed"
cp "$OUT"/rt1_factor_revert_prod_*.json "$KEEP/" 2>/dev/null || true
CUR=$(factor_now)
echo "   psql: the stored 4G factor is '$CUR'"
[ "$CUR" = "$F_BEFORE" ] || stop AFTER "after the revert psql reads '$CUR', not '$F_BEFORE' — tell the CA"
chmod -R a+rX "$OUT"
echo; echo "######## DONE (revert F) — tell the CA: $OUT"
