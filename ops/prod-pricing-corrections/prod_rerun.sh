#!/usr/bin/env bash
# v1.58 — prod costing audit RE-RUN after the pricing-corrections apply, plus the read-only checks
# of BA ruling 2c (F2 draft shape, the ICECREAM 4.8 floor, the shared SRD PU sweep, the 7 Sep and
# 22 Sep change causes). The operator runs, on the VM:
#
#     sudo bash /tmp/icb-audit-rerun/prod_rerun.sh
#
# READ-ONLY on prod; writes only under /tmp/icb-audit-rerun/. Against icb_platform it only SELECTs
# (the audit costs in-process and never commits; prod_checks.sql is one READ ONLY transaction).
# Nothing under /opt/icb-platform changes, no service is touched, nothing is a deploy.
# Staged by the CA with mkrerun (git archive of one commit, LF), checked against SHA256SUMS.
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u

EXPECT_DB=icb_platform
BASE=/tmp/icb-audit-rerun
STAGE=$BASE/stage
PACKS="smoke chillers freezers icecream explosive"
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
PY=/opt/icb-platform/.venv/bin/python

mkdir -p "$OUT/reports" "$OUT/checks" || { echo "STOP: cannot create $OUT"; exit 1; }
exec > >(tee -a "$OUT/run.log") 2>&1
stop() { echo; echo "######## STOP: $*"; chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop "run with sudo (the env file is root-readable only)"
[ -d "$STAGE/backend/tools/costing_audit" ] || stop "tool not staged at $STAGE/backend"
( cd "$STAGE" && sha256sum -c --quiet SHA256SUMS ) || stop "staged files do not match SHA256SUMS — re-stage"
[ -r /etc/icb/backend.env ] || stop "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop "DATABASE_URL not set"

URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
DBNAME=$(psql "$URL" -XAtc "select current_database()") || stop "cannot reach the database"
[ "$DBNAME" = "$EXPECT_DB" ] || stop "database is '$DBNAME', expected $EXPECT_DB"
ALEMBIC=$(psql "$URL" -XAtc "select string_agg(version_num, ',') from alembic_version") || stop "cannot read alembic_version"
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse --short=7 HEAD 2>/dev/null || echo '?')
STAGED=$(cat "$STAGE/STAGED_FROM" 2>/dev/null || echo '?')
say "prod: db=$DBNAME alembic=$ALEMBIC code=$HEAD staged=$STAGED  $(date -Is)"

cd "$STAGE/backend" || stop "cd $STAGE/backend"
export PYTHONPATH=/opt/icb-platform/backend:/tmp/icb-audit-deps
$PY -c "import app.routers.calculator, yaml; from tools.costing_audit.cli import build_parser" \
  || stop "the staged tool does not import against prod's app code (is /tmp/icb-audit-deps there?)"

# ---- 1. the audit, five packs, prod's accepted list as staged ----------------------------
say "audit re-run — five packs, --env prod"
RED=
for p in $PACKS; do
  $PY -m tools.costing_audit run --pack "$p" --env prod --out "$OUT/reports" \
      --stem "prod_after_$p" > "$OUT/reports/$p.log" 2>&1
  rc=$?
  md="$OUT/reports/prod_after_$p.md"
  [ -s "$md" ] || stop "$p produced no report (exit $rc) — see $OUT/reports/$p.log"
  echo "   $p exit=$rc  $(grep -E '^- Cells' "$md")"
  [ "$rc" != 0 ] && RED="$RED $p"
done
[ -n "$RED" ] && say "NOTE: unaccepted cells in:$RED (reported, not a stop — the CA reads the reports)"

# ---- 2. the read-only checks ---------------------------------------------------------------
say "read-only checks (one READ ONLY transaction, rolled back)"
( cd "$OUT/checks" && psql "$URL" -X -q -v ON_ERROR_STOP=1 -f "$STAGE/prod_checks.sql" ) || stop "checks failed"
for f in "$OUT"/checks/*.csv; do echo "   $(basename "$f"): $(($(wc -l < "$f") - 1)) row(s)"; done

chmod -R a+rX "$OUT"
echo
echo "######## DONE — tell the CA: $OUT"
