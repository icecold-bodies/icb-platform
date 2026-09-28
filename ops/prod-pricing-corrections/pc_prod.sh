#!/usr/bin/env bash
# v1.58 — costing-audit pricing corrections on PROD. The operator runs, on the VM, ONE mode
# at a time and sends the CA the output folder name before the next:
#
#     sudo bash /tmp/icb-audit-pc/pc_prod.sh impact     # 1. read-only impact refresh (quote numbers only)
#     sudo bash /tmp/icb-audit-pc/pc_prod.sh dryrun     # 2. the manifest against prod, READ ONLY
#     sudo bash /tmp/icb-audit-pc/pc_prod.sh apply      # 3. only after the CA/BA reviewed 1 + 2
#     sudo bash /tmp/icb-audit-pc/pc_prod.sh revert /var/backups/icb-pricing-corrections-2026-09/<journal>.json
#
# What each mode touches on prod:
#   impact  one psql READ ONLY transaction, rolled back — writes nothing; selects no customer,
#           contact, end-user or person column (quote numbers only)
#   dryrun  the tool's dry-run, inside a READ ONLY transaction — writes nothing
#   apply   first a data-only pg_dump of bill_of_materials + bom_override_history into the output
#           folder, then the tool's apply: ONE transaction, every guard checked before any write
#           (one mismatch aborts everything), journal copied to /var/backups/icb-pricing-corrections-2026-09/
#   revert  puts every journaled line back column for column (refuses if a line moved since)
# Nothing under /opt/icb-platform changes; no service is touched; nothing is a deploy.
# The tool + manifest are staged by the CA at /tmp/icb-audit-pc/stage (byte-exact, LF).
#
# Each check is a loud STOP; deliberately no bare `set -e` (a grep with no match must not
# kill the run half way).
set -u

MODE=${1:-}
EXPECT_DB=icb_platform
BASE=/tmp/icb-audit-pc
STAGE=$BASE/stage
KEEP=/var/backups/icb-pricing-corrections-2026-09
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT=$BASE/out-$MODE-$TS
PY=/opt/icb-platform/.venv/bin/python

case "$MODE" in impact|dryrun|apply|revert) ;; *)
  echo "usage: sudo bash $0 impact|dryrun|apply|revert <journal.json>"; exit 1 ;; esac

mkdir -p "$OUT" || { echo "STOP: cannot create $OUT"; exit 1; }
chmod 700 "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
stop() { echo; echo "######## STOP: $*"; chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop "run with sudo (the env file is root-readable only)"
[ -r /etc/icb/backend.env ] || stop "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop "DATABASE_URL not set"
[ -f "$STAGE/backend/tools/audit_pricing_corrections.py" ] || stop "tool not staged at $STAGE/backend/tools"
[ -f "$STAGE/docs/audit/pricing_corrections_2026-09/manifest.yaml" ] || stop "manifest not staged"
( cd "$STAGE" && sha256sum -c --quiet SHA256SUMS ) || stop "staged files do not match SHA256SUMS — re-stage"

URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
DBNAME=$(psql "$URL" -XAtc "select current_database()") || stop "cannot reach the database"
[ "$DBNAME" = "$EXPECT_DB" ] || stop "database is '$DBNAME', expected $EXPECT_DB"
ALEMBIC=$(psql "$URL" -XAtc "select string_agg(version_num, ',') from alembic_version") || stop "cannot read alembic_version"
HEAD=$(git -C /opt/icb-platform rev-parse --short=7 HEAD 2>/dev/null || echo '?')
say "prod: db=$DBNAME alembic=$ALEMBIC code=$HEAD mode=$MODE  $(date -Is)"

export PYTHONPATH=/opt/icb-platform/backend:/tmp/icb-audit-deps
TOOL="$PY $STAGE/backend/tools/audit_pricing_corrections.py --target prod"

if [ "$MODE" = impact ]; then
  cp "$STAGE/docs/audit/pricing_corrections_2026-09/impact/impact_refresh.sql" "$OUT/" || stop "sql not staged"
  ( cd "$OUT" && psql "$URL" -X -q -v ON_ERROR_STOP=1 -f impact_refresh.sql ) || stop "impact query failed"
  say "00_env.csv:"; cat "$OUT/00_env.csv"
  say "affected costings: $(($(wc -l < "$OUT/C_impact.csv") - 1))   (quote numbers only — no customer columns)"
fi

if [ "$MODE" = dryrun ] || [ "$MODE" = apply ]; then
  $PY -c "import yaml, app.formula_engine, app.db_guard" \
    || stop "PyYAML or prod's app code does not import (is /tmp/icb-audit-deps staged?)"
  say "dry-run (READ ONLY)"
  $TOOL > "$OUT/dryrun.txt" 2>&1; rc=$?
  cat "$OUT/dryrun.txt"
  [ $rc = 0 ] || stop "dry-run refused (exit $rc) — a guard mismatch means prod moved; send the CA this folder"
fi

if [ "$MODE" = apply ]; then
  grep -q "already applied" "$OUT/dryrun.txt" || stop "no plan summary in the dry-run output"
  if grep -q "^nothing to apply" "$OUT/dryrun.txt"; then
    say "nothing to apply — the manifest is already on prod"; chmod -R a+rX "$OUT"; exit 0
  fi
  say "pre-apply backup (data only): bill_of_materials + bom_override_history"
  pg_dump "$URL" --data-only -t icb_costings.bill_of_materials -t icb_costings.bom_override_history \
    | gzip > "$OUT/pre_apply_bom.sql.gz" || stop "pg_dump failed — nothing applied"
  [ -s "$OUT/pre_apply_bom.sql.gz" ] || stop "empty backup — nothing applied"
  say "apply — one transaction"
  $TOOL --apply --out-dir "$OUT" > "$OUT/apply.txt" 2>&1; rc=$?
  cat "$OUT/apply.txt"
  [ $rc = 0 ] || stop "apply refused or failed (exit $rc) — the transaction rolled back; nothing changed"
  J=$(ls "$OUT"/pricing_corrections_journal_prod_*.json 2>/dev/null | head -n1)
  [ -n "$J" ] || stop "applied but no journal found in $OUT — tell the CA NOW"
  mkdir -p "$KEEP" && cp "$J" "$OUT/pre_apply_bom.sql.gz" "$KEEP/" && chmod 700 "$KEEP" \
    || stop "journal not copied to $KEEP (it is still in $OUT) — tell the CA"
  say "second dry-run (must find nothing to apply)"
  $TOOL > "$OUT/after.txt" 2>&1
  cat "$OUT/after.txt"
  grep -q "^nothing to apply" "$OUT/after.txt" || stop "the second dry-run still finds work — tell the CA"
  say "journal kept at $KEEP/$(basename "$J")"
fi

if [ "$MODE" = revert ]; then
  JR=${2:-}
  [ -f "$JR" ] || stop "usage: revert <journal.json> (see $KEEP)"
  $TOOL --revert "$JR" --out-dir "$OUT" > "$OUT/revert.txt" 2>&1; rc=$?
  cat "$OUT/revert.txt"
  [ $rc = 0 ] || stop "revert refused (exit $rc) — nothing changed"
  cp "$OUT"/pricing_corrections_revert_prod_*.json "$KEEP/" 2>/dev/null
fi

chmod -R a+rX "$OUT"
echo
echo "######## DONE ($MODE) — tell the CA: $OUT"
