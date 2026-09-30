#!/usr/bin/env bash
# v1.58.1 SRD rear-frame discovery (dispatch 6 §3.0 + BA ruling 6a §6) — READ ONLY on prod.
#
#     sudo bash /tmp/icb-srd-discovery/srd_discovery.sh
#
# One Python run: scope sweep, Trailer Designer picker scope + sweep of every item rule,
# Part B line state, then the saved-quote check — each saved v2 quote on an in-scope body
# re-priced by prod's own engine code with and without the proposed REAR FRAME rule (the
# rule is applied IN MEMORY; the engine session is read only and rolled back).
# Selects no customer, contact, end-user or person column (quote numbers only). Writes nothing
# to the database; writes only under /tmp (no .pyc into /opt/icb-platform); no service touched.
# Output: /tmp/icb-srd-discovery/out-<ts>/discovery.txt — send the CA the folder name.
#
# Deliberately no bare `set -e`: each check is a loud STOP.
set -u
BASE=/tmp/icb-srd-discovery
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT=$BASE/out-$TS
PY=/opt/icb-platform/.venv/bin/python
stop() { echo; echo "######## STOP: $*"; exit 1; }

[ "$(id -u)" = 0 ] || stop "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop "staged files do not match SHA256SUMS — re-stage"
mkdir -p "$OUT" && chmod 700 "$OUT" || stop "cannot create $OUT"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
export PGOPTIONS='-c default_transaction_read_only=on'
DBNAME=$(psql "$URL" -XAtc "select current_database()") || stop "cannot reach the database"
[ "$DBNAME" = icb_platform ] || stop "database is '$DBNAME', expected icb_platform"
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse --short=7 HEAD 2>/dev/null || echo '?')
echo "== prod: db=$DBNAME code=$HEAD $(date -Is)" | tee "$OUT/discovery.txt"
export PYTHONPATH=/opt/icb-platform/backend
export PYTHONDONTWRITEBYTECODE=1
( cd "$OUT" && "$PY" "$BASE/srd_discovery.py" "$URL" ) >> "$OUT/discovery.txt" 2>&1; rc=$?
chmod -R a+rX "$OUT"
grep -E 'LANE SCOPE|SELF-TEST|SUMMARY|!!' "$OUT/discovery.txt"
tail -n 3 "$OUT/discovery.txt"
[ $rc = 0 ] || stop "discovery script failed (exit $rc) — send the CA $OUT"
echo "== DONE: $OUT/discovery.txt ($(wc -l < "$OUT/discovery.txt") lines)"
