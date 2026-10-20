#!/usr/bin/env bash
# RT7 build paste (RT7_RULING_1 + 1A) — the CI snapshot and the reference run at ONE instant. READ ONLY on prod.
# Michael runs ONE line on Windows (run_export.ps1 copies the kit, runs this over `ssh -t`, fetches the result); on
# the VM itself:
#
#     sudo bash /tmp/icb-rt7-export/rt7_export.sh
#
# Its FIRST output line names the machine, the database (name and host), the git HEAD and the BOOT TIME, and it
# refuses unless they are prod's — and refuses a kit staged before the last boot (ops/lib/icb_where.sh). Then:
#   0. the 4G foam factor, read EXACTLY (value + updated_at): anything but '1.3170731707317074' (= 5400/4100, set by
#      Michael on 19 Oct — RT7_RULING_1A) is a STOP; and the 15 bodies, by id AND name;
#   1. All — the five costing-audit packs from the DEPLOYED code, `--env prod` (the reference run);
#   2. the snapshot export of the 15 bodies (RT2's set: the five packs' 12 + MEAT HANGER LARGE, MEAT HANGER
#      SMALL-MEDIUM, RHINORANGE — test_g1 asserts them). The exporter is an allow-list: a table outside it, or a
#      personal-looking column, refuses the whole export;
#   3. the no-people gate re-run on the written file + its inventory (tables, rows, column NAMES) — G4;
#   4. every unaccepted / accepted cell by body, section and cause (cells, never customers).
# Every database session is read-only (PGOPTIONS default_transaction_read_only=on: a write fails loudly). Writes
# only under /tmp/icb-rt7-export/. No service is touched and nothing under /opt/icb-platform changes: not a deploy.
# Never prints a value from the environment file.
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u
BASE=/tmp/icb-rt7-export
KIT_DIR=$BASE
ICB_LANE=RT7
REPO=/opt/icb-platform
PY=$REPO/.venv/bin/python
PACKS="smoke chillers freezers icecream explosive"
WANT_FACTOR='1.3170731707317074'
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
stop() { echo; echo "######## STOP [$1]: $2"; [ -d "${OUT:-/nonexistent}" ] && chmod -R a+rX "$OUT"; echo "######## nothing was changed on prod — tell the CA${OUT:+: $OUT}"; exit 1; }
say()  { echo "== $*"; }

# ---- where am I? (the first line, before anything else) ----------------------------------------------------------
URL=''
if [ "$(id -u)" = 0 ] && [ -r /etc/icb/backend.env ]; then
  URL=$( set -a; . /etc/icb/backend.env >/dev/null 2>&1; printf '%s' "${DATABASE_URL:-}" )
  URL=${URL/postgresql+psycopg:/postgresql:}
