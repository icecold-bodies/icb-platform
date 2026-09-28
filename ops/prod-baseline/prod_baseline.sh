#!/usr/bin/env bash
# v1.57.3 — make PROD the CI costing-audit baseline. The operator runs, on the VM:
#
#     sudo bash /tmp/icb-prod-baseline/prod_baseline.sh
#
# READ-ONLY on prod; writes only under /tmp/icb-prod-baseline/. Against icb_platform
# it only SELECTs:
#   1. assert the database is icb_platform and alembic_version is 0048;
#   2. the five costing-audit packs with prod's accepted list (the REFERENCE run);
#   3. `audit snapshot` — the calc-path pricing rows of every pack body (the exporter
#      refuses any table outside its allow-list or any personal-looking column);
#   4. the no-people gate re-run on the written file; sha256.
# Nothing under /opt/icb-platform changes, no service is touched, nothing is a deploy.
# The tool + tests are staged by the CA at /tmp/icb-prod-baseline/stage/backend.
#
# Each check is a loud STOP; deliberately no bare `set -e` (a grep with no match must
# not kill the run half way).
set -u

EXPECT_DB=icb_platform
EXPECT_ALEMBIC=0048
BASE=/tmp/icb-prod-baseline
STAGE=$BASE/stage/backend
PACKS="smoke chillers freezers icecream explosive"
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
PY=/opt/icb-platform/.venv/bin/python

mkdir -p "$OUT/reports" || { echo "STOP: cannot create $OUT"; exit 1; }
exec > >(tee -a "$OUT/run.log") 2>&1
stop() { echo; echo "######## STOP: $*"; chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop "run with sudo (the env file is root-readable only)"
[ -d "$STAGE/tools/costing_audit" ] || stop "tool not staged at $STAGE"
[ -r /etc/icb/backend.env ] || stop "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop "DATABASE_URL not set"

cd "$STAGE" || stop "cd $STAGE"
export PYTHONPATH=/opt/icb-platform/backend:/tmp/icb-audit-deps
DBNAME=$($PY -c "from app.config import settings; from app.db_guard import resolve_db_name; print(resolve_db_name(settings.DATABASE_URL))") \
  || stop "cannot resolve the database name"
[ "$DBNAME" = "$EXPECT_DB" ] || stop "database is '$DBNAME', expected $EXPECT_DB"
ALEMBIC=$($PY - <<'PY'
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
    print(c.execute(text("select version_num from alembic_version")).scalar())
PY
) || stop "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC — surface to the BA"
HEAD=$(git -C /opt/icb-platform rev-parse --short=7 HEAD 2>/dev/null || echo '?')
say "prod: db=$DBNAME alembic=$ALEMBIC code=$HEAD  $(date -Is)"

$PY -c "import app.routers.calculator, yaml; from tools.costing_audit.cli import build_parser" \
  || stop "the staged tool does not import against prod's app code"

# ---- 1. reference run --------------------------------------------------------------
say "reference run — five packs, --env prod"
CHILLERS_RC=9; OTHER_RED=
for p in $PACKS; do
  $PY -m tools.costing_audit run --pack "$p" --env prod --out "$OUT/reports" \
      --stem "prod_costing_audit_$p" > "$OUT/reports/$p.log" 2>&1
  rc=$?
  md="$OUT/reports/prod_costing_audit_$p.md"
  [ -s "$md" ] || stop "$p produced no report (exit $rc) — see $OUT/reports/$p.log"
  echo "   $p exit=$rc  $(grep -E '^- Cells' "$md")"
  [ "$p" = chillers ] && CHILLERS_RC=$rc
  [ "$p" != chillers ] && [ "$rc" != 0 ] && OTHER_RED="$OTHER_RED $p"
done
if [ "$CHILLERS_RC" != 0 ]; then
  sed -n '/^### Unaccepted differences/,/^### /p' "$OUT/reports/prod_costing_audit_chillers.md"
  stop "chillers has unaccepted cells (exit $CHILLERS_RC) — expected 0 with the SRD DOOR FITTINGS fix in; no snapshot taken"
fi
[ -n "$OTHER_RED" ] && say "NOTE: unaccepted cells in:$OTHER_RED (reported, not a stop)"

# ---- 2. snapshot export (pricing definitions only) ------------------------------------
say "snapshot export"
SNAP=$OUT/all.json
ARGS=; for p in $PACKS; do ARGS="$ARGS --pack $p"; done
$PY -m tools.costing_audit snapshot $ARGS --out "$SNAP" || { rm -f "$SNAP"; stop "snapshot export failed or was refused"; }

# ---- 3. the no-people gate, again, on the written file ---------------------------------
$PY - "$SNAP" <<'PY' || { rm -f "$SNAP"; stop "no-people gate FAILED on the export — file deleted"; }
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("gate", "tests/costing_audit/test_mes_snapshot_no_people.py")
gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
gate.SNAPSHOT = Path(sys.argv[1])
for name in ("test_the_gates_catch_a_known_hit", "test_snapshot_tables_are_pricing_definitions_only",
             "test_snapshot_has_no_personal_columns", "test_snapshot_has_no_email_addresses"):
    getattr(gate, name)()
    print(f"   gate ok: {name}")
PY

( cd "$OUT" && sha256sum all.json > all.json.sha256 )
cat > "$OUT/MANIFEST.txt" <<EOF
database     $DBNAME
alembic      $ALEMBIC
prod_code    $HEAD
snapshot     all.json  $(cut -d' ' -f1 "$OUT/all.json.sha256")  $(stat -c %s "$SNAP") bytes
chillers_rc  $CHILLERS_RC
other_red   ${OTHER_RED:- none}
finished     $(date -Is)
EOF
chmod -R a+rX "$OUT"
echo; cat "$OUT/MANIFEST.txt"; echo
echo "######## DONE — tell the CA: $TS"
