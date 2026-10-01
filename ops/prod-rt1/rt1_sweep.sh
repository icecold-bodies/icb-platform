#!/usr/bin/env bash
# RT1 ruling 1 §3 — sweep by mechanism, READ ONLY on prod. The operator runs, on the VM:
#
#     sudo bash /tmp/icb-rt1-sweep/rt1_sweep.sh
#
# One Python run (rt1_sweep.py, psycopg only — independent of prod's app code, so it runs on v1.59.0 or v1.59.2):
# every active body's PU lines that inherit a PU material with no thickness term (the MEAT HANGER mechanism; known hit
# before Manifest M = the 11 MEAT HANGER lines), Manifest M's lines as they are now, the two rear-door templates to
# fix by hand, the stored 4G factor, and the saved costings affected (quote numbers only). A read-only session;
# writes only under /tmp/icb-rt1-sweep/; no service touched; not a deploy. No customer, contact, end-user, user or
# person column is selected.
#
# Deliberately no bare `set -e`: each check is a loud STOP.
set -u
BASE=/tmp/icb-rt1-sweep
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
PY=/opt/icb-platform/.venv/bin/python
stop() { echo; echo "######## STOP [$1]: $2"; exit 1; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEADS EXPECT_ALEMBIC STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
mkdir -p "$OUT" && chmod 700 "$OUT" || stop KIT "cannot create $OUT"
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
echo "== prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} $(date -Is)" | tee "$OUT/sweep.txt"
"$PY" "$BASE/rt1_sweep.py" "$URL" >> "$OUT/sweep.txt" 2>&1; rc=$?
chmod -R a+rX "$OUT"
grep -E 'KNOWN HIT|M APPLIED|PARTIAL|SUMMARY|STORED 4G|costing\(s\)' "$OUT/sweep.txt"
[ $rc = 0 ] || stop SWEEP "the sweep failed (exit $rc) — tell the CA: $OUT"
echo "######## DONE — tell the CA: $OUT"
