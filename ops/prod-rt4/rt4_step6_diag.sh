#!/usr/bin/env bash
# RT4 close — READ ONLY diagnosis: the close check (rt4_close.sh, 12:33) found bom_sections 83 / 84 / 85 still on
# prod after window step 6's deletes. Run on the VM with sudo; writes /tmp/rt4-step6-diag.txt for the CA:
#   1. the service's own log since the window: every non-GET call on /api/bom-sections (method, path, status) and
#      every error / traceback — did a DELETE reach prod, and what did it answer?
#   2. the database (PGOPTIONS default_transaction_read_only=on): every foreign key that references bom_sections,
#      and every row still pointing at 83 / 84 / 85 through one (body_option_groups.bom_section_id, ...).
# Nothing is changed. Client addresses in the log lines are cut off. Deliberately no bare `set -e`.
set -u
OUT=/tmp/rt4-step6-diag.txt
SINCE="2026-10-05 08:50"
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
set -a; . /etc/icb/backend.env; set +a
U="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
export PGOPTIONS='-c default_transaction_read_only=on'
q() { echo "-- $1"; psql "$U" -XA -F ' | ' -P footer=off -c "$2" || echo "!! the query failed"; echo; }
{
  echo "== RT4 step-6 diagnosis $(date -Is) · code $(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse --short HEAD)"
  echo
  echo "== 1. the service log since $SINCE"
  echo "-- non-GET calls on /api/bom-sections (the request line and its status)"
  journalctl -u icb-backend --since "$SINCE" --no-pager -o short-iso 2>/dev/null \
    | grep -E '"(DELETE|PUT|POST|PATCH) /api/bom-sections' | sed -E 's/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+ - //' | tail -n 80
  echo
  echo "-- the Sections list and usage reads (count per path)"
  journalctl -u icb-backend --since "$SINCE" --no-pager 2>/dev/null \
    | grep -oE '"GET /api/bom-sections[^ ]*' | sort | uniq -c | sort -rn | head -n 20
  echo
  echo "-- errors and tracebacks"
  journalctl -u icb-backend --since "$SINCE" --no-pager -o short-iso 2>/dev/null \
    | grep -nE 'Traceback|IntegrityError|ForeignKeyViolation|violates foreign key|ERROR|Exception' | head -n 60
  echo
  echo "== 2. the database (read-only)"
  q "session" "select current_database() as db, current_setting('default_transaction_read_only') as read_only"
  q "bom_sections 83, 84, 85 now" "select id, name, sort_order, archived_at, body_option_master_id from bom_sections where id in (83,84,85) order by id"
  q "every foreign key that references bom_sections" \
    "select conrelid::regclass as tbl, conname, pg_get_constraintdef(oid) as def from pg_constraint
      where contype = 'f' and confrelid = 'bom_sections'::regclass order by 1, 2"
  q "body_option_groups pointing at 83 / 84 / 85" \
    "select id, name, sort_order, bom_section_id from body_option_groups where bom_section_id in (83,84,85) order by id"
  q "bill_of_materials pointing at 83 / 84 / 85 (expected 0)" \
    "select count(*) from bill_of_materials where bom_section_id in (83,84,85)"
  echo "== done $(date -Is)"
} > "$OUT" 2>&1
chmod a+r "$OUT"
cat "$OUT"
rm -f "$0"
