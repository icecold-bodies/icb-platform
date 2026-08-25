#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# v1.51 - one-off PROD heal: strip R-2001 / R-2002 back to a plain R-number.
#
# WHY. Through v1.50 the repair document number was minted from an admin
# template that embedded {customer} and {vehicle_registration}, so the two
# quotes Lezette test-drove carry their whole identity INSIDE the number:
#
#     R-2002 Karan Beef Farming (Pty) Ltd KK 12 LT GP
#
# That is what overprinted the Document Date on the quotation, and it is what
# the acceptance form quotes back as the Quote Ref. Michael has reverted the
# template to R-{counter}, which fixes every FUTURE repair; these two rows were
# already issued and are immutable by design (D6), so they need a data heal.
#
# WHAT IT TOUCHES. Exactly the two rows it finds and prints for you first, in
# the two JSON paths the number lives in. Nothing else - no counter, no
# template, no other costing. It refuses to run unless it finds exactly one row
# for R-2001 and exactly one for R-2002.
#
# HOW TO RUN (on the VM, as a user who can reach the DB):
#
#     bash heal_repair_doc_numbers_v1_51.sh            # DRY RUN - shows the plan
#     APPLY=1 bash heal_repair_doc_numbers_v1_51.sh    # writes, after a backup
#
# Dry run is the default on purpose: read what it says it will do, THEN run it
# with APPLY=1. A backup of both rows' full result_json is written before any
# write and its path is printed, with the exact command to roll back.
# ---------------------------------------------------------------------------
set -u -o pipefail

# prod is `icb_platform`, NOT the dev name `icb`. Override if you must.
DB="${DB:-icb_platform}"
PSQL_BIN="${PSQL_BIN:-psql}"
BACKUP_DIR="${BACKUP_DIR:-/tmp}"
APPLY="${APPLY:-0}"

TABLE="icb_costings.calculations"
# The number lives at BOTH of these paths on the same row.
DOCNO="coalesce(result_json::jsonb ->> 'repair_document_number', result_json::jsonb -> 'input_state' ->> 'repair_document_number')"

psql_q() { "$PSQL_BIN" -d "$DB" -v ON_ERROR_STOP=1 -qAt -c "$1"; }

stop() { printf '\n  x STOP: %s\n  Nothing further was changed.\n' "$*"; exit 1; }
ok()   { printf '  . %s\n' "$*"; }

echo "==================================================================="
echo " v1.51 repair document number heal  .  DB=$DB  .  APPLY=$APPLY"
echo "==================================================================="

# -- 1. anchors -------------------------------------------------------------
command -v "$PSQL_BIN" >/dev/null 2>&1 || stop "psql not found (set PSQL_BIN=/path/to/psql)"

WHOAMI="$(psql_q "select current_database()")" || stop "cannot connect to '$DB'"
[ "$WHOAMI" = "$DB" ] || stop "connected to '$WHOAMI', expected '$DB'"
ok "connected to $WHOAMI"

TBL="$(psql_q "select to_regclass('$TABLE')")"
[ -n "$TBL" ] || stop "$TABLE does not exist - wrong database?"
ok "table $TABLE found"

# A check that returns nothing is meaningless until it is shown able to return
# something: this proves the JSON paths are readable before anything is judged
# by them, and its value is re-asserted at the end.
CANARY="$(psql_q "select count(*) from $TABLE where is_repair is true and result_json is not null and $DOCNO is not null")"
[ "${CANARY:-0}" -gt 0 ] || stop "no repair carries a document number at all - refusing to guess"
ok "$CANARY repair costings carry a document number"

# -- 2. find EXACTLY the two rows ------------------------------------------
# Matched on the SHAPE of the defect (an R-number with anything after it), never
# on a hardcoded id: ids differ between environments and a wrong one would heal
# a stranger's quote.
declare -A TARGET_ID
declare -A TARGET_NOW
for n in 2001 2002; do
  ROWS="$(psql_q "select id || '|' || $DOCNO from $TABLE where is_repair is true and $DOCNO like 'R-$n %' order by id")" \
    || stop "query failed for R-$n"
  COUNT="$(printf '%s' "$ROWS" | grep -c . || true)"
  if [ "$COUNT" != "1" ]; then
    stop "expected exactly 1 row for R-$n, found $COUNT.
     0 means it is already healed (or the number never carried a suffix);
     2+ means something else matches and this script must not choose."
  fi
  TARGET_ID[$n]="${ROWS%%|*}"
  TARGET_NOW[$n]="${ROWS#*|}"
  ok "R-$n  ->  id=${TARGET_ID[$n]}"
  printf '        now: [%s]\n' "${TARGET_NOW[$n]}"
  printf '        new: [R-%s]\n' "$n"
