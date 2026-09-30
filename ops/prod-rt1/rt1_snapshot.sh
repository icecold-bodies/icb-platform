#!/usr/bin/env bash
# RT1 — prod pricing snapshot + reference run + rear-door thickness report. READ ONLY on prod.
# The operator runs, on the VM:
#
#     sudo bash /tmp/icb-rt1-snapshot/rt1_snapshot.sh
#
# The staged expected.env (covered by SHA256SUMS, written by mkstage_snapshot.sh) says which run it is:
#   MODE=reference  RT1 1b, BEFORE the v1.59.2 release. The five packs run as the reference; cells that
#                   are not accepted are REPORTED, not a stop, and the snapshot is taken regardless (it
#                   seeds the prod mirror and Manifest B's guards: "prod as it is now").
#   MODE=baseline   RT1 Stage 3, AFTER the release and Manifests A + B, with the pruned prod list. A pack
#                   with unaccepted cells is a STOP and no snapshot is taken (CI would go red on it).
# Steps: assert db icb_platform, alembic and prod's code = expected.env -> the five packs --env prod ->
# `audit snapshot` (the CI file, pack bodies) + the two MEAT HANGERs (no pack covers them; the mirror
# needs them for Manifest B) -> the no-people gate on both files -> the rear-door thickness report.
# Against icb_platform it only SELECTs (read-only sessions). Writes only under /tmp/icb-rt1-snapshot/.
# No service is touched and nothing under /opt/icb-platform changes: not a deploy.
# Selects no customer, contact, end-user, user or person column (the exporter refuses them).
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u

BASE=/tmp/icb-rt1-snapshot
STAGE=$BASE/stage/backend
PACKS="smoke chillers freezers icecream explosive"
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
PY=/opt/icb-platform/.venv/bin/python

mkdir -p "$OUT/reports" || { echo "STOP: cannot create $OUT"; exit 1; }
exec > >(tee -a "$OUT/run.log") 2>&1
stop() { echo; echo "######## STOP [$1]: $2"; echo "######## tell the CA: $OUT"; chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in MODE EXPECT_HEAD EXPECT_ALEMBIC STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
case "$MODE" in reference|baseline) ;; *) stop KIT "MODE is '$MODE'" ;; esac
[ -r /etc/icb/backend.env ] || stop KIT "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
q() { PGOPTIONS='-c default_transaction_read_only=on' psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "$1" 2>&1; }
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/opt/icb-platform/backend

DBNAME=$(q "select current_database()") || stop DB "cannot reach the database: $DBNAME"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"
ALEMBIC=$(q "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC"
# Under sudo git refuses the icb-owned repo as "dubious ownership" unless the path is trusted (read-only).
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD 2>/dev/null || echo '?')
[ "$HEAD" = "$EXPECT_HEAD" ] || stop CODE "prod's code is ${HEAD:0:7}, this run expects ${EXPECT_HEAD:0:7} ($MODE)"
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} mode=$MODE staged=${STAGED_FROM:0:7}  $(date -Is)"

