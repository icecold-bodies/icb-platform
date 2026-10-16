#!/usr/bin/env bash
# RT7 §3.0 — the audit truth on prod today. READ ONLY on prod. Michael runs ONE line on Windows (run_discovery.ps1
# copies the kit, runs this over `ssh -t`, and fetches the result); on the VM itself:
#
#     sudo bash /tmp/icb-rt7-discovery/rt7_discovery.sh
#
# Its FIRST output line names the machine, the database (name and host), the git HEAD and the BOOT TIME, and it
# refuses unless they are prod's — and refuses a kit staged before the last boot (ops/lib/icb_where.sh, the RT7
# reboot guard). Then, from the DEPLOYED code (/opt/icb-platform/backend: its golden, packs and prod accepted list):
#   1. All — the five costing-audit packs, `--env prod` (the CLI twin of the admin page's All);
#   2. `audit snapshot` of the five packs' bodies (the CI baseline candidate). The exporter is an allow-list:
#      a table outside it, or a personal-looking column, refuses the whole export;
#   3. the no-people gate re-run on the written file, and its inventory: every table, its row count and its column
#      NAMES (rt7_inventory.py) — the G4 proof;
#   4. a summary of every unaccepted cell by body, section and cause (rt7_summary.py) — cells, never customers.
# Every database session is read-only (PGOPTIONS default_transaction_read_only=on: a write would fail loudly). Writes
# only under /tmp/icb-rt7-discovery/. No service is touched and nothing under /opt/icb-platform changes (no
# __pycache__ either): not a deploy. Never prints a value from an environment file.
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u
BASE=/tmp/icb-rt7-discovery
KIT_DIR=$BASE
ICB_LANE=RT7
REPO=/opt/icb-platform
PY=$REPO/.venv/bin/python
PACKS="smoke chillers freezers icecream explosive"
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
stop() { echo; echo "######## STOP [$1]: $2"; [ -d "${OUT:-/nonexistent}" ] && chmod -R a+rX "$OUT"; echo "######## nothing was changed on prod — tell the CA${OUT:+: $OUT}"; exit 1; }
say()  { echo "== $*"; }

# ---- where am I? (the first line, before anything else) ----------------------------------------------------------
URL=''
if [ "$(id -u)" = 0 ] && [ -r /etc/icb/backend.env ]; then
  # only DATABASE_URL is taken, in a subshell: nothing else of the file enters this script
  URL=$( set -a; . /etc/icb/backend.env >/dev/null 2>&1; printf '%s' "${DATABASE_URL:-}" )
  URL=${URL/postgresql+psycopg:/postgresql:}
fi
export PGOPTIONS='-c default_transaction_read_only=on'     # every session below is read-only (libpq reads it)
# shellcheck disable=SC1091
. "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT7 discovery · machine $(hostname -s) · db ? · head ? · boot ?"; stop KIT "lib/icb_where.sh missing: copy the kit again"; }
# shellcheck disable=SC1091
. "$BASE/expected.env" 2>/dev/null || true
icb_where "discovery (read only)" "$REPO" "$URL"
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
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=$REPO/backend
cd "$REPO/backend" || stop CODE "cd $REPO/backend"
$PY -c "import app.routers.calculator, yaml; from tools.costing_audit.cli import build_parser" \
  || stop CODE "the deployed audit tool does not import"

# ---- 1. All — the five packs, --env prod --------------------------------------------------------------------------
say "1. All: the five packs, --env prod (the deployed code, read-only sessions)"
for p in $PACKS; do
  $PY -m tools.costing_audit run --pack "$p" --env prod --out "$OUT/reports" --stem "prod_$p" > "$OUT/reports/$p.log" 2>&1
  rc=$?
  case $rc in 0|1) ;; *) stop RUN "$p exited $rc (0 = clean, 1 = unaccepted cells; anything else is a crash) — see $OUT/reports/$p.log" ;; esac
  [ -s "$OUT/reports/prod_$p.md" ] && [ -s "$OUT/reports/prod_$p.json" ] || stop RUN "$p produced no report (exit $rc)"
  echo "   $p exit=$rc  $(grep -E '^- Cells' "$OUT/reports/prod_$p.md" || true)"
done

# ---- 2. the snapshot export (pricing definitions only) -------------------------------------------------------------
say "2. snapshot export (allow-listed pricing tables; refuses on any other table or a personal-looking column)"
ARGS=; for p in $PACKS; do ARGS="$ARGS --pack $p"; done
# shellcheck disable=SC2086
$PY -m tools.costing_audit snapshot $ARGS --out "$OUT/all.json" > "$OUT/snapshot.log" 2>&1 \
  || { cat "$OUT/snapshot.log"; rm -f "$OUT/all.json"; stop EXPORT "the export failed or was refused (see above) — file removed"; }
sed 's/^/   /' "$OUT/snapshot.log"

# ---- 3. the no-people gate, again, on the written file; its inventory ----------------------------------------------
say "3. the no-people gate on the written file + its inventory (tables, rows, column NAMES)"
$PY "$BASE/rt7_inventory.py" "$OUT/all.json" "$BASE/test_mes_snapshot_no_people.py" > "$OUT/inventory.txt" 2>&1 \
  || { cat "$OUT/inventory.txt"; rm -f "$OUT/all.json"; stop GATE "the no-people gate FAILED on the export — file removed"; }
cat "$OUT/inventory.txt"

# ---- 4. the unaccepted cells, by body / section / cause -------------------------------------------------------------
say "4. unaccepted cells by body, section and cause"
$PY "$BASE/rt7_summary.py" "$OUT/reports" > "$OUT/summary.txt" 2>&1 || stop SUMMARY "the summary failed (see $OUT/summary.txt)"
cat "$OUT/summary.txt"
[ -z "$(find "$REPO" -name __pycache__ -newer "$OUT/run.txt" 2>/dev/null | head -n1)" ] || echo "   !! a __pycache__ appeared in the repo — tell the CA"

( cd "$OUT" && sha256sum all.json reports/*.json inventory.txt summary.txt > SHA256SUMS.out ) || stop OUT "sha256sum failed"
chmod -R a+rX "$OUT"
( cd "$BASE" && tar -cf "out-$TS.tar" "out-$TS" ) || stop OUT "cannot tar $OUT"
echo
echo "######## DONE (read only) — the run line fetches $BASE/out-$TS.tar"
