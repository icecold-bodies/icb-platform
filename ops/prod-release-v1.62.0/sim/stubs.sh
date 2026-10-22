#!/bin/bash
# Stub executables for the v1.62.0 release simulation (RT9), written into $1 (a bin dir). State lives in $SIMSTATE:
#   live_code      the code the fake service is RUNNING (moves at restart) — the doors answer for that code
#   live_env       the ICB_ENVIRONMENT the running service read at its start (the restart reads /etc/icb/backend.env)
#   target         the v1.62.0 commit (the doors answer v1.62.0 and carry the new route only when it runs)
#   alembic        the schema head of the fake database (0053 throughout: v1.62.0 migrates nothing)
#   factor         the 4G factor's exact text;  quotes  the saved costings' "count md5";  dbname  the live database
#   saved3         flag: 3 costings were saved after the deploy (the count reads 75, the digest moves; the live COPY
#                  stream carries 3 more rows than the backup's)
#   changed        flag: one deploy-time row changed too (the repair's contact_name, in the live stream only)
#   rt9rows        the fake calculations table in COPY text format, shared by the pg_restore (the backup) and psql
#                  (the live rows) stand-ins: `rt9rows cols | dump | now`
#   pid aet mono   the fake service; journal = "epoch message" lines
#   absent_prev    "METHOD path" lines the OLD code lacks (the gate answers 404 there)
#   cfcache/       Cloudflare's edge: the FIRST bytes it fetched for a /static URL, kept and served again (4 h)
#   curl.log       every URL the kit asked for, in order ("METHOD url")
#   flags          cfstale, routeopen, fail_restart / fail_bootstrap / traceback, backup_no_calcs, fail_pgdump
B=$1; mkdir -p "$B"

cat > "$B/sudo" <<'EOF'
#!/bin/bash
while [ $# -gt 0 ]; do case "$1" in -u) shift 2;; -v) exit 0;; -n|-E|-H) shift;; -*) shift;; *) break;; esac; done
[ $# -eq 0 ] && exit 0
exec "$@"
EOF

cat > "$B/systemctl" <<'EOF'
#!/bin/bash
S=$SIMSTATE
case "$1" in
  show) prop=; while [ $# -gt 0 ]; do [ "$1" = -p ] && prop=$2; shift; done
        case "$prop" in MainPID) cat "$S/pid";; ActiveEnterTimestamp) cat "$S/aet";; ActiveEnterTimestampMonotonic) cat "$S/mono";; esac ;;
  restart) [ -f "$S/fail_restart" ] && { echo "Job for icb-backend.service failed" >&2; exit 1; }
           sleep 1
           echo $(( $(cat "$S/pid") + 7 )) > "$S/pid"; date '+%a %Y-%m-%d %H:%M:%S SAST' > "$S/aet"
           awk '{ printf "%d\n", $1 * 1000000 }' /proc/uptime > "$S/mono"
           git -C /opt/icb-platform rev-parse HEAD > "$S/live_code"
           ( set -a; . /etc/icb/backend.env 2>/dev/null; printf '%s' "${ICB_ENVIRONMENT:-}" ) > "$S/live_env"
           now=$(date +%s); for i in 1 2 3 4; do echo "$now INFO:     Application startup complete." >> "$S/journal"; done
           [ -f "$S/fail_bootstrap" ] && echo "$now ERROR BOOTSTRAP FAILED permission seeding" >> "$S/journal"
           if [ -f "$S/traceback" ]; then
             echo "$now Traceback (most recent call last):" >> "$S/journal"
             echo "$now   File \"/opt/icb-platform/backend/app/routers/calculator.py\", line 1050, in api_reprice_preview" >> "$S/journal"
             echo "$now KeyError: 'saved_at'" >> "$S/journal"
           fi
           exit 0 ;;
  is-active) echo active ;;
  start) [ "$2" = icb-pg-backup.service ] && echo "$(date +%s) (stub) icb-pg-backup ran" >> "$S/pgbackup.log"; exit 0 ;;
  status) echo "   (stub) inactive (dead) — finished oneshot"; exit 3 ;;
esac
EOF

cat > "$B/journalctl" <<'EOF'
#!/bin/bash
S=$SIMSTATE; since=0; now=$(date +%s); until=$now
ep_of() { case "$1" in @*) echo "${1#@}" ;; now) echo "$now" ;; -*s) echo $(( now - ${1:1:${#1}-2} )) ;; "-2 min") echo $(( now - 120 )) ;;
          *) echo "journalctl stub: unsupported time '$1'" >&2; exit 2 ;; esac; }
while [ $# -gt 0 ]; do
  case "$1" in --since) since=$(ep_of "$2") || exit 2; shift ;; --until) until=$(ep_of "$2") || exit 2; shift ;; esac
  shift
done
while read -r ep msg; do [ "$ep" -ge "$since" ] && [ "$ep" -le "$until" ] && echo "$(date -d @"$ep" '+%b %d %H:%M:%S') icb uvicorn[77]: $msg"; done < "$S/journal"
exit 0
EOF

cat > "$B/curl" <<'EOF'
#!/bin/bash
# Static files come from DISK, as on prod — but Cloudflare's edge keeps the FIRST bytes it fetched for a /static URL
# and serves them again (by URL, query included: that is why a ?v= bump works, and why asking for the new ?v= before
# the deploy would pin the OLD bytes under it). The doors answer for the code the service RUNS and the environment it
# read at its start; a route the running code lacks answers 404; a GET to a POST-only route answers 405.
S=$SIMSTATE; out=; fmt=; url=; method=GET
while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift;; -w) fmt=$2; shift;; -X) method=$2; shift;; --data-binary|-d) [ "$method" = GET ] && method=POST; shift;;
  --max-time|-H) shift;; -*) ;; *) url=$1;; esac; shift; done
