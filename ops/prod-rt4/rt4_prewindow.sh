#!/usr/bin/env bash
# RT4_RULING_2 — the pre-window check of Michael's hand removals (chillers: no PU; freezers: EPS on the ROOF and
# FLOOR only). READ ONLY on prod; run any time before the window. The operator runs, on the VM:
#
#     sudo bash /tmp/icb-rt4-prewindow/rt4_prewindow.sh
#
#   (a)+(b) rt4_prewindow.py facts: what changed (the 15 snapshot bodies' pricing rows exported now with the audit
#           tool's own exporter and diffed against the committed all.json = prod on 2 Oct 17:33; the drafts against
#           the 3 Oct door report and their Settings-page backups; which insulation masters each chiller / freezer
#           draft still offers), and Manifest A's REAR FRAME rules (each condition's master by id and name; the
#           engine pricing each body DRD and SRD with the insulation it still has)
#   (c)     RT1's door report, unchanged: does it run, and read 14 OK
#   (d)     the five audit packs from the deployed code (CLI, --env prod — as rt2_all.sh does) against the 3 Oct page
#           run (#BASE_RUN), cell by cell
#
# Every database session is read-only (PGOPTIONS default_transaction_read_only=on; the python also SETs the
# transaction READ ONLY and asserts it). Writes only under /tmp/icb-rt4-prewindow/. No service is touched; nothing
# under /opt/icb-platform changes: not a deploy. Selects no customer, contact, user or person column.
# A check that cannot run is reported and the others still run; the kit STOPs only on its own preconditions and on
# the no-people gates. Deliberately no bare `set -e`.
set -u
BASE=/tmp/icb-rt4-prewindow
REPO=/opt/icb-platform
PY=$REPO/.venv/bin/python
PACKS="smoke chillers freezers icecream explosive"
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
stop() { echo; echo "######## STOP [$1]: $2"; [ -d "$OUT" ] && chmod -R a+rX "$OUT"; echo "######## tell the CA: $OUT"; exit 1; }
say()  { echo; echo "== $*"; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEADS EXPECT_ALEMBIC BASE_RUN STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
[ -e "$OUT" ] && stop KIT "$OUT already exists (two runs in one second?): run again"
mkdir -p "$OUT/reports" && chmod 700 "$OUT" || stop KIT "cannot create $OUT"
exec > >(tee -a "$OUT/run.txt") 2>&1
[ -r /etc/icb/backend.env ] || stop KIT "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
export PGOPTIONS='-c default_transaction_read_only=on'
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=$REPO/backend
DBNAME=$(psql "$URL" -XAtc "select current_database()") || stop DB "cannot reach the database"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"
ALEMBIC=$(psql "$URL" -XAtc "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC"
# Under sudo git refuses the icb-owned repo as "dubious ownership" unless the path is trusted (read-only).
HEAD=$(git -c safe.directory=$REPO -C $REPO rev-parse HEAD 2>/dev/null || echo '?')
case " $EXPECT_HEADS " in *" $HEAD "*) ;; *) stop CODE "prod's code is ${HEAD:0:7}, expected one of: $EXPECT_HEADS" ;; esac
[ "$(git -c safe.directory=$REPO -C $REPO status --porcelain --untracked-files=no | wc -l)" = 0 ] || stop CODE "prod has modified tracked files"
echo "== prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} baseline run #$BASE_RUN  $(date -Is)"
cd "$REPO/backend" || stop CODE "cd $REPO/backend"
: > "$OUT/verdicts.txt"
EMAIL='[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}'

# ---- (a) + (b) ---------------------------------------------------------------------------------------------------
say "(a)+(b) what changed, and Manifest A's rules (read-only session; the audit tool's own exporter)"
"$PY" "$BASE/rt4_prewindow.py" facts "$OUT" "$BASE" > "$OUT/facts.log" 2>&1; RC_F=$?
if [ -f "$OUT/now_snapshot.json" ]; then
  "$PY" - "$OUT/now_snapshot.json" <<'PY' || { rm -f "$OUT"/now_snapshot.json "$OUT"/snapshot_diff.json "$OUT"/facts.*; stop GATE "the no-people gate FAILED on the export — files deleted"; }
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
fi
# the drafts' labels and backup names are typed text: no email-shaped value may leave the VM
EM=$(cat "$OUT"/facts.* "$OUT"/snapshot_diff.json 2>/dev/null | grep -cE "$EMAIL" || true)
[ "$EM" = 0 ] || { rm -f "$OUT"/facts.* "$OUT"/snapshot_diff.json "$OUT"/now_snapshot.json; stop GATE "an email-shaped value in the facts — files deleted"; }
echo "   gate ok: no email-shaped value in the facts"
if [ -f "$OUT/facts.txt" ]; then
  grep -E '^== |VERDICT|Burt|draft:|DELETED|!!|-- bill_of_materials|-- materials|engine:' "$OUT/facts.txt" | head -n 160
