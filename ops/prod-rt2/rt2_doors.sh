#!/usr/bin/env bash
# RT2 — the rear-door thickness report, READ ONLY on prod: the prod proof of Part 1 (dispatch Part 4, step 6: after
# Michael's door test — a test quote toggled DRD <-> SRD and EPS <-> PU several times — it must still read 14 OK;
# again at the close). The operator runs, on the VM:
#
#     sudo bash /tmp/icb-rt2-doors/rt2_doors.sh
#
# RT1's report, unchanged (ops/prod-rt1/rt1_door_report.py, psycopg only): the 14 Manifest A bodies' rear-door
# insulation masters against the door the calculator opens with, one verdict per body. Before v1.59.3 a door toggle
# in the calculator rewrote these masters (RT1's 12 -> 11 -> 10 -> 12 -> 13 -> 14 OK timeline); from v1.59.3 a quote
# never writes the Body Template, so toggling cannot move them. The "then -> now" column compares with the committed
# CI snapshot. A read-only session; writes only under /tmp/icb-rt2-doors/; no service touched; not a deploy. Selects
# the draft's updated_at only — no person, customer or contact column.
#
# Deliberately no bare `set -e`: each check is a loud STOP.
set -u
BASE=/tmp/icb-rt2-doors
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
PY=/opt/icb-platform/.venv/bin/python
stop() { echo; echo "######## STOP [$1]: $2"; exit 1; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEADS EXPECT_ALEMBICS STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
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
case " $EXPECT_ALEMBICS " in *" $ALEMBIC "*) ;; *) stop DB "alembic_version is '$ALEMBIC', expected one of: $EXPECT_ALEMBICS" ;; esac
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD 2>/dev/null || echo '?')
case " $EXPECT_HEADS " in *" $HEAD "*) ;; *) stop CODE "prod's code is ${HEAD:0:7}, expected one of: $EXPECT_HEADS" ;; esac
echo "== prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} $(date -Is)" | tee "$OUT/door_report.txt"
"$PY" "$BASE/rt1_door_report.py" "$URL" "$BASE/all.json" >> "$OUT/door_report.txt" 2>&1; rc=$?
chmod -R a+rX "$OUT"
sed -n '2,$p' "$OUT/door_report.txt"
[ $rc = 0 ] || stop DOORS "the door report failed (exit $rc) — tell the CA: $OUT"
echo "######## DONE — tell the CA: $OUT"