done

if [ "$APPLY" != "1" ]; then
  printf '\n  DRY RUN - nothing written.\n  Re-run with APPLY=1 to make the two changes above.\n'
  exit 0
fi

# -- 3. back both rows up BEFORE touching them -----------------------------
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_DIR/icb-repair-docnum-heal-$STAMP.sql"
"$PSQL_BIN" -d "$DB" -v ON_ERROR_STOP=1 -qAt \
  -c "select 'UPDATE $TABLE SET result_json = ' || quote_literal(result_json) || ' WHERE id = ' || id || ';' from $TABLE where id in (${TARGET_ID[2001]}, ${TARGET_ID[2002]})" \
  > "$BACKUP" || stop "could not write the backup - refusing to change anything"
[ -s "$BACKUP" ] || stop "the backup came out empty - refusing to change anything"
ok "backup written: $BACKUP  ($(wc -l < "$BACKUP") rollback statements)"
printf '        to roll back:  psql -d %s -f %s\n' "$DB" "$BACKUP"

# -- 4. the guarded update --------------------------------------------------
# The exact value read in step 2 is passed as a psql variable and used in the
# WHERE, so if anything changed the row since (another deploy, a re-save, a
# second operator) this updates 0 rows and says so, rather than overwriting work
# it never saw. The value is never interpolated into SQL text - psql quotes the
# variable itself - so an apostrophe in a customer name cannot break out.
for n in 2001 2002; do
  CHANGED="$("$PSQL_BIN" -d "$DB" -v ON_ERROR_STOP=1 -qAt \
    -v now="${TARGET_NOW[$n]}" -v want="R-$n" -v rid="${TARGET_ID[$n]}" \
    -f /dev/stdin <<SQL | head -1
with upd as (
  update $TABLE
     set result_json = jsonb_set(
           jsonb_set(result_json::jsonb,
                     '{repair_document_number}', to_jsonb(:'want'::text), true),
           '{input_state,repair_document_number}', to_jsonb(:'want'::text), true
         )::text
   where id = :rid
     and $DOCNO = :'now'
  returning 1)
select count(*) from upd;
SQL
)"
  # NB -qAt on a DML+RETURNING statement appends the command tag on its own
  # line; head -1 keeps the count and drops it (v1.50 lesson).
  if [ "${CHANGED:-0}" != "1" ]; then
    stop "R-$n updated ${CHANGED:-0} rows, expected 1 - the stored value changed
     since it was read. Nothing further was attempted; anything already changed
     restores with:  psql -d $DB -f $BACKUP"
  fi
  ok "R-$n updated"
done

# -- 5. verify from the DATABASE, not from the update ----------------------
FAILED=0
for n in 2001 2002; do
  TOP="$(psql_q "select result_json::jsonb ->> 'repair_document_number' from $TABLE where id = ${TARGET_ID[$n]}")"
  IN="$(psql_q "select result_json::jsonb -> 'input_state' ->> 'repair_document_number' from $TABLE where id = ${TARGET_ID[$n]}")"
  if [ "$TOP" = "R-$n" ] && [ "$IN" = "R-$n" ]; then
    ok "verified id=${TARGET_ID[$n]}: both paths read R-$n"
  else
    printf '  x id=%s: top=[%s] input_state=[%s] (expected [R-%s])\n' "${TARGET_ID[$n]}" "$TOP" "$IN" "$n"
    FAILED=1
  fi
done

# Nothing else may have moved while this ran.
STILL="$(psql_q "select count(*) from $TABLE where is_repair is true and result_json is not null and $DOCNO is not null")"
if [ "$STILL" != "$CANARY" ]; then
  printf '  x the count of numbered repairs moved: %s -> %s\n' "$CANARY" "$STILL"
  FAILED=1
fi

printf '\n'
if [ "$FAILED" = "0" ]; then
  echo "  DONE - R-2001 and R-2002 now carry a plain R-number."
  echo "  Re-download either quotation: the header and the acceptance form"
  echo "  should both read R-2001 / R-2002 and nothing more."
else
  stop "verification failed - restore with:  psql -d $DB -f $BACKUP"
fi
