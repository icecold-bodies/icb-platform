#!/usr/bin/env bash
# RT9 close (RT9_RULING_2 Q1) — which costings were saved during the v1.62.0 window? READ ONLY. Staged by
# mkstage_close.sh at /tmp/icb-rt9-quotes; Michael runs it from his laptop line (run_quotes_check.ps1: ssh, then this
# file BY PATH under sudo):
#
#     sudo bash /tmp/icb-rt9-quotes/rt9_quotes.sh
#
# What it does, in order:
#   1. the deploy's CHECKED backup (release.sh step 5, 22 Oct 12:35:35): its size and sha256 read back against
#      expected.env (BACKUP, BACKUP_BYTES, BACKUP_SHA);
#   2. the saved costings' count + md5 now, beside the deploy's own (DEPLOY_COUNT DEPLOY_DIGEST): information only;
#   3. the backup STREAMED (pg_restore --data-only, never restored: no database is created and nothing is extracted
#      to disk — it goes straight down a pipe) against the live rows (a read-only COPY TO STDOUT, the same pipe), row
#      by row, in rt9_quotes_filter.py: added, changed (the changed columns' NAMES only), removed, and every row
#      created today — printing only id, the quote number's FIRST WORD, created_at as stored, version, status,
#      soft-deleted Y/N and the totals. No customer, contact, user or rep column; nothing else from result_json.
# Every database session is read-only (PGOPTIONS default_transaction_read_only=on: a write would fail loudly). Writes
# only under /tmp/icb-rt9-quotes/out-*/ (run.log, rows.txt: allow-listed text). Deliberately no bare `set -e`.
set -u
BASE=/tmp/icb-rt9-quotes
KIT_DIR=$BASE
ICB_LANE=RT9
REPO=/opt/icb-platform
ENV_FILE=/etc/icb/backend.env
PY=$REPO/.venv/bin/python
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
stop() { echo; echo "######## STOP [$1]: $2"; echo "######## read only: nothing was changed. Tell the CA${OUT:+: $OUT}";
         [ -n "$OUT" ] && [ -d "$OUT" ] && chmod -R a+rX "$OUT"; exit 1; }
say() { echo "== $*"; }
# release.sh's own digest statement (the deploy recorded its answer), repeated here for the comparison line
QUOTES_SQL="select count(*) || ' ' || md5(coalesce(string_agg(md5(c::text), '' order by c.id), '')) from icb_costings.calculations c"

URL=''
if [ "$(id -u)" = 0 ] && [ -r "$ENV_FILE" ]; then
  URL=$( set -a; . "$ENV_FILE" >/dev/null 2>&1; printf '%s' "${DATABASE_URL:-}" )
  URL=${URL/postgresql+psycopg:/postgresql:}
fi
# shellcheck disable=SC1091
. "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT9 quotes check · machine $(hostname -s) · db ? · head ? · boot ?"; OUT=''; stop KIT "lib/icb_where.sh missing: copy the kit again"; }
# shellcheck disable=SC1091
. "$BASE/expected.env" 2>/dev/null || true
export PGOPTIONS='-c default_transaction_read_only=on'
icb_where "quotes check (read only)" "$REPO" "$URL"
OUT_TMP=$OUT; OUT=''
[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file and the backup are root-readable only)"
[ -n "$URL" ] || stop KIT "DATABASE_URL not found in $ENV_FILE"
for v in EXPECT_HEADS BACKUP BACKUP_BYTES BACKUP_SHA DEPLOY_COUNT DEPLOY_DIGEST DEPLOY_AT EXPECT_MACHINE EXPECT_DB EXPECT_DBHOST; do
  [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
done
icb_where_check || stop WHERE "$WHERE_WHY"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: copy the kit again"
OUT=$OUT_TMP
mkdir -p "$OUT" && chmod 700 "$OUT" || { OUT=''; stop KIT "cannot create $OUT_TMP"; }
exec > >(tee -a "$OUT/run.log") 2>&1
q() { psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "$1" 2>&1; }

say "1. the deploy's checked backup ($DEPLOY_AT): size and sha256 read back"
[ -f "$BACKUP" ] || stop BACKUP "$BACKUP is not there"
B_BYTES=$(stat -c %s "$BACKUP"); B_SHA=$(sha256sum "$BACKUP" | cut -d' ' -f1)
[ "$B_BYTES" = "$BACKUP_BYTES" ] && [ "$B_SHA" = "$BACKUP_SHA" ] \
  || stop BACKUP "$BACKUP reads $B_BYTES bytes sha256 ${B_SHA:0:16}, the deploy recorded $BACKUP_BYTES bytes ${BACKUP_SHA:0:16}"
echo "   ok   $BACKUP  $B_BYTES bytes  sha256 ${B_SHA:0:16}... = the deploy's"

say "2. the saved costings' count + md5 (every whole row): now, beside the deploy's"
NOW_DIGEST=$(q "$QUOTES_SQL") || stop DB "cannot read the costings: $NOW_DIGEST"
TZN=$(q "show timezone") || TZN='?'
echo "   at the deploy  $DEPLOY_COUNT $DEPLOY_DIGEST"
echo "   now            $NOW_DIGEST"
echo "   (created times below are as stored; the database's TimeZone setting is $TZN)"

say "3. the backup streamed (pg_restore --data-only, never restored) against the live rows (a read-only COPY), row by row"
COLS=$(q "select string_agg(column_name, ',' order by ordinal_position) from information_schema.columns where table_schema = 'icb_costings' and table_name = 'calculations'") \
  || stop DB "cannot read the table's columns: $COLS"
[ -n "$COLS" ] || stop DB "the live table has no columns?"
"$PY" -I "$BASE/rt9_quotes_filter.py" \
  --dump <(pg_restore --data-only -n icb_costings -t calculations -f - "$BACKUP") \
  --now <(psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "copy (select * from icb_costings.calculations order by id) to stdout") \
  --columns "$COLS" --deploy-count "$DEPLOY_COUNT" --today "$(date +%F)" > "$OUT/rows.txt" 2>&1; rc=$?
sed 's/^/   /' "$OUT/rows.txt"
( cd "$OUT" && sha256sum rows.txt > SHA256SUMS.out ) || true
chmod -R a+rX "$OUT"
case $rc in
  0) ;;
  3) stop BACKUP "$(tail -n1 "$OUT/rows.txt"): the backup is not the deploy's state — tell the CA" ;;
  *) stop FILTER "the comparison did not run (exit $rc): $(tail -n1 "$OUT/rows.txt")" ;;
esac
SUMMARY=$(sed -n 's/^SUMMARY: //p' "$OUT/rows.txt" | tail -n1)
[ -n "$SUMMARY" ] || stop FILTER "no SUMMARY line in the comparison's output"
echo; echo "######## DONE (read only): the backup compared row by row: ${SUMMARY#*; *; } — tell the CA: $OUT"; exit 0   # drops "backup N rows; now M rows; "
