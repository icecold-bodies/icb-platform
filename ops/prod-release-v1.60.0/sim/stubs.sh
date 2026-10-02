#!/bin/bash
# Stub executables for the v1.60.0 release simulation, written into $1 (a bin dir). State lives in $SIMSTATE:
#   alembic        the schema head the fake database is at (0050 -> 0051 by the alembic stub's `upgrade`)
#   groups         the trailer_groups list the fake database reads (the 'groupseeded' flag adds one at restart)
#   pid aet mono   the fake service; journal = "epoch message" lines
#   calc_prev.js   served instead of the disk's calculator.js when the 'stalecache' flag is set
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
           if [ -f "$S/groupseeded" ]; then   # the OLD bootstrap's defect: a group comes back at restart
             echo "$now Seeded TrailerGroup: MEATHANGER (id=9)" >> "$S/journal"
             echo "$(cat "$S/groups") 9:MEATHANGER:3" > "$S/groups"
           fi
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
# Static files come from DISK (StaticFiles reads them per request), as on prod; 'stalecache' serves the previous
# calculator.js under any ?v= (a cache that kept old bytes).
S=$SIMSTATE; out=; fmt=; url=
while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift;; -w) fmt=$2; shift;; --max-time) shift;; -*) ;; *) url=$1;; esac; shift; done
path="/${url#https://*/}"; path_noq=${path%%\?*}
code=200; body=; file=
case "$path_noq" in
  /health) body='{"status":"ok"}' ;;
  /static/js/calculator.js) if [ -f "$S/stalecache" ]; then file=$S/calc_prev.js; else file=/opt/icb-platform/backend/app/static/js/calculator.js; fi ;;
  /static/js/*|/static/css/*) f=/opt/icb-platform/backend/app${path_noq}; [ -f "$f" ] && file=$f || code=404 ;;
  /mes-app/assets/*) f=/opt/icb-platform/frontend/dist/${path_noq#/mes-app/}; [ -f "$f" ] && file=$f || code=404 ;;
  /openapi.json) body="{\"openapi\": \"3.1.0\", \"live\": \"$(cat "$S/live_code")\"}" ;;
  *) code=404 ;;
esac
if [ -n "$file" ]; then if [ -n "$out" ]; then cat "$file" > "$out"; else cat "$file"; fi
elif [ -n "$out" ]; then printf '%s' "$body" > "$out"; else printf '%s' "$body"; fi
[ -n "$fmt" ] && printf '%s' "$code"
exit 0
EOF

cat > "$B/psql" <<'EOF'
#!/bin/bash
# Answers exactly the read-only SQL release.sh sends; anything else is a loud failure (so a new query cannot pass
# unnoticed). The 0051 columns exist once the alembic stub has upgraded.
S=$SIMSTATE; sql=
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT a read-only session" ; exit 3;; esac
while [ $# -gt 0 ]; do [ "$1" = -c ] && sql=$2; shift; done
mig=$(cat "$S/alembic")
case "$sql" in
  *current_database*) echo icb_platform ;;
  *alembic_version*) echo "$mig" ;;
  *"select string_agg(column_name"*) [ "$mig" = 0051 ] && echo "colour:character varying:7:YES:NULL sort_order:integer:-:NO:100" ;;
  *"select count(*) from information_schema.columns"*trailer_groups*) [ "$mig" = 0051 ] && echo 2 || echo 0 ;;
  *ck_trailer_groups_colour*) [ "$mig" = 0051 ] && echo 1 || echo 0 ;;
  *"from icb_costings.trailer_groups where colour is not null"*) echo 0 ;;
  *"from icb_costings.trailer_groups"*) cat "$S/groups" ;;
  *"md5("*trailer_types*) echo 3f2c9a1b0d7e4c55aa66bb77cc88dd99 ;;
  *) echo "psql stub: unknown SQL: $sql"; exit 3 ;;
esac
EOF

cat > "$B/pg_dump" <<'EOF'
#!/bin/bash
f=; while [ $# -gt 0 ]; do [ "$1" = -f ] && f=$2; shift; done
[ -f "$SIMSTATE/fail_pgdump" ] && exit 1
{ echo PGDMP; head -c 4096 /dev/urandom; } > "$f"
echo "$(cat "$SIMSTATE/alembic")" > "$SIMSTATE/backup_at_alembic"
EOF

cat > "$B/pg_restore" <<'EOF'
#!/bin/bash
echo ";"
echo "5001; 0 0 TABLE DATA icb_costings alembic_version icb_app"
echo "5002; 0 0 TABLE DATA icb_costings trailer_types icb_app"
[ -f "$SIMSTATE/backup_no_groups" ] || echo "5003; 0 0 TABLE DATA icb_costings trailer_groups icb_app"
EOF

cat > "$B/npm" <<'EOF'
#!/bin/bash
# `npm run build` in frontend/: a new bundle that carries the family chip's field (the real build's output);
# 'nobuild' = the build silently produced nothing new.
echo "(stub) npm $*"
[ "$*" = "run build" ] || exit 0
[ -f "$SIMSTATE/nobuild" ] && exit 0
d=/opt/icb-platform/frontend/dist
rm -f "$d"/assets/index-*.js
echo 'const r={trailer_family:null};console.log("spa v1.60.0",r)' > "$d/assets/index-Rt3FaMly.js"
echo '<script type="module" src="/mes-app/assets/index-Rt3FaMly.js"></script>' > "$d/index.html"
EOF
chmod +x "$B"/*