cd "$STAGE" || stop KIT "cd $STAGE"
WHERE=$($PY -c "import app.routers.calculator, yaml, tools.costing_audit as t; from tools.costing_audit.cli import build_parser; print(t.__file__)" 2>&1 | tail -n1)
case "$WHERE" in "$STAGE"/*) ;; *) stop IMPORT "the audit tool does not import from the staged copy: $WHERE" ;; esac

# ---- 1. the reference run -----------------------------------------------------------------------
say "1. the five packs, --env prod"
RED=
for p in $PACKS; do
  $PY -m tools.costing_audit run --pack "$p" --env prod --out "$OUT/reports" \
      --stem "prod_costing_audit_$p" > "$OUT/reports/$p.log" 2>&1
  rc=$?
  md="$OUT/reports/prod_costing_audit_$p.md"
  [ -s "$md" ] || stop RUN "$p produced no report (exit $rc) — see $OUT/reports/$p.log"
  echo "   $p exit=$rc  $(grep -E '^- Cells' "$md" || true)"
  [ "$rc" != 0 ] && RED="$RED $p"
done
if [ -n "$RED" ]; then
  if [ "$MODE" = baseline ]; then
    for p in $RED; do sed -n '/^### Unaccepted differences/,/^### /p' "$OUT/reports/prod_costing_audit_$p.md" || true; done
    stop PACKS "unaccepted cells in:$RED — no snapshot taken (CI would go red on it)"
  fi
  say "NOTE: unaccepted cells in:$RED (reference mode: reported, not a stop)"
fi

# ---- 2. the snapshots (pricing definitions only; the exporter refuses anything else) --------------
say "2. snapshot export"
ARGS=; for p in $PACKS; do ARGS="$ARGS --pack $p"; done
$PY -m tools.costing_audit snapshot $ARGS --out "$OUT/all.json" || { rm -f "$OUT/all.json"; stop SNAPSHOT "the pack snapshot failed or was refused"; }
$PY - "$OUT/meat_hangers.json" <<'PY' || { rm -f "$OUT/meat_hangers.json"; stop SNAPSHOT "the MEAT HANGER snapshot failed or was refused"; }
import sys
from pathlib import Path
from sqlalchemy import text
from app.database import engine
from tools.costing_audit.mes_snapshot import export_snapshot
want = {12: "MEAT HANGER LARGE", 36: "MEAT HANGER SMALL-MEDIUM"}   # ids are shared dev <-> prod
with engine.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    have = dict(c.execute(text("SELECT id, name FROM trailer_types WHERE id = ANY(:i)"), {"i": list(want)}).all())
if have != want:
    raise SystemExit(f"body ids moved: prod has {have}, expected {want}")
export_snapshot(sorted(want), Path(sys.argv[1]))
PY

# ---- 3. the no-people gate, again, on both written files ------------------------------------------
say "3. no-people gate"
for f in all.json meat_hangers.json; do
  $PY - "$OUT/$f" <<'PY' || { rm -f "$OUT/$f"; stop GATE "no-people gate FAILED on $f — file deleted"; }
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("gate", "tests/costing_audit/test_mes_snapshot_no_people.py")
gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
gate.SNAPSHOT = Path(sys.argv[1])
for name in ("test_the_gates_catch_a_known_hit", "test_snapshot_tables_are_pricing_definitions_only",
             "test_snapshot_has_no_personal_columns", "test_snapshot_has_no_email_addresses"):
    getattr(gate, name)()
    print(f"   {Path(sys.argv[1]).name}: gate ok: {name}")
PY
done

# ---- 4. the rear-door thickness report (read only; timestamps only, no people columns) -------------
say "4. rear-door thickness report"
$PY "$BASE/rt1_door_report.py" "$URL" "$STAGE/tests/costing_audit/mes_snapshot/all.json" > "$OUT/door_report.txt" 2>&1; rc=$?
cat "$OUT/door_report.txt"
[ $rc = 0 ] || stop DOORS "the door report failed (exit $rc)"

( cd "$OUT" && sha256sum all.json meat_hangers.json door_report.txt > SHA256SUMS.out )
cat > "$OUT/MANIFEST.txt" <<EOF
database     $DBNAME
alembic      $ALEMBIC
prod_code    $HEAD
mode         $MODE
staged_from  $STAGED_FROM
packs_red    ${RED:- none}
all.json     $(sha256sum "$OUT/all.json" | cut -d' ' -f1)  $(stat -c %s "$OUT/all.json") bytes
meat_hangers $(sha256sum "$OUT/meat_hangers.json" | cut -d' ' -f1)  $(stat -c %s "$OUT/meat_hangers.json") bytes
finished     $(date -Is)
EOF
chmod -R a+rX "$OUT"
echo; cat "$OUT/MANIFEST.txt"; echo
echo "######## DONE — tell the CA: $OUT"
