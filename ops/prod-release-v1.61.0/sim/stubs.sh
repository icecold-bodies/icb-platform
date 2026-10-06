#!/bin/bash
# Stub executables for the v1.61.0 release simulation, written into $1 (a bin dir). State lives in $SIMSTATE:
#   live_code      the code the fake service is RUNNING (moves at restart) — the doors answer for that code
#   live_env       the ICB_ENVIRONMENT the running service read at its start (the restart reads /etc/icb/backend.env)
#   alembic        the schema head of the fake database (0052 -> 0053 by the alembic stub's `upgrade`)
#   pid aet mono   the fake service; journal = "epoch message" lines
#   flags          stalecache, cfstale, famchanged, fail_restart / fail_bootstrap / traceback, backup_no_calcs,
#                  fail_pgdump, nobuild (npm builds nothing)
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
           [ -f "$S/famchanged" ] && echo moved > "$S/families_moved"
           now=$(date +%s); for i in 1 2 3 4; do echo "$now INFO:     Application startup complete." >> "$S/journal"; done
           [ -f "$S/fail_bootstrap" ] && echo "$now ERROR BOOTSTRAP FAILED permission seeding" >> "$S/journal"
           [ -f "$S/traceback" ] && echo "$now Traceback (most recent call last):" >> "$S/journal"
           exit 0 ;;
  is-active) echo active ;;
  start) [ "$2" = icb-pg-backup.service ] && echo "$(date +%s) (stub) icb-pg-backup ran" >> "$S/pgbackup.log"; exit 0 ;;
  status) echo "   (stub) inactive (dead) — finished oneshot"; exit 3 ;;
esac
EOF

cat > "$B/journalctl" <<'EOF'
#!/bin/bash
S=$SIMSTATE; since=0; now=$(date +%s)
while [ $# -gt 0 ]; do
  if [ "$1" = --since ]; then
    v=$2
    case "$v" in
      @*) since=${v#@} ;;
      -*s) since=$(( now - ${v:1:${#v}-2} )) ;;
      "-2 min") since=$(( now - 120 )) ;;
      *) echo "journalctl stub: unsupported --since '$v'" >&2; exit 2 ;;
    esac
    shift
  fi
  shift
done
while read -r ep msg; do [ "$ep" -ge "$since" ] && echo "$(date -d @"$ep" '+%b %d %H:%M:%S') icb uvicorn: $msg"; done < "$S/journal"
exit 0
EOF

cat > "$B/curl" <<'EOF'
#!/bin/bash
# Static files come from DISK, as on prod. The doors answer for the code the service RUNS and the environment it read
# at its start: v1.60.2 has no banner and /health/version = {"version"}; v1.61.0 answers {"version","environment"} and
# puts the TEST bar on /login unless it started with ICB_ENVIRONMENT=prod.
S=$SIMSTATE; out=; fmt=; url=
while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift;; -w) fmt=$2; shift;; --max-time|-H) shift;; -*) ;; *) url=$1;; esac; shift; done
host=${url#https://}; host=${host%%/*}
path="/${url#https://*/}"; [ "$path" = "/$url" ] && path=/
path_noq=${path%%\?*}
new=0; [ "$(cat "$S/live_code")" = "$(cat "$S/target")" ] && new=1
env=$(cat "$S/live_env" 2>/dev/null); [ -n "$env" ] || env=unset
code=200; body='{}'; file=
case "$path_noq" in
  /health) body='{"status":"ok"}' ;;
  /health/version)
    if [ $new = 1 ] && ! { [ -f "$S/cfstale" ] && [ "$host" = mes.icecoldgrp.online ]; }; then body="{\"version\":\"v1.61.0\",\"environment\":\"$env\"}"
    else body='{"version":"v1.60.2"}'; fi ;;
  /login)
    if [ $new = 1 ] && [ "$env" != prod ]; then body="<html><head><title>[TEST] Login</title></head><body><div id=\"icb-test-banner\">TEST SERVER — $host — not prod</div></body></html>"
    else body='<html><head><title>Login</title></head><body>login</body></html>'; fi ;;
  /static/js/calculator.js)
    if [ -f "$S/stalecache" ]; then file=$S/calc_prev.js; else file=/opt/icb-platform/backend/app/static/js/calculator.js; fi ;;
  /static/js/*|/static/css/*) f=/opt/icb-platform/backend/app${path_noq}; [ -f "$f" ] && file=$f || code=404 ;;
  /mes-app/assets/*) f=/opt/icb-platform/frontend/dist/${path_noq#/mes-app/}; [ -f "$f" ] && file=$f || code=404 ;;
  *)
    want=$(awk -v p="$path" '$2 == p { print $1; exit }' /tmp/icb-release-v1.61.0/probe_paths.txt)
    code=${want:-404} ;;
esac
if [ -n "$file" ]; then if [ -n "$out" ]; then cat "$file" > "$out"; else cat "$file"; fi
elif [ -n "$out" ]; then printf '%s' "$body" > "$out"; else printf '%s' "$body"; fi
[ -n "$fmt" ] && printf '%s' "$code"
exit 0
EOF

cat > "$B/psql" <<'EOF'
#!/bin/bash
# Answers exactly the read-only SQL release.sh (and ops/lib/icb_where.sh) sends; anything else is a loud failure.
S=$SIMSTATE; sql=
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT a read-only session" ; exit 3;; esac
while [ $# -gt 0 ]; do [ "$1" = -c ] && sql=$2; shift; done
mig=$(cat "$S/alembic")
case "$sql" in
  *current_database*) cat "$S/dbname" 2>/dev/null || echo icb_platform ;;
  *alembic_version*) echo "$mig" ;;
  *"column_name = 'insulation_rule'"*) [ "$mig" = 0053 ] && echo "insulation_rule:text:YES:NULL" || echo none ;;
  *"where insulation_rule is not null"*) echo 0 ;;
  *"md5("*trailer_groups*) [ -f "$S/families_moved" ] && echo 0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f || echo 9a1b2c3d4e5f60718293a4b5c6d7e8f9 ;;
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
echo ";"
for t in alembic_version trailer_types trailer_groups bill_of_materials; do echo "5001; 0 0 TABLE DATA icb_costings $t icb_app"; done
[ -f "$SIMSTATE/backup_no_calcs" ] || echo "5009; 0 0 TABLE DATA icb_costings calculations icb_app"
EOF

cat > "$B/npm" <<'EOF'
#!/bin/bash
# `npm run build` in frontend/: a new bundle that carries the Accept refusal's sentence (the real build's output)
echo "(stub) npm $*" >> "$SIMSTATE/npm.log"
[ -f "$SIMSTATE/nobuild" ] && exit 0
d=/opt/icb-platform/frontend/dist
n="index-RT6$(date +%s)"
echo 'console.log("This costing cannot be accepted.")' > "$d/assets/$n.js"
echo "<script type=\"module\" src=\"/mes-app/assets/$n.js\"></script>" > "$d/index.html"
EOF
chmod +x "$B"/*
