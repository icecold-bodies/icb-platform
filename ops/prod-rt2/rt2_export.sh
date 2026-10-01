#!/usr/bin/env bash
# RT2 R8 — the read-only prod export of the 15 bodies (RT2_RULING_1 R7 + R8). READ ONLY on prod.
# The operator runs, on the VM, AFTER setting bom 5284 (EXPLOSIVE UP TO 2.7 / DRD PU) to 0.041 in Body Templates:
#
#     sudo bash /tmp/icb-rt2-export/rt2_export.sh
#
# Steps: assert db icb_platform, alembic and prod's code = expected.env -> R7: bom 5284 must read 0.041 (else a STOP:
# ask the BA) -> the 15 body ids must carry their expected names -> `export_snapshot` of the 15 bodies in a READ ONLY
# session (the committed CI snapshot grows to these; G1 and the mirror read it) -> the no-people gate on the file ->
# the PU foam line summary (expect 86 lines, 57 with their own price) -> the rear-door thickness report.
# Against icb_platform it only SELECTs (every session read-only). Writes only under /tmp/icb-rt2-export/.
# No service is touched and nothing under /opt/icb-platform changes: not a deploy.
# Selects no customer, contact, end-user, user or person column (the exporter refuses them; the gate re-checks).
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u

BASE=/tmp/icb-rt2-export
STAGE=$BASE/stage/backend
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
PY=/opt/icb-platform/.venv/bin/python

mkdir -p "$OUT" || { echo "STOP: cannot create $OUT"; exit 1; }
exec > >(tee -a "$OUT/run.log") 2>&1
stop() { echo; echo "######## STOP [$1]: $2"; echo "######## tell the CA: $OUT"; chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEAD EXPECT_ALEMBIC STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
[ -r /etc/icb/backend.env ] || stop KIT "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
q() { PGOPTIONS='-c default_transaction_read_only=on' psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "$1" 2>&1; }
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/opt/icb-platform/backend
# every python session below is read-only too (libpq reads PGOPTIONS; the app sets no `options`)
export PGOPTIONS='-c default_transaction_read_only=on'

DBNAME=$(q "select current_database()") || stop DB "cannot reach the database: $DBNAME"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"
ALEMBIC=$(q "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC"
# Under sudo git refuses the icb-owned repo as "dubious ownership" unless the path is trusted (read-only).
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD 2>/dev/null || echo '?')
[ "$HEAD" = "$EXPECT_HEAD" ] || stop CODE "prod's code is ${HEAD:0:7}, this export expects ${EXPECT_HEAD:0:7} (v1.59.2)"
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7}  $(date -Is)"

