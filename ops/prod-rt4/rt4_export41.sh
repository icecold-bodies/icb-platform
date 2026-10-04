#!/usr/bin/env bash
# RT4 (RT4_RULING_1 Q3) — the read-only export Manifest S needs from deleted id 41. READ ONLY on prod. On the VM:
#
#     sudo bash /tmp/icb-rt4-export41/rt4_export41.sh
#
#   1. rt4_export41.py (psycopg only, one read-only session): body 41's lines in sections 83/84/85, its draft
#      payload, and EVERY body or draft that still names 83/84/85;
#   2. body 41's pricing rows, exported for the CA's mirror (the audit tool's own exporter, read-only session)
#      + the no-people gate on the written file.
# Against icb_platform it only SELECTs (every session read-only). Writes only under /tmp/icb-rt4-export41/.
# No service is touched and nothing under /opt/icb-platform changes: not a deploy.
# Selects no customer, contact, end-user, user or person column.
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u
BASE=/tmp/icb-rt4-export41
STAGE=$BASE/stage/backend
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
PY=/opt/icb-platform/.venv/bin/python
stop() { echo; echo "######## STOP [$1]: $2"; [ -d "$OUT" ] && chmod -R a+rX "$OUT"; echo "######## tell the CA: $OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEADS EXPECT_ALEMBIC STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
[ -e "$OUT" ] && stop KIT "$OUT already exists (two runs in one second?): run again"
mkdir -p "$OUT" && chmod 700 "$OUT" || stop KIT "cannot create $OUT"
exec > >(tee -a "$OUT/run.txt") 2>&1
[ -r /etc/icb/backend.env ] || stop KIT "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
export PGOPTIONS='-c default_transaction_read_only=on'
export PYTHONDONTWRITEBYTECODE=1
DBNAME=$(psql "$URL" -XAtc "select current_database()") || stop DB "cannot reach the database"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"
ALEMBIC=$(psql "$URL" -XAtc "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC"
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD 2>/dev/null || echo '?')
case " $EXPECT_HEADS " in *" $HEAD "*) ;; *) stop CODE "prod's code is ${HEAD:0:7}, expected one of: $EXPECT_HEADS" ;; esac
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} $(date -Is)"

say "1. body 41's lines in 83/84/85, its draft, and who else names them (read-only session)"
"$PY" "$BASE/rt4_export41.py" "$URL" "$OUT" > "$OUT/export41.log" 2>&1; rc=$?
grep -vE '^   bom ' "$OUT/export41.log" | head -n 20
[ $rc = 0 ] || { tail -n 20 "$OUT/export41.log"; stop EXPORT41 "the export failed (exit $rc)"; }
EM=$(grep -cE '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}' "$OUT/export41.json" || true)
[ "$EM" = 0 ] || { rm -f "$OUT"/export41.*; stop GATE "an email-shaped value in export41.json — files deleted"; }
echo "   gate ok: no email-shaped value in export41.json"

say "2. body 41's pricing rows, for the CA's mirror (read-only session)"
cd "$STAGE" || stop KIT "cd $STAGE"
export PYTHONPATH=/opt/icb-platform/backend
WHERE=$("$PY" -c "import tools.costing_audit as t; print(t.__file__)" 2>&1 | tail -n1)
case "$WHERE" in "$STAGE"/*) ;; *) stop IMPORT "the audit tool does not import from the staged copy: $WHERE" ;; esac
"$PY" - "$OUT/body41_snapshot.json" <<'PY' || { rm -f "$OUT/body41_snapshot.json"; stop SNAPSHOT "the export failed or was refused"; }
import sys
from pathlib import Path
from tools.costing_audit.mes_snapshot import export_snapshot
export_snapshot([41], Path(sys.argv[1]))
PY
"$PY" - "$OUT/body41_snapshot.json" <<'PY' || { rm -f "$OUT/body41_snapshot.json"; stop GATE "no-people gate FAILED — file deleted"; }
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
cd "$BASE" || stop KIT "cd $BASE"

( cd "$OUT" && sha256sum export41.json export41.txt body41_snapshot.json > SHA256SUMS.out )
cat > "$OUT/MANIFEST.txt" <<EOF
database     $DBNAME
alembic      $ALEMBIC
prod_code    $HEAD
staged_from  $STAGED_FROM
finished     $(date -Is)
EOF
chmod -R a+rX "$OUT"
( cd "$BASE" && tar -cf "out-$TS.tar" "out-$TS" && chmod a+r "out-$TS.tar" ) || stop TAR "cannot tar $OUT"
echo; cat "$OUT/MANIFEST.txt"; echo
echo "######## DONE — copy back: $BASE/out-$TS.tar"
