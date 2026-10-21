#!/usr/bin/env bash
# RT8 — can every pending quote on prod be edited at its saved prices? READ ONLY on prod. Michael runs ONE line on
# Windows (run_check.ps1 copies the kit, runs this over `ssh -t`, and fetches the result); on the VM itself:
#
#     sudo bash /tmp/icb-rt8-check/rt8_frozen_check.sh
#
# Its FIRST output line names the machine, the database (name and host) and the git HEAD, and it refuses unless they
# are prod's (ops/lib/icb_where.sh). Then, with the DEPLOYED code's python and engine (/opt/icb-platform):
#   1. rt8_frozen_check.py — the counts and the replay check over PENDING costings, allow-listed reads only (G4):
#      quote numbers, months, body names and counts; never a customer, contact, user or description;
#   2. the inventory of exactly what was read, and a sha256 of every output.
# Every database session is read-only (PGOPTIONS default_transaction_read_only=on: a write would fail loudly, and
# the python asserts the session mode). Writes only under its own /tmp folder. No service is touched and nothing
# under /opt/icb-platform changes (no __pycache__ either): not a deploy. Never prints a value from an env file.
#
# Each check is a loud STOP; deliberately no bare `set -e`. ICB_KIT_BASE / ICB_REPO / ICB_ENV_FILE / ICB_PY are
# overrides for the simulation only (sim/run_check_sim.sh); on prod every default applies.
set -u
BASE=${ICB_KIT_BASE:-/tmp/icb-rt8-check}
KIT_DIR=$BASE          # lib/icb_where.sh's reboot guard: KIT_DIR/.staged_at (written by the copy line) must post-date the last boot
ICB_LANE=RT8
REPO=${ICB_REPO:-/opt/icb-platform}
ENVF=${ICB_ENV_FILE:-/etc/icb/backend.env}
PY=${ICB_PY:-$REPO/.venv/bin/python}
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
stop() { echo; echo "######## STOP [$1]: $2"; [ -d "${OUT:-/nonexistent}" ] && chmod -R a+rX "$OUT"; echo "######## nothing was changed on prod — tell the CA${OUT:+: $OUT}"; exit 1; }
say()  { echo "== $*"; }

# ---- where am I? (the first line, before anything else) ----------------------------------------------------------
URL=''
if [ -r "$ENVF" ]; then
  # only DATABASE_URL is taken, in a subshell: nothing else of the file enters this script
  URL=$( set -a; . "$ENVF" >/dev/null 2>&1; printf '%s' "${DATABASE_URL:-}" )
  URL=${URL/postgresql+psycopg:/postgresql:}
fi
export PGOPTIONS='-c default_transaction_read_only=on'     # every session below is read-only (libpq reads it)
# shellcheck disable=SC1091
. "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT8 frozen-quote check · machine $(hostname -s) · db ? · head ?"; stop KIT "lib/icb_where.sh missing: copy the kit again"; }
# shellcheck disable=SC1091
. "$BASE/expected.env" 2>/dev/null || true
icb_where "frozen-quote check (read only)" "$REPO" "$URL"     # the line reads "RT8 frozen-quote check …" (ICB_LANE)
[ -r "$ENVF" ] || stop KIT "cannot read $ENVF (run with sudo: the env file is root-readable only)"
[ -n "$URL" ] || stop KIT "DATABASE_URL not found in $ENVF"
for v in EXPECT_MACHINE EXPECT_DB EXPECT_DBHOST EXPECT_HEADS EXPECT_ALEMBIC STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
icb_where_check || stop WHERE "$WHERE_WHY"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: copy the kit again"
[ -e "$OUT" ] && stop KIT "$OUT already exists (two runs in one second?): run again"
mkdir -p "$OUT" && chmod 700 "$OUT" || stop KIT "cannot create $OUT"
exec > >(tee -a "$OUT/run.txt") 2>&1
echo "(the line above, as run: machine $WHERE_MACHINE, db $WHERE_DB @ $WHERE_DBHOST, head $WHERE_HEAD)"
ALEMBIC=$(psql "$URL" -XAtc "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC"
RO=$(psql "$URL" -XAtc "select current_setting('transaction_read_only')") || stop DB "cannot read the session mode"
[ "$RO" = on ] || stop DB "the session is not read-only ($RO)"
[ "$(git -c safe.directory=$REPO -C $REPO status --porcelain --untracked-files=no | wc -l)" = 0 ] || stop CODE "prod has modified tracked files"
say "prod: alembic=$ALEMBIC · read-only sessions · staged=${STAGED_FROM:0:7} · $(date -Is)"
# The app package imports its Settings, which read DATABASE_URL and SESSION_SECRET from the ENVIRONMENT — exactly as
# the service gets them from this file. Loaded silently, never printed (RT7's 16 Oct lesson).
set -a; . "$ENVF" >/dev/null 2>&1; set +a
[ -n "${DATABASE_URL:-}" ] && [ -n "${SESSION_SECRET:-}" ] || stop KIT "$ENVF did not provide DATABASE_URL and SESSION_SECRET"
export PGOPTIONS='-c default_transaction_read_only=on'     # again, after the env file: still every session read-only
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=$REPO/backend
cd "$REPO/backend" || stop CODE "cd $REPO/backend"
$PY -c "import app.formula_engine, psycopg" || stop CODE "the deployed engine (or psycopg) does not import"

# ---- 1. the counts and the replay check -----------------------------------------------------------------------------
say "1. pending costings: counts, the replay check, repairs (allow-listed reads; quote numbers only)"
$PY "$BASE/rt8_frozen_check.py" "$OUT" > "$OUT/check.log" 2>&1 || { cat "$OUT/check.log"; stop CHECK "the check failed (see $OUT/check.log)"; }
[ -s "$OUT/summary.txt" ] && [ -s "$OUT/details.json" ] && [ -s "$OUT/inventory.txt" ] || stop CHECK "the check wrote no summary"
cat "$OUT/summary.txt"

# ---- 2. the inventory of what was read, and the hashes ---------------------------------------------------------------
say "2. what was read (the G4 proof)"
cat "$OUT/inventory.txt"
[ -z "$(find "$REPO" -name __pycache__ -newer "$OUT/run.txt" 2>/dev/null | head -n1)" ] || echo "   !! a __pycache__ appeared in the repo — tell the CA"
( cd "$OUT" && sha256sum summary.txt details.json inventory.txt > SHA256SUMS.out ) || stop OUT "sha256sum failed"
chmod -R a+rX "$OUT"
( cd "$BASE" && tar -cf "out-$TS.tar" "out-$TS" ) || stop OUT "cannot tar $OUT"
echo
echo "######## DONE (read only) — the run line fetches $BASE/out-$TS.tar"