cd "$STAGE" || stop KIT "cd $STAGE"
WHERE=$($PY -c "import tools.costing_audit as t; from tools.costing_audit.mes_snapshot import export_snapshot; print(t.__file__)" 2>&1 | tail -n1)
case "$WHERE" in "$STAGE"/*) ;; *) stop IMPORT "the audit tool does not import from the staged copy: $WHERE" ;; esac

# ---- 1. R7: EXPLOSIVE UP TO 2.7 DRD PU master = 0.041 (Michael's Body Templates edit) ------------------------
say "1. R7 — bom 5284 (EXPLOSIVE UP TO 2.7 / DRD PU)"
R7=$(q "select b.trailer_type_id || '|' || m.name || '|' || coalesce(b.variable_value::text, 'NULL')
          from bill_of_materials b join materials m on m.id = b.material_id where b.id = 5284") \
  || stop DB "cannot read bom 5284: $R7"
echo "   bom 5284: $R7   (body | master | thickness)"
[ "$R7" = "34|DRD PU|0.041" ] || stop R7 "bom 5284 reads '$R7', not '34|DRD PU|0.041' — set 0.041 in Body Templates first; if it was set, ask the BA (ruling R7)"

# ---- 2. the 15 bodies, by id AND name (ids are shared dev <-> prod) ------------------------------------------
say "2. the 15 bodies"
$PY - <<'PY' || stop BODIES "a body id does not carry its expected name (see above) — nothing exported"
from sqlalchemy import text
from app.database import engine
WANT = {12: "MEAT HANGER LARGE", 15: "RHINORANGE TRAILER", 16: "ICECREAM BODY SMALL", 17: "ICECREAM BODY MEDIUM",
        18: "ICECREAM BODY LARGE", 19: "FREEZER 2.3 METER", 20: "FREEZER MEDIUM", 21: "FREEZER LARGE",
        24: "EXPLOSIVE 4.9 AND UP", 25: "CHILLER 2.3 METER", 26: "CHILLER MEDIUM", 27: "CHILLER LARGE",
        34: "EXPLOSIVE UP TO 2.7", 36: "MEAT HANGER SMALL-MEDIUM", 37: "EXPLOSIVE 2.7 TO 4.8"}
with engine.connect() as c:
    ro = c.execute(text("show transaction_read_only")).scalar()
    have = {i: (n, a) for i, n, a in c.execute(text(
        "SELECT id, name, is_active FROM trailer_types WHERE id = ANY(:i)"), {"i": list(WANT)}).all()}
print(f"   session read-only: {ro}")
bad = [f"{i}: expected {n!r}, prod has {have.get(i)}" for i, n in WANT.items() if have.get(i, (None,))[0] != n]
for i, (n, a) in sorted(have.items()):
    print(f"   {i:>3} {n:<26} active={a}")
if ro != "on" or bad:
    raise SystemExit("; ".join(bad) or "the session is not read-only")
PY

# ---- 3. the export (pricing definitions only; the exporter refuses anything else) ----------------------------
say "3. snapshot export of the 15 bodies (read-only session)"
$PY - "$OUT/all.json" <<'PY' || { rm -f "$OUT/all.json"; stop SNAPSHOT "the export failed or was refused"; }
import sys
from pathlib import Path
from tools.costing_audit.mes_snapshot import export_snapshot
export_snapshot([12, 15, 16, 17, 18, 19, 20, 21, 24, 25, 26, 27, 34, 36, 37], Path(sys.argv[1]))
PY

# ---- 4. the no-people gate, again, on the written file ---------------------------------------------------------
say "4. no-people gate"
$PY - "$OUT/all.json" <<'PY' || { rm -f "$OUT/all.json"; stop GATE "no-people gate FAILED — file deleted"; }
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

# ---- 5. the PU foam line summary (from the file; the G1 preview of RT2_RETURN_1 §4.4) ------------------------
say "5. PU foam cost lines on the 15 bodies"
$PY - "$OUT/all.json" > "$OUT/pu_lines.txt" <<'PY' || stop SUMMARY "the PU summary failed"
import json, re, sys
T = json.load(open(sys.argv[1], encoding="utf-8"))["tables"]
mats = {m["id"]: m["name"] for m in T["materials"]}
tts = {t["id"]: t for t in T["trailer_types"]}
tok = re.compile(r"\{\s*(FRONT|DRD|SRD|SIDES|ROOF|FLOOR)\s+PU\s*\}", re.I)
rows = [b for b in T["bill_of_materials"] if (mats.get(b["material_id"]) or "").strip().upper() in ("PU", "PU FOAM")
        and not b["is_body_option"] and tts[b["trailer_type_id"]]["is_active"]]
own = [b for b in rows if b["unit_price_override"] is not None]
notok = [b for b in rows if not tok.search(b["formula_expression"] or "")]
print(f"active PU foam cost lines {len(rows)} · own price {len(own)} · no thickness token {len(notok)}")
for b in sorted(own + [x for x in notok if x not in own], key=lambda b: (tts[b['trailer_type_id']]['name'], b['id'])):
    print(f"   {tts[b['trailer_type_id']]['name']:<26} bom {b['id']:>5} {b['bom_section']:<6} own {b['unit_price_override']!s:<20} | {b['formula_expression']}")
PY
head -n1 "$OUT/pu_lines.txt" | sed 's/^/   /'

# ---- 6. the rear-door thickness report (read only; timestamps only, no people columns) ------------------------
say "6. rear-door thickness report"
$PY "$BASE/rt1_door_report.py" "$URL" "$STAGE/tests/costing_audit/mes_snapshot/all.json" > "$OUT/door_report.txt" 2>&1; rc=$?
cat "$OUT/door_report.txt"
[ $rc = 0 ] || stop DOORS "the door report failed (exit $rc)"

( cd "$OUT" && sha256sum all.json pu_lines.txt door_report.txt > SHA256SUMS.out )
cat > "$OUT/MANIFEST.txt" <<EOF
database     $DBNAME
alembic      $ALEMBIC
prod_code    $HEAD
staged_from  $STAGED_FROM
r7_bom_5284  $R7
pu_lines     $(head -n1 "$OUT/pu_lines.txt")
all.json     $(sha256sum "$OUT/all.json" | cut -d' ' -f1)  $(stat -c %s "$OUT/all.json") bytes
finished     $(date -Is)
EOF
chmod -R a+rX "$OUT"
echo; cat "$OUT/MANIFEST.txt"; echo
echo "######## DONE — tell the CA: $OUT"