fi
export PGOPTIONS='-c default_transaction_read_only=on'     # every session below is read-only (libpq reads it)
# shellcheck disable=SC1091
. "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT7 build export · machine $(hostname -s) · db ? · head ? · boot ?"; stop KIT "lib/icb_where.sh missing: copy the kit again"; }
# shellcheck disable=SC1091
. "$BASE/expected.env" 2>/dev/null || true
icb_where "build export (read only)" "$REPO" "$URL"
[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
[ -n "$URL" ] || stop KIT "DATABASE_URL not found in /etc/icb/backend.env"
for v in EXPECT_MACHINE EXPECT_DB EXPECT_DBHOST EXPECT_HEADS EXPECT_ALEMBIC STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
icb_where_check || stop WHERE "$WHERE_WHY"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: copy the kit again"
[ -e "$OUT" ] && stop KIT "$OUT already exists (two runs in one second?): run again"
mkdir -p "$OUT/reports" && chmod 700 "$OUT" || stop KIT "cannot create $OUT"
exec > >(tee -a "$OUT/run.txt") 2>&1
echo "(the line above, as run: machine $WHERE_MACHINE, db $WHERE_DB @ $WHERE_DBHOST, head $WHERE_HEAD, boot $WHERE_BOOT_TXT)"
ALEMBIC=$(psql "$URL" -XAtc "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC"
RO=$(psql "$URL" -XAtc "select current_setting('transaction_read_only')") || stop DB "cannot read the session mode"
[ "$RO" = on ] || stop DB "the session is not read-only ($RO)"
[ "$(git -c safe.directory=$REPO -C $REPO status --porcelain --untracked-files=no | wc -l)" = 0 ] || stop CODE "prod has modified tracked files"
say "prod: alembic=$ALEMBIC · read-only sessions · staged=${STAGED_FROM:0:7} · $(date -Is)"
# The app's Settings read DATABASE_URL and SESSION_SECRET from the ENVIRONMENT, as the service does. Loaded
# silently, never printed (16 Oct: the first discovery paste stopped on exactly this).
set -a; . /etc/icb/backend.env >/dev/null 2>&1; set +a
[ -n "${DATABASE_URL:-}" ] && [ -n "${SESSION_SECRET:-}" ] || stop KIT "/etc/icb/backend.env did not provide DATABASE_URL and SESSION_SECRET"
export PGOPTIONS='-c default_transaction_read_only=on'     # again, after the env file: still every session read-only
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=$REPO/backend
cd "$REPO/backend" || stop CODE "cd $REPO/backend"
$PY -c "import app.routers.calculator, yaml; from tools.costing_audit.cli import build_parser" \
  || stop CODE "the deployed audit tool does not import"

# ---- 0. the 4G factor, exactly; the 15 bodies by id AND name --------------------------------------------------------
say "0. the 4G foam factor (exact text) and the 15 bodies"
WANT_FACTOR="$WANT_FACTOR" $PY - > "$OUT/precheck.txt" 2>&1 <<'PY'
import os
from sqlalchemy import text
from app.database import engine
WANT = {12: "MEAT HANGER LARGE", 15: "RHINORANGE TRAILER", 16: "ICECREAM BODY SMALL", 17: "ICECREAM BODY MEDIUM",
        18: "ICECREAM BODY LARGE", 19: "FREEZER 2.3 METER", 20: "FREEZER MEDIUM", 21: "FREEZER LARGE",
        24: "EXPLOSIVE 4.9 AND UP", 25: "CHILLER 2.3 METER", 26: "CHILLER MEDIUM", 27: "CHILLER LARGE",
        34: "EXPLOSIVE UP TO 2.7", 36: "MEAT HANGER SMALL-MEDIUM", 37: "EXPLOSIVE 2.7 TO 4.8"}
with engine.connect() as c:
    ro = c.execute(text("show transaction_read_only")).scalar()
    f = c.execute(text("SELECT value, updated_at FROM admin_settings WHERE key = 'costings.pu_foam_4g_factor'")).all()
    have = {i: (n, a) for i, n, a in c.execute(text(
        "SELECT id, name, is_active FROM trailer_types WHERE id = ANY(:i)"), {"i": list(WANT)}).all()}
print(f"   session read-only: {ro}")
if len(f) != 1:
    raise SystemExit(f"FACTOR: {len(f)} rows for costings.pu_foam_4g_factor (expected exactly 1)")
value, upd = f[0]
print(f"   costings.pu_foam_4g_factor = {value!r}  updated_at {upd}  (expected {os.environ['WANT_FACTOR']!r} = 5400/4100)")
bad = [f"{i}: expected {n!r}, prod has {have.get(i)}" for i, n in WANT.items() if have.get(i, (None,))[0] != n]
for i, (n, a) in sorted(have.items()):
    print(f"   {i:>3} {n:<26} active={a}")
if ro != "on":
    raise SystemExit("the session is not read-only")
if value != os.environ["WANT_FACTOR"]:
    raise SystemExit(f"FACTOR: the 4G factor reads {value!r}, not exactly {os.environ['WANT_FACTOR']!r} — "
                     "a rounded value moves cells by R0.01 (RT7_RULING_1A)")
if bad:
    raise SystemExit("BODIES: " + "; ".join(bad))
PY
rc=$?
cat "$OUT/precheck.txt"
if [ $rc != 0 ]; then
  grep -q '^FACTOR' "$OUT/precheck.txt" && stop FACTOR "$(grep '^FACTOR' "$OUT/precheck.txt" | sed 's/^FACTOR: //')"
  stop PRECHECK "see above (bodies or the session)"
fi

# ---- 1. All — the five packs, --env prod --------------------------------------------------------------------------
say "1. All: the five packs, --env prod (the deployed code, read-only sessions)"
for p in $PACKS; do
  $PY -m tools.costing_audit run --pack "$p" --env prod --out "$OUT/reports" --stem "prod_$p" > "$OUT/reports/$p.log" 2>&1
  rc=$?
  case $rc in 0|1) ;; *) stop RUN "$p exited $rc (0 = clean, 1 = unaccepted cells; anything else is a crash) — see $OUT/reports/$p.log" ;; esac
  [ -s "$OUT/reports/prod_$p.md" ] && [ -s "$OUT/reports/prod_$p.json" ] || stop RUN "$p produced no report (exit $rc)"
  echo "   $p exit=$rc  $(grep -E '^- Cells' "$OUT/reports/prod_$p.md" || true)"
done

# ---- 2. the 15-body snapshot export (pricing definitions only) -----------------------------------------------------
say "2. snapshot export of the 15 bodies (allow-listed pricing tables; refuses any other table or a personal-looking column)"
$PY - "$OUT/all.json" > "$OUT/snapshot.log" 2>&1 <<'PY' || { cat "$OUT/snapshot.log"; rm -f "$OUT/all.json"; stop EXPORT "the export failed or was refused (see above) — file removed"; }
import sys
from pathlib import Path
from tools.costing_audit.mes_snapshot import export_snapshot
export_snapshot([12, 15, 16, 17, 18, 19, 20, 21, 24, 25, 26, 27, 34, 36, 37], Path(sys.argv[1]))
PY
sed 's/^/   /' "$OUT/snapshot.log"

# ---- 3. the no-people gate, again, on the written file; its inventory ----------------------------------------------
say "3. the no-people gate on the written file + its inventory (tables, rows, column NAMES)"
$PY "$BASE/rt7_inventory.py" "$OUT/all.json" "$BASE/test_mes_snapshot_no_people.py" > "$OUT/inventory.txt" 2>&1 \
  || { cat "$OUT/inventory.txt"; rm -f "$OUT/all.json"; stop GATE "the no-people gate FAILED on the export — file removed"; }
cat "$OUT/inventory.txt"

# ---- 4. the cells, by body / section / cause ------------------------------------------------------------------------
say "4. cells by body, section and cause"
$PY "$BASE/rt7_summary.py" "$OUT/reports" > "$OUT/summary.txt" 2>&1 || stop SUMMARY "the summary failed (see $OUT/summary.txt)"
cat "$OUT/summary.txt"
[ -z "$(find "$REPO" -name __pycache__ -newer "$OUT/run.txt" 2>/dev/null | head -n1)" ] || echo "   !! a __pycache__ appeared in the repo — tell the CA"

( cd "$OUT" && sha256sum all.json reports/*.json precheck.txt inventory.txt summary.txt > SHA256SUMS.out ) || stop OUT "sha256sum failed"
chmod -R a+rX "$OUT"
( cd "$BASE" && tar -cf "out-$TS.tar" "out-$TS" ) || stop OUT "cannot tar $OUT"
echo
echo "######## DONE (read only) — the run line fetches $BASE/out-$TS.tar"
