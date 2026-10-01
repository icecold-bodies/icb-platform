#!/usr/bin/env bash
# RT1 ruling 3 addendum — READ ONLY on prod, before F2 and the close. The operator runs, on the VM:
#
#     sudo bash /tmp/icb-rt1-check/rt1_check.sh
#
# One Python run (rt1_check.py, psycopg only, so it runs on v1.59.0 or v1.59.2): every PU foam material's price (must
# read R4 100) and the PU foam lines with their own price; the stored 4G factor; the three chillers after the "no PU
# on chillers" edit (masters, PU foam lines, PU nodes in their drafts, and a dump of their BOM rows for the CA's diff);
# Manifest A's REAR FRAME rules against their masters. A read-only session; writes only under /tmp/icb-rt1-check/;
# no service touched; not a deploy. No customer, contact, user or person column is selected.
#
# Deliberately no bare `set -e`: each check is a loud STOP.
set -u
BASE=/tmp/icb-rt1-check
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
echo "== prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} $(date -Is)" | tee "$OUT/check.txt"
"$PY" "$BASE/rt1_check.py" "$URL" "$OUT" >> "$OUT/check.txt" 2>&1; rc=$?
chmod -R a+rX "$OUT"
grep -E 'SUMMARY|STORED 4G|OWN price|of them named PU|PU foam lines:|nodes that name PU|chiller_rows' "$OUT/check.txt"
[ $rc = 0 ] || stop CHECK "the check failed (exit $rc) — tell the CA: $OUT"
echo "######## DONE — tell the CA: $OUT"