fi
if [ $RC_F != 0 ]; then
  tail -n 25 "$OUT/facts.log"
  echo "   !! (a)/(b) did not finish (exit $RC_F) — the other checks still run; tell the CA"
  grep -q '^a:' "$OUT/verdicts.txt" || echo "a: !! DID NOT RUN (exit $RC_F, see facts.log)" >> "$OUT/verdicts.txt"
  grep -q '^b:' "$OUT/verdicts.txt" || echo "b: !! DID NOT RUN (exit $RC_F, see facts.log)" >> "$OUT/verdicts.txt"
fi

# ---- (c) ---------------------------------------------------------------------------------------------------------
say "(c) the door report (RT1's rt1_door_report.py, unchanged; read-only session)"
"$PY" "$BASE/rt1_door_report.py" "$URL" "$BASE/all.json" > "$OUT/door_report.txt" 2>&1; RC_D=$?
cat "$OUT/door_report.txt"
SUMMARY=$(grep '^SUMMARY:' "$OUT/door_report.txt" | head -n1)
case "$RC_D:$SUMMARY" in
  "0:SUMMARY: 14 OK;"*) echo "c: runs (exit 0) and reads $SUMMARY" >> "$OUT/verdicts.txt" ;;
  0:*) echo "c: !! runs (exit 0) but does NOT read 14 OK: ${SUMMARY:-no SUMMARY line}" >> "$OUT/verdicts.txt" ;;
  *)   echo "c: !! the door report FAILED (exit $RC_D): $(tail -n 1 "$OUT/door_report.txt")" >> "$OUT/verdicts.txt" ;;
esac

# ---- (d) ---------------------------------------------------------------------------------------------------------
say "(d) the five packs (the deployed code, --env prod, read-only sessions) against page run #$BASE_RUN"
CRASH=
for p in $PACKS; do
  "$PY" -m tools.costing_audit run --pack "$p" --env prod --out "$OUT/reports" --stem "prod_$p" > "$OUT/reports/$p.log" 2>&1
  rc=$?
  case $rc in 0|1) ;; *) CRASH="$CRASH $p(exit $rc)" ;; esac
  echo "   $p exit=$rc  $(grep -E '^- Cells' "$OUT/reports/prod_$p.md" 2>/dev/null || echo 'no report')"
done
if [ -n "$CRASH" ]; then
  echo "d: !! the audit crashed on:$CRASH (see reports/*.log)" >> "$OUT/verdicts.txt"
else
  "$PY" "$BASE/rt4_prewindow.py" cells "$OUT" "$OUT/reports" "$BASE_RUN" > "$OUT/cells.log" 2>&1; RC_C=$?
  grep -E '^baseline|^   stored|^page runs|^   #|^CLI|^   [a-z]|^   page|^cells:|MOVED|ONLY' "$OUT/cells.log" | head -n 80
  [ $RC_C -le 1 ] || { tail -n 15 "$OUT/cells.log"; grep -q '^d:' "$OUT/verdicts.txt" || echo "d: !! the comparison did not run (exit $RC_C)" >> "$OUT/verdicts.txt"; }
fi
[ -z "$(find "$REPO" -name __pycache__ -newer "$OUT/run.txt" 2>/dev/null | head -n1)" ] || echo "   !! a __pycache__ appeared in the repo — tell the CA"

# ---- the record --------------------------------------------------------------------------------------------------
( cd "$OUT" && find . -type f ! -name SHA256SUMS.out ! -name run.txt | LC_ALL=C sort | xargs sha256sum > SHA256SUMS.out )
cat > "$OUT/MANIFEST.txt" <<EOF
database     $DBNAME
alembic      $ALEMBIC
prod_code    $HEAD
staged_from  $STAGED_FROM
baseline_run $BASE_RUN
finished     $(date -Is)
EOF
chmod -R a+rX "$OUT"
( cd "$BASE" && tar -cf "out-$TS.tar" "out-$TS" && chmod a+r "out-$TS.tar" ) || stop TAR "cannot tar $OUT"
echo; echo "######## the four answers (RT4_RULING_2):"; sed 's/^/   /' "$OUT/verdicts.txt"
if grep -q '!!' "$OUT/verdicts.txt"; then
  echo; echo "######## DONE, WITH FINDINGS — copy back: $BASE/out-$TS.tar (the CA reports to the BA before the window)"
else
  echo; echo "######## DONE — copy back: $BASE/out-$TS.tar (the CA reads it before the window)"
fi
