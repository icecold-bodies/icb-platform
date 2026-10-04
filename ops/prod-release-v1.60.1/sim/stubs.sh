#!/bin/bash
# Stub executables for the v1.60.1 release simulation, written into $1 (a bin dir). State lives in $SIMSTATE:
#   live_code      the code the fake service is RUNNING (moves at restart) — the doors answer for that code:
#                  v1.60.0 = every probe path answers 200 and /health/version is 404; v1.60.1 = probe_paths.txt
#   pid aet mono   the fake service; journal = "epoch message" lines
#   flags          stalecache (old Body Templates script served), stillopen (one route stays open after the deploy),
#                  cfstale (the Cloudflare door still reports the old version), fail_restart / fail_bootstrap / traceback
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
while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift;; -w) fmt=$2; shift;; --max-time|-H) shift;; -*) ;; *) url=$1;; esac; shift; done
host=${url#https://}; host=${host%%/*}
path="/${url#https://*/}"; [ "$path" = "/$url" ] && path=/
path_noq=${path%%\?*}
new=0; [ "$(cat "$S/live_code")" = "$(cat "$S/target")" ] && new=1
code=200; body='{}'; file=
case "$path_noq" in
  /health) body='{"status":"ok"}' ;;
  /health/version)
    if [ $new = 1 ] && ! { [ -f "$S/cfstale" ] && [ "$host" = mes.icecoldgrp.online ]; }; then body='{"version":"v1.60.1"}'
    elif [ -f "$S/cfstale" ] && [ "$host" = mes.icecoldgrp.online ]; then body='{"version":"v1.60.0"}'
    else code=404; body='{"detail":"Not Found"}'; fi ;;
  /static/js/admin_templates.js)
    if [ -f "$S/stalecache" ]; then file=$S/stat_prev.js; else file=/opt/icb-platform/backend/app/static/js/admin_templates.js; fi ;;
  /mes-app/assets/*) f=/opt/icb-platform/frontend/dist/${path_noq#/mes-app/}; [ -f "$f" ] && file=$f || code=404 ;;
  *)
    if [ $new = 1 ]; then
      want=$(awk -v p="$path" '$2 == p { print $1; exit }' /tmp/icb-release-v1.60.1/probe_paths.txt)
      code=${want:-404}
      [ -f "$S/stillopen" ] && [ "$path" = /api/materials ] && code=200
    else
      code=200     # v1.60.0: the §3.0 list answered without a session
    fi ;;
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
echo ";"
echo "5001; 0 0 TABLE DATA icb_costings alembic_version icb_app"
echo "5002; 0 0 TABLE DATA icb_costings bill_of_materials icb_app"
echo "5003; 0 0 TABLE DATA icb_costings bom_sections icb_app"
[ -f "$SIMSTATE/backup_no_drafts" ] || echo "5004; 0 0 TABLE DATA icb_costings configurator_drafts icb_app"
EOF

cat > "$B/npm" <<'EOF'
#!/bin/bash
echo "(stub) npm $*"
EOF
chmod +x "$B"/*
