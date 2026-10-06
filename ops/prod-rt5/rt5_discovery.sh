#!/usr/bin/env bash
# RT5 §3.0 — can Burt's two insulation rules still be broken on prod, and does the freezer pack's new variant price
# on prod? READ ONLY on prod. The operator runs, on the VM:
#
#     sudo bash /tmp/icb-rt5-discovery/rt5_discovery.sh
#
#   1. rt5_discovery.py (psycopg only, one read-only session): the families (the note's scope); per chiller / freezer
#      body the forbidden masters, the live draft and its backups; the saved costings and validated references that
#      carry a forbidden choice (quote numbers only); the freezers' side-door lines.
#   2. the STAGED audit tool (RT5's roof_floor_eps prototype, with its packs, golden and prod's accepted list) runs
#      the freezers and smoke packs against prod, read-only — the deployed code prices; only the tool is staged.
#
# Against icb_platform it only SELECTs (every session read-only). Writes only under /tmp/icb-rt5-discovery/.
# No service is touched and nothing under /opt/icb-platform changes: not a deploy.
# Selects no customer, contact, end-user, user or person column (see rt5_discovery.py).
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u
BASE=/tmp/icb-rt5-discovery
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
mkdir -p "$OUT/reports" && chmod 700 "$OUT" || stop KIT "cannot create $OUT"
exec > >(tee -a "$OUT/run.txt") 2>&1
[ -r /etc/icb/backend.env ] || stop KIT "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
# every session below is read-only (libpq reads PGOPTIONS; the app sets no `options`)
export PGOPTIONS='-c default_transaction_read_only=on'
export PYTHONDONTWRITEBYTECODE=1
DBNAME=$(psql "$URL" -XAtc "select current_database()") || stop DB "cannot reach the database"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"
ALEMBIC=$(psql "$URL" -XAtc "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC"
# Under sudo git refuses the icb-owned repo as "dubious ownership" unless the path is trusted (read-only).
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD 2>/dev/null || echo '?')
case " $EXPECT_HEADS " in *" $HEAD "*) ;; *) stop CODE "prod's code is ${HEAD:0:7}, expected one of: $EXPECT_HEADS" ;; esac
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} $(date -Is)"

# ---- 1. the rules on prod's data -------------------------------------------------------------------------------
say "1. discovery (read-only session)"
"$PY" "$BASE/rt5_discovery.py" "$URL" "$OUT" > "$OUT/discovery.log" 2>&1; rc=$?
grep -E '^== |^   [A-Z#]|^      [A-Z]' "$OUT/discovery.log" | head -n 120
[ $rc = 0 ] || { tail -n 20 "$OUT/discovery.log"; stop DISCOVERY "the discovery failed (exit $rc)"; }
# no email-shaped value may leave the VM
EM=$(cat "$OUT/discovery.json" "$OUT/discovery.txt" "$OUT/drafts.json" | grep -cE '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}' || true)
[ "$EM" = 0 ] || { rm -f "$OUT/discovery.json" "$OUT/discovery.txt" "$OUT/drafts.json" "$OUT/discovery.log"; stop GATE "an email-shaped value in the discovery output — files deleted"; }
echo "   gate ok: no email-shaped value in the discovery output"

# ---- 2. the freezer and smoke packs with roof_floor_eps, on prod ------------------------------------------------
say "2. the staged audit tool: freezers + smoke, --env prod (prod's deployed code prices; read-only session)"
cd "$STAGE" || stop KIT "cd $STAGE"
export PYTHONPATH=/opt/icb-platform/backend
WHERE=$("$PY" -c "import tools.costing_audit as t; print(t.__file__)" 2>&1 | tail -n1)
case "$WHERE" in "$STAGE"/*) ;; *) stop IMPORT "the audit tool does not import from the staged copy: $WHERE" ;; esac
APP=$("$PY" -c "import app; print(app.__file__)" 2>&1 | tail -n1)
case "$APP" in /opt/icb-platform/backend/*) ;; *) stop IMPORT "the app does not import from prod's code: $APP" ;; esac
for p in freezers smoke; do
  "$PY" -m tools.costing_audit run --pack "$p" --env prod --out "$OUT/reports" --stem "prod_$p" > "$OUT/reports/$p.log" 2>&1
  rc=$?
  case $rc in 0|1) ;; *) stop RUN "$p exited $rc (0 = clean, 1 = unaccepted cells; anything else is a crash) — see $OUT/reports/$p.log" ;; esac
  [ -s "$OUT/reports/prod_$p.json" ] || stop RUN "$p produced no report (exit $rc) — see $OUT/reports/$p.log"
  echo "   $p exit=$rc  $(grep -E '^- Cells' "$OUT/reports/prod_$p.md" || true)"
done
[ -z "$(find /opt/icb-platform -name __pycache__ -newer "$OUT/run.txt" 2>/dev/null | head -n1)" ] || echo "   !! a __pycache__ appeared in the repo — tell the CA"
cd "$BASE" || stop KIT "cd $BASE"

( cd "$OUT" && find . -type f ! -name SHA256SUMS.out ! -name run.txt | LC_ALL=C sort | xargs sha256sum > SHA256SUMS.out )
chmod -R a+rX "$OUT"
( cd "$BASE" && tar -cf "out-$TS.tar" "out-$TS" && chmod a+r "out-$TS.tar" ) || stop TAR "cannot tar $OUT"
echo
echo "######## DONE — tell the CA: $OUT  (copy $BASE/out-$TS.tar back)"
