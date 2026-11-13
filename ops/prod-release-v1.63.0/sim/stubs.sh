#!/bin/bash
# Stub executables for the v1.63.0 release simulation (RT12), written into $1 (a bin dir). State lives in $SIMSTATE:
#   live_code      the code the fake service is RUNNING (moves at restart) — the doors answer for that code
#   live_env       the ICB_ENVIRONMENT the running service read at its start (the restart reads /etc/icb/backend.env)
#   target         the v1.63.0 commit (the doors answer v1.63.0 only when it runs)
#   alembic        the schema head of the fake database (0053 throughout: v1.63.0 migrates nothing)
#   factor         the 4G factor's exact text;  quotes  the saved costings' "count md5";  dbname  the live database
#   saved3         flag: 3 costings were saved after the deploy (the count reads 75; three new row digests)
#   deleted        flag: one deploy-time row (1107, the repair) was soft-deleted after the deploy (its digest moves)
#   rt12rows       the fake calculations table for the kit's two row statements: `rt12rows rows` (id md5 per row) and
#                  `rt12rows name <ids>` (the allow-listed naming line per id, as the kit's SQL prints it)
#   pid aet mono   the fake service; journal = "epoch message" lines
#   absent_prev    "METHOD path" lines the OLD code lacks (none for v1.63.0)
#   cfcache/       Cloudflare's edge: the FIRST bytes it fetched for a /static or /mes-app/assets URL, kept and served
#   curl.log       every URL the kit asked for, in order ("METHOD url")
#   flags          cfstale, routeopen, fail_restart / fail_bootstrap / traceback, backup_no_calcs, fail_pgdump, npm_noop
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
           # the new code (RT10 #230) logs the letterhead gate at start-up: False while weasyprint is absent from the venv
           if [ "$(cat "$S/live_code")" = "$(cat "$S/target")" ]; then
             g=False; [ -f "$S/weasyprint" ] && g=True
             for i in 1 2 3 4; do echo "$now INFO:     Letterhead quote (Generate Quote) available: $g" >> "$S/journal"; done
           fi
           [ -f "$S/fail_bootstrap" ] && echo "$now ERROR BOOTSTRAP FAILED permission seeding" >> "$S/journal"
           if [ -f "$S/traceback" ]; then
             echo "$now Traceback (most recent call last):" >> "$S/journal"
             echo "$now   File \"/opt/icb-platform/backend/app/services/revisions.py\", line 115, in chain_info" >> "$S/journal"
             echo "$now KeyError: 'version'" >> "$S/journal"
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
while IFS= read -r line; do ep=${line%% *}; msg=${line#* }; [ "$msg" = "$line" ] && msg=''
  [ "$ep" -ge "$since" ] && [ "$ep" -le "$until" ] && echo "$(date -d @"$ep" '+%b %d %H:%M:%S') icb-mes-prod uvicorn[99877]: $msg"; done < "$S/journal"
exit 0
EOF

cat > "$B/curl" <<'EOF'
#!/bin/bash
# Static files and SPA assets come from DISK, as on prod — but Cloudflare's edge keeps the FIRST bytes it fetched for
# a /static or /mes-app/assets URL and serves them again (by URL, query included: that is why a ?v= bump works, and
# why asking for a new ?v= before the deploy would pin the OLD bytes under it; a rebuilt SPA bundle has a NEW name, so
# it is never served stale). The doors answer for the code the service RUNS and the environment it read at its
# start; a route the running code lacks answers 404; a GET to a POST-only route answers 405.
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
edge() { # $1 the file on disk: Cloudflare keeps the first bytes per URL
  if [ "$host" = mes.icecoldgrp.online ]; then
    mkdir -p "$S/cfcache"; c="$S/cfcache/$(printf '%s' "$path" | sha256sum | cut -c1-32)"
    [ -f "$c" ] || cp "$1" "$c"          # MISS: the edge fetches from the origin and keeps it
    file=$c
  else file=$1; fi
}
case "$path_noq" in
  /health) body='{"status":"ok"}' ;;
  /health/version)
    if [ $new = 1 ] && ! { [ -f "$S/cfstale" ] && [ "$host" = mes.icecoldgrp.online ]; }; then body="{\"version\":\"v1.63.0\",\"environment\":\"$env\"}"
    else body="{\"version\":\"v1.62.0\",\"environment\":\"$env\"}"; fi ;;
  /login)
    if [ "$env" != prod ]; then body="<html><head><title>[TEST] Login</title></head><body><div id=\"icb-test-banner\">TEST SERVER — $host — not prod</div></body></html>"
    else body='<html><head><title>Login</title></head><body>login</body></html>'; fi ;;
  /static/js/*|/static/css/*)
    f=/opt/icb-platform/backend/app${path_noq}
    if [ ! -f "$f" ]; then code=404; else edge "$f"; fi ;;
  /mes-app/assets/*)
    f=/opt/icb-platform/frontend/dist/${path_noq#/mes-app/}
    if [ ! -f "$f" ]; then code=404; else edge "$f"; fi ;;
  *)
    want=$(awk -v m="$method" -v p="$path" '!/^#/ && NF == 3 && $2 == m && $3 == p { print $1; exit }
                                           !/^#/ && NF == 2 && m == "GET" && $2 == p { print $1; exit }' /tmp/icb-release-v1.63.0/probe_paths.txt)
    if [ -z "$want" ] && [ "$method" = GET ] && awk -v p="$path" 'NF == 3 && $3 == p { f = 1 } END { exit !f }' /tmp/icb-release-v1.63.0/probe_paths.txt; then
      want=405                              # a GET to a route that only takes a body method
    fi
    code=${want:-404}
    # RT6_RULING_3: a route the RUNNING code lacks answers 404 (none for v1.63.0: absent_prev is empty)
    [ $new = 0 ] && grep -qxF -- "$method $path" "$S/absent_prev" 2>/dev/null && code=404
    # the negative control: an old route answering WITHOUT a session after the deploy
    [ $new = 1 ] && [ -f "$S/routeopen" ] && [ "$method $path" = "GET /api/calculations" ] && code=200 ;;
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
  # release.sh's three costings statements, most specific first: the per-row digests, the naming of given ids, the digest
  *"md5(c::text) from icb_costings.calculations c order by c.id"*) rt12rows rows ;;
  *split_part*"from icb_costings.calculations c where c.id in ("*)
    ids=${sql##*where c.id in (}; ids=${ids%%)*}; rt12rows name $(tr ',' ' ' <<< "$ids") ;;
  *"from icb_costings.calculations c"*)
    if [ -f "$S/saved3" ] || [ -f "$S/deleted" ]; then
      echo "$(rt12rows rows | wc -l) $(rt12rows rows | md5sum | cut -c1-32)"
    else cat "$S/quotes"; fi ;;
  *) echo "psql stub: unknown SQL: $sql"; exit 3 ;;
esac
EOF

cat > "$B/rt12rows" <<'EOF'
#!/bin/bash
# The fake icb_costings.calculations, as release.sh's two row statements read it. `rows` = "id md5" per row: the 72
# of the deploy, plus 3 N10022 revisions saved after it when saved3 is set, with row 1107 (the repair) changed when
# deleted is set. `name <ids>` = the allow-listed naming line per id, the shape the kit's SQL prints:
# id | quote (first word) | created (as stored) | version | status | deleted. The repair's quote number carries a
# (made-up) customer's name on prod: only its first word is ever printed.
S=$SIMSTATE; mode=${1:?rows|name}; shift
digest() { printf '%s' "$1" | md5sum | cut -c1-32; }
case "$mode" in
  rows)
    for i in $(seq 1 72); do id=$((1100 + i)); seed="row $id v1"
      [ $i = 7 ] && [ -f "$S/deleted" ] && seed="row $id v1 deleted"
      echo "$id $(digest "$seed")"; done
    if [ -f "$S/saved3" ]; then for v in 4 5 6; do echo "$((1234 + v)) $(digest "row $((1234 + v)) v$v")"; done; fi ;;
  name)
    for id in "$@"; do
      if [ "$id" -ge 1101 ] && [ "$id" -le 1172 ]; then
        i=$((id - 1100)); q="N100$(printf '%02d' $i)/10/2026"; [ $i = 7 ] && q="R-2003"
        del=N; [ $i = 7 ] && [ -f "$S/deleted" ] && del=Y
        echo "$id | $q | 2026-10-$(printf '%02d' $(( (i % 20) + 1 ))) 09:00:$(printf '%02d' $((i % 60))) | 1 | pending | $del"
      elif [ "$id" -ge 1238 ] && [ "$id" -le 1240 ]; then
        v=$((id - 1234)); echo "$id | N10022/10/2026 | 2026-10-22 13:0$((v - 2)):10 | $v | pending | N"
      fi
    done ;;
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
# `pg_restore -l <dump>` (the backup helper's check): the dump's table-of-contents lines
echo ";"
for t in alembic_version admin_settings trailer_types bill_of_materials materials; do echo "5001; 0 0 TABLE DATA icb_costings $t icb_app"; done
[ -f "$SIMSTATE/backup_no_calcs" ] || echo "5009; 0 0 TABLE DATA icb_costings calculations icb_app"
EOF

cat > "$B/npm" <<'EOF'
#!/bin/bash
# v1.63.0 changes frontend/: icb-deploy.sh runs `npm run build` as icb once (recorded; the sim reports the count). The
# stub writes a NEW bundle (a new name, as vite does) carrying RT10's text when the checked-out source carries it —
# the kit's SPA_MARK checks then read the real guard. With npm_noop set the build does nothing (the negative control:
# the kit's SPA_REBUILT must stop).
echo "(stub) npm $*" >> "$SIMSTATE/npm.log"
[ -f "$SIMSTATE/npm_noop" ] && { echo "(stub) npm: did nothing"; exit 0; }
d=/opt/icb-platform/frontend/dist
n="index-RT12$(date +%s)"
mark=$(sed -n 's/^SPA_MARK="\(.*\)"$/\1/p' /tmp/icb-release-v1.63.0/expected.env 2>/dev/null)
{ echo 'console.log("rebuilt")'
  [ -n "$mark" ] && grep -rqF -- "$mark" /opt/icb-platform/frontend/src && echo "console.log(\"$mark\")"; } > "$d/assets/$n.js"
echo "<script type=\"module\" src=\"/mes-app/assets/$n.js\"></script>" > "$d/index.html"
EOF
chmod +x "$B"/*
