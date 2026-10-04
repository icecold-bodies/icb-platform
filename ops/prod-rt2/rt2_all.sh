#!/usr/bin/env bash
# RT2 window — the audit "All" from the CLI, beside the page's All (dispatch Part 4, steps 1, 3 and 5). READ ONLY.
# Michael first clicks Admin -> Costing audit -> All and lets it finish; then, on the VM:
#
#     sudo bash /tmp/icb-rt2-all/rt2_all.sh <label>        label = pre | post | afterP | afterD | afterS | close
#
# Runs the five packs from the DEPLOYED code (/opt/icb-platform/backend: the page's own golden, packs and prod list)
# with `--env prod`, then compares the page's newest finished All run with the CLI cell by cell (rt2_all_compare.py)
# and prints both sets of counts. Every database session is read-only (PGOPTIONS default_transaction_read_only=on:
# a write would fail loudly). Writes only under /tmp/icb-rt2-all/; no service touched; not a deploy. Selects no
# customer, contact, user or person column (the page run's started_by is never read).
#
# Deliberately no bare `set -e`: each check is a loud STOP.
set -u
LABEL=${1:-}
case "$LABEL" in pre|post|afterP|afterD|afterS|close) ;; *) echo "usage: sudo bash $0 pre|post|afterP|afterD|afterS|close"; exit 1 ;; esac
BASE=/tmp/icb-rt2-all
REPO=/opt/icb-platform
PY=$REPO/.venv/bin/python
PACKS="smoke chillers freezers icecream explosive"
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$LABEL-$TS
MAX_AGE_MIN=45

[ -e "$OUT" ] && { echo "STOP: $OUT already exists (two runs in one second?): run again"; exit 1; }
mkdir -p "$OUT/reports" || { echo "STOP: cannot create $OUT"; exit 1; }
chmod 700 "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
stop() { echo; echo "######## STOP [$1]: $2"; echo "######## tell the CA: $OUT"; chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEADS EXPECT_ALEMBICS STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
# the data kits' journal folders: a page run must START after the newest journal in any of them (C11).
# RT4: expected.env may name more than RT2's own (KEEP_DIRS, space-separated); RT2's stays the default.
KEEP_DIRS=${KEEP_DIRS:-/var/backups/icb-rt2-2026-10}
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
case " $EXPECT_ALEMBICS " in *" $ALEMBIC "*) ;; *) stop DB "alembic_version is '$ALEMBIC', expected one of: $EXPECT_ALEMBICS" ;; esac
# Under sudo git refuses the icb-owned repo as "dubious ownership" unless the path is trusted (read-only).
HEAD=$(git -c safe.directory=$REPO -C $REPO rev-parse HEAD 2>/dev/null || echo '?')
case " $EXPECT_HEADS " in *" $HEAD "*) ;; *) stop CODE "prod's code is ${HEAD:0:7}, expected one of: $EXPECT_HEADS" ;; esac
[ "$(git -c safe.directory=$REPO -C $REPO status --porcelain --untracked-files=no | wc -l)" = 0 ] || stop CODE "prod has modified tracked files"
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} label=$LABEL staged=${STAGED_FROM:0:7}  $(date -Is)"

say "1. the five packs, --env prod (the deployed code, read-only sessions)"
cd "$REPO/backend" || stop CODE "cd $REPO/backend"
RED=
for p in $PACKS; do
  $PY -m tools.costing_audit run --pack "$p" --env prod --out "$OUT/reports" --stem "prod_$p" > "$OUT/reports/$p.log" 2>&1
  rc=$?
  md="$OUT/reports/prod_$p.md"
  case $rc in 0|1) ;; *) stop RUN "$p exited $rc (0 = clean, 1 = unaccepted cells; anything else is a crash) — see $OUT/reports/$p.log" ;; esac
  [ -s "$md" ] && [ -s "$OUT/reports/prod_$p.json" ] || stop RUN "$p produced no report (exit $rc) — see $OUT/reports/$p.log"
  echo "   $p exit=$rc  $(grep -E '^- Cells' "$md" || true)"
  [ "$rc" != 0 ] && RED="$RED $p"
done
[ -z "$RED" ] || say "NOTE: unaccepted cells in:$RED (reported, not a stop: the window table says which are expected)"
[ -z "$(find "$REPO" -name __pycache__ -newer "$OUT/run.log" 2>/dev/null | head -n1)" ] || echo "   !! a __pycache__ appeared in the repo — tell the CA"

say "2. the page's newest All against the CLI"
NOT_BEFORE=$(for k in $KEEP_DIRS; do stat -c %Y "$k"/journal_*.json "$k"/*revert*.json 2>/dev/null; done | sort -n | tail -n1 || true)
NOT_BEFORE=${NOT_BEFORE:-0}
echo "   last data change on prod (a data-kit apply or revert journal in $KEEP_DIRS): $( [ "$NOT_BEFORE" = 0 ] && echo none || date -d "@$NOT_BEFORE" -Is)"
"$PY" "$BASE/rt2_all_compare.py" "$URL" "$OUT/reports" "$MAX_AGE_MIN" "$NOT_BEFORE" > "$OUT/compare.txt" 2>&1; rc=$?
cat "$OUT/compare.txt"
( cd "$OUT" && sha256sum reports/*.json compare.txt > SHA256SUMS.out )
chmod -R a+rX "$OUT"
case $rc in
  0) echo; echo "######## DONE ($LABEL): PAGE = CLI — tell the CA: $OUT" ;;
  1) echo; echo "######## DONE ($LABEL): the page and the CLI DIFFER — change nothing; tell the CA: $OUT"; exit 1 ;;
  *) stop PAGE "no usable page run (see above) — click All, wait for it to finish, run again" ;;
esac
