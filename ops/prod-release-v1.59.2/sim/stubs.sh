#!/bin/bash
# Stub executables for the v1.59.2 release simulation, written into $1 (a bin dir). State lives in $SIMSTATE.
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
           now=$(date +%s); for i in 1 2 3 4; do echo "$now INFO:     Application startup complete." >> "$S/journal"; done
           [ -f "$S/fail_bootstrap" ] && echo "$now ERROR BOOTSTRAP FAILED permission seeding" >> "$S/journal"
           [ -f "$S/traceback" ] && echo "$now Traceback (most recent call last):" >> "$S/journal"
           exit 0 ;;
  is-active) echo active ;;
  start) exit 0 ;;
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
S=$SIMSTATE; out=; fmt=; url=
while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift;; -w) fmt=$2; shift;; --max-time) shift;; -*) ;; *) url=$1;; esac; shift; done
path="/${url#https://*/}"; path_noq=${path%%\?*}
code=200; body=; file=
case "$path_noq" in
  /health) body='{"status":"ok"}' ;;
  /static/js/calculator.js) if [ -f "$S/stalecache" ]; then file=$S/calc_prev.js; else file=/opt/icb-platform/backend/app/static/js/calculator.js; fi ;;
  /mes-app/assets/*) f=/opt/icb-platform/frontend/dist/${path_noq#/mes-app/}; [ -f "$f" ] && file=$f || code=404 ;;
  /openapi.json) body='{"openapi": "3.1.0", "paths": {"/health": {}}}' ;;
  *) code=404 ;;
esac
if [ -n "$file" ]; then if [ -n "$out" ]; then cat "$file" > "$out"; else cat "$file"; fi
elif [ -n "$out" ]; then printf '%s' "$body" > "$out"; else printf '%s' "$body"; fi
[ -n "$fmt" ] && printf '%s' "$code"
exit 0
EOF

cat > "$B/psql" <<'EOF'
#!/bin/bash
S=$SIMSTATE; sql=
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT a read-only session" ; exit 3;; esac
while [ $# -gt 0 ]; do [ "$1" = -c ] && sql=$2; shift; done
case "$sql" in
  *current_database*) echo icb_platform ;;
  *alembic_version*) cat "$S/alembic" ;;
  *) echo "psql stub: unknown SQL: $sql"; exit 3 ;;
esac
EOF

cat > "$B/pg_dump" <<'EOF'
#!/bin/bash
f=; while [ $# -gt 0 ]; do [ "$1" = -f ] && f=$2; shift; done
[ -f "$SIMSTATE/fail_pgdump" ] && exit 1
{ echo PGDMP; head -c 4096 /dev/urandom; } > "$f"
EOF

cat > "$B/pg_restore" <<'EOF'
#!/bin/bash
echo ";"; echo "5001; 0 0 TABLE DATA icb_costings alembic_version icb_app"; echo "5002; 0 0 TABLE DATA icb_costings bill_of_materials icb_app"
EOF
chmod +x "$B"/*
