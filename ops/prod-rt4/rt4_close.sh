#!/usr/bin/env bash
# RT4 close (RT4_RULING_2 + the BA's step-6 addition), pasted on the VM and run with sudo:
#   1. READ ONLY (PGOPTIONS default_transaction_read_only=on, asserted): step 6's evidence — bom_sections 83, 84, 85
#      are gone and 26, 15, 21 exist — plus Manifest S's end state (no line or draft names 83/84/85; MANNI DF's 7
#      lines on 64 / 65; deleted id 41's 39 lines on 26 / 15 / 21);
#   2. the RT4 kit folders and tars under /tmp removed (an explicit list; /var/backups is kept);
# all of it written to /tmp/rt4-close-check.txt for the CA (the OUTCOME records it). Selects no person column.
# Deliberately no bare `set -e`.
set -u
OUT=/tmp/rt4-close-check.txt
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
set -a; . /etc/icb/backend.env; set +a
U="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
export PGOPTIONS='-c default_transaction_read_only=on'
q() { echo "-- $1"; psql "$U" -XA -F ' | ' -P footer=off -c "$2" || echo "!! the query failed"; echo; }
KIT="/tmp/icb-release-v1.60.1 /tmp/icb-release-v1.60.1.tar /tmp/icb-rt4-data /tmp/icb-rt4-data.tar
     /tmp/icb-rt2-all /tmp/icb-rt2-all.tar /tmp/icb-rt2-doors /tmp/icb-rt2-doors.tar
     /tmp/icb-rt4-prewindow /tmp/icb-rt4-prewindow.tar /tmp/icb-rt4-discovery /tmp/icb-rt4-discovery.tar
     /tmp/icb-rt4-export41 /tmp/icb-rt4-export41.tar /tmp/rt4-prewindow-back.tar /tmp/rt4-window-back.tar"
{
  echo "== RT4 close $(date -Is) · code $(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse --short HEAD)"
  echo
  echo "== 1. READ ONLY"
  q "session" "select current_database() as db, current_setting('default_transaction_read_only') as read_only,
                      (select string_agg(version_num, ',') from alembic_version) as alembic"
  q "bom_sections 83, 84, 85 (must be gone) and 26, 15, 21 (must exist)" \
    "select id, name, sort_order, multiplier, is_optional, archived_at from bom_sections where id in (83,84,85,26,15,21) order by id"
  q "lines naming 83 / 84 / 85 by id or by string (must be 0)" \
    "select count(*) as lines from bill_of_materials where bom_section_id in (83,84,85)
        or bom_section in ('DOOR FITTINGS SRD', 'DOOR FITTINGS DRD', 'REAR FRAME + FLOOR PLATE')"
  q "drafts naming them as a key (must be 0)" \
    "select count(*) as drafts from configurator_drafts where payload like '%\"DOOR FITTINGS SRD\"%'
        or payload like '%\"DOOR FITTINGS DRD\"%' or payload like '%\"REAR FRAME + FLOOR PLATE\"%'"
  q "MANNI DF's 7 lines (Manifest S1: 793-796 on 64, 843-845 on 65)" \
    "select id, trailer_type_id, bom_section_id, bom_section from bill_of_materials where id in (793,794,795,796,843,844,845) order by id"
  q "deleted id 41's 39 Manifest S2 lines by section (26 x 17, 15 x 13, 21 x 9)" \
    "select bom_section_id, bom_section, count(*) from bill_of_materials where trailer_type_id = 41
        and (id between 11113 and 11129 or id between 11134 and 11146 or id between 11192 and 11200) group by 1, 2 order by 1"
  echo "== 2. /tmp clean-up (the RT4 kits; /var/backups is kept)"
  echo "-- before:"; ls -ld /tmp/icb-* /tmp/rt4-* 2>/dev/null
  # shellcheck disable=SC2086
  rm -rf $KIT
  echo "-- after:"; ls -ld /tmp/icb-* /tmp/rt4-* 2>/dev/null
  echo "-- kept:"; ls -l /var/backups/icb-rt4-2026-10/ /var/backups/postgres/icb_platform_pre-v1.60.1_* 2>/dev/null
  echo; echo "== done $(date -Is)"
} > "$OUT" 2>&1
chmod a+r "$OUT"
cat "$OUT"
rm -f "$0"