echo "$method $url" >> "$S/curl.log"
host=${url#https://}; host=${host%%/*}
path="/${url#https://*/}"; [ "$path" = "/$url" ] && path=/
path_noq=${path%%\?*}
new=0; [ "$(cat "$S/live_code")" = "$(cat "$S/target")" ] && new=1
env=$(cat "$S/live_env" 2>/dev/null); [ -n "$env" ] || env=unset
code=200; body='{}'; file=
case "$path_noq" in
  /health) body='{"status":"ok"}' ;;
  /health/version)
    if [ $new = 1 ] && ! { [ -f "$S/cfstale" ] && [ "$host" = mes.icecoldgrp.online ]; }; then body="{\"version\":\"v1.62.0\",\"environment\":\"$env\"}"
    else body="{\"version\":\"v1.61.1\",\"environment\":\"$env\"}"; fi ;;
  /login)
    if [ "$env" != prod ]; then body="<html><head><title>[TEST] Login</title></head><body><div id=\"icb-test-banner\">TEST SERVER — $host — not prod</div></body></html>"
    else body='<html><head><title>Login</title></head><body>login</body></html>'; fi ;;
  /static/js/*|/static/css/*)
    f=/opt/icb-platform/backend/app${path_noq}
    if [ ! -f "$f" ]; then code=404
    elif [ "$host" = mes.icecoldgrp.online ]; then
      mkdir -p "$S/cfcache"; c="$S/cfcache/$(printf '%s' "$path" | sha256sum | cut -c1-32)"
      [ -f "$c" ] || cp "$f" "$c"          # MISS: the edge fetches from the origin and keeps it
      file=$c
    else file=$f; fi ;;
  /mes-app/assets/*) f=/opt/icb-platform/frontend/dist/${path_noq#/mes-app/}; [ -f "$f" ] && file=$f || code=404 ;;
  *)
    want=$(awk -v m="$method" -v p="$path" '!/^#/ && NF == 3 && $2 == m && $3 == p { print $1; exit }
                                           !/^#/ && NF == 2 && m == "GET" && $2 == p { print $1; exit }' /tmp/icb-release-v1.62.0/probe_paths.txt)
    if [ -z "$want" ] && [ "$method" = GET ] && awk -v p="$path" 'NF == 3 && $3 == p { f = 1 } END { exit !f }' /tmp/icb-release-v1.62.0/probe_paths.txt; then
      want=405                              # a GET to a route that only takes a body method
    fi
    code=${want:-404}
    # RT6_RULING_3: a route the RUNNING code lacks answers 404 (v1.62.0 adds the reprice preview)
    [ $new = 0 ] && grep -qxF -- "$method $path" "$S/absent_prev" 2>/dev/null && code=404
    # the negative control: the new route answering WITHOUT a session after the deploy
    [ $new = 1 ] && [ -f "$S/routeopen" ] && [ "$method $path" = "POST /api/calculations/1/reprice-preview" ] && code=200 ;;
esac
if [ -n "$file" ]; then if [ -n "$out" ]; then cat "$file" > "$out"; else cat "$file"; fi
elif [ -n "$out" ]; then printf '%s' "$body" > "$out"; else printf '%s' "$body"; fi
[ -n "$fmt" ] && printf '%s' "$code"
exit 0
EOF

cat > "$B/psql" <<'EOF'
#!/bin/bash
# Answers exactly the read-only SQL the kits send; anything else is a loud failure.
S=$SIMSTATE; sql=
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT a read-only session" ; exit 3;; esac
while [ $# -gt 0 ]; do case "$1" in -c|-[A-Za-z]*c) sql=$2 ;; esac; shift; done   # -c, or combined like -XAtc
mig=$(cat "$S/alembic")
case "$sql" in
  *current_database*) cat "$S/dbname" 2>/dev/null || echo icb_platform ;;
  *alembic_version*) echo "$mig" ;;
  *pu_foam_4g_factor*) cat "$S/factor" ;;
  # the close's quotes check (rt9_quotes.sh): the database's zone, the live table's columns, the live rows as a COPY
  # stream (rt9rows now: the backup's 72, plus 3 with saved3, one changed with changed), and release.sh's digest
  *"show timezone"*) echo Africa/Johannesburg ;;
  *information_schema.columns*) rt9rows cols ;;
  *"copy (select * from icb_costings.calculations order by id) to stdout"*) rt9rows now ;;
  *"from icb_costings.calculations c"*) if [ -f "$S/saved3" ]; then echo "75 9cc317a694c80eb95b824d05b45c3f7b"; else cat "$S/quotes"; fi ;;
  *) echo "psql stub: unknown SQL: $sql"; exit 3 ;;
esac
EOF

cat > "$B/pg_dump" <<'EOF'
#!/bin/bash
f=; while [ $# -gt 0 ]; do [ "$1" = -f ] && f=$2; shift; done
[ -f "$SIMSTATE/fail_pgdump" ] && { echo "pg_dump: error: connection to server failed" >&2; exit 1; }
{ echo PGDMP; head -c 4096 /dev/urandom; } > "$f"
echo "$(cat "$SIMSTATE/alembic")" > "$SIMSTATE/backup_at_alembic"
EOF

cat > "$B/pg_restore" <<'EOF'
#!/bin/bash
# `pg_restore -l <dump>` (the backup helper's check), or `pg_restore --data-only -n icb_costings -t calculations -f -
# <dump>` (the close's quotes check): the backup's costings as a pg_restore script — one COPY block, the shape the real
# pg_restore writes. The dump file must exist (the stub never reads it: its 72 rows are rt9rows' fixture).
case " $* " in
  *" --data-only "*)
    f=${*: -1}; [ -f "$f" ] || { echo "pg_restore: error: could not open input file \"$f\"" >&2; exit 1; }
    echo "--"; echo "-- PostgreSQL database dump (stub)"; echo "--"; echo "SET statement_timeout = 0;"
    echo "SELECT pg_catalog.set_config('search_path', '', false);"; echo
    echo "COPY icb_costings.calculations ($(rt9rows cols | sed 's/,/, /g')) FROM stdin;"
    rt9rows dump; echo '\.'; echo; echo "-- PostgreSQL database dump complete"; exit 0 ;;
esac
echo ";"
for t in alembic_version admin_settings trailer_types bill_of_materials materials; do echo "5001; 0 0 TABLE DATA icb_costings $t icb_app"; done
[ -f "$SIMSTATE/backup_no_calcs" ] || echo "5009; 0 0 TABLE DATA icb_costings calculations icb_app"
EOF

cat > "$B/rt9rows" <<'EOF'
#!/bin/bash
# The fake icb_costings.calculations in COPY text format (tab-separated, \N = null), the few columns the close's
# filter needs plus two it must NEVER print (contact_name, customer_id). `dump` = the backup's 72 rows; `now` = the
# same 72 byte for byte, plus 3 N10022 revisions saved after the deploy when saved3 is set (v1.62.0's "Save as Rev."),
# and the repair row 1107's contact_name changed when `changed` is set. Row 1107 is a repair whose quote number
# carries a (made-up) customer's name, as prod's do: the filter prints its first word only.
S=$SIMSTATE; mode=${1:?cols|dump|now}
[ "$mode" = cols ] && { echo "id,quote_number,created_at,status,deleted_at,net_total,result_json,contact_name,customer_id"; exit 0; }
row() { printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$@"; }
for i in $(seq 1 72); do
  id=$((1100 + i)); q="N100$(printf '%02d' $i)/10/2026"; contact="Person $i"
  [ $i = 7 ] && q="R-2003 Example Farming (Pty) Ltd 001 ICB GP"
  [ "$mode" = now ] && [ -f "$S/changed" ] && [ $i = 7 ] && contact="Changed Person 7"
  row "$id" "$q" "2026-10-$(printf '%02d' $(( (i % 20) + 1 ))) 09:00:$(printf '%02d' $((i % 60)))" pending '\N' "$((100000 + i)).00" \
      "{\"version\": 1, \"grand_total\": $((120000 + i)).5, \"customer_name\": \"Never Printed $i\"}" "$contact" "$i"
done
if [ "$mode" = now ] && [ -f "$S/saved3" ]; then
  for v in 4 5 6; do
    row "$((1234 + v))" "N10022/10/2026" "2026-10-22 13:0$((v - 2)):10" pending '\N' "389120.00" \
        "{\"version\": $v, \"grand_total\": 389120.0, \"repriced\": {\"from_version\": 1}, \"customer_name\": \"Never Printed 22\"}" "Person 22" 22
  done
fi
EOF

cat > "$B/npm" <<'EOF'
#!/bin/bash
# v1.62.0 changes nothing under frontend/: npm must never run on a fresh deploy. If it does, it is recorded (the sim
# reports the count) and it REWRITES the bundle, so the kit's SPA_UNCHANGED check would catch it too.
echo "(stub) npm $*" >> "$SIMSTATE/npm.log"
d=/opt/icb-platform/frontend/dist
n="index-RT9$(date +%s)"
echo 'console.log("rebuilt")' > "$d/assets/$n.js"
echo "<script type=\"module\" src=\"/mes-app/assets/$n.js\"></script>" > "$d/index.html"
EOF
chmod +x "$B"/*
