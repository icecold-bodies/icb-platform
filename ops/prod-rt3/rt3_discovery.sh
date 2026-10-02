#!/usr/bin/env bash
# RT3 §3.0 — body families discovery, READ ONLY on prod. The operator runs, on the VM:
#
#     sudo bash /tmp/icb-rt3-discovery/rt3_discovery.sh
#
# One Python run of rt3_discovery.py (psycopg only): the report templates, the trailer groups, EVERY body (active and
# inactive) with its group, its resolved quote template today and its proposed family, the template guard under the
# proposal, orphaned template assignments, and saved-costing counts per body. A read-only session; writes only under
# /tmp/icb-rt3-discovery/; no service touched; not a deploy. Selects no customer, contact, user or person column.
#
# Deliberately no bare `set -e`: each check is a loud STOP.
set -u
BASE=/tmp/icb-rt3-discovery
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
PY=/opt/icb-platform/.venv/bin/python
stop() { echo; echo "######## STOP [$1]: $2"; exit 1; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEADS EXPECT_ALEMBIC STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
[ -e "$OUT" ] && stop KIT "$OUT already exists (two runs in one second?): run again"
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
echo "== prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} $(date -Is)" | tee "$OUT/run.txt"
"$PY" "$BASE/rt3_discovery.py" "$URL" "$OUT" >> "$OUT/run.txt" 2>&1; rc=$?
chmod -R a+rX "$OUT"
grep -E '^== |bodies [0-9]|keep with override' "$OUT/run.txt" | head -40
[ $rc = 0 ] || stop DISCOVERY "the discovery failed (exit $rc) — tell the CA: $OUT"
echo "######## DONE — tell the CA: $OUT"
