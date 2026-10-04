#!/bin/bash
# rt4_export41.sh simulation, run as root in WSL:  bash run_export41_sim.sh [branch]
# The REAL rt4_export41.sh + mkstage_discovery.sh (kit export41) in a private mount namespace (fake /opt, /etc, /tmp); psql, curl
# and the prod-only python steps are stubs (the real rt4_export41.py ran read-only against the prod mirror; the
# exporter is the audit tool's own, as in RT2); the no-people gate and the id selection run for real; git is real.
set -u
BR=${1:-rt4/discovery}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt4simX-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout,state}
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
$G fetch -q "$WIN/icb-platform" "$BR" "refs/tags/v1.60.0:refs/tags/v1.60.0" && git -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
bash ops/prod-rt4/mkstage_discovery.sh "$SIM/stageout" HEAD export41 > "$SIM/stage.log" 2>&1 || { cat "$SIM/stage.log"; exit 1; }
head -n 1 "$SIM/stage.log"
tar -xf "$SIM/stageout/icb-rt4-export41.tar" -C "$SIM/tmp" || exit 1
PROD=$(git rev-parse "v1.60.0^{commit}")
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "refs/tags/v1.60.0:refs/tags/v1.60.0" \
  && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD" || exit 1
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'PY'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "python stub: NOT read-only"; exit 3;; esac
case "$1" in
  */rt4_export41.py)
    cat "$SIMSTATE/export41.json" > "$3/export41.json"; echo "lines in 83/84/85 (stub)" | tee "$3/export41.txt"; exit 0 ;;
  -c) case "$2" in *"print(t.__file__)"*) echo "$PWD/tools/costing_audit/__init__.py"; exit 0 ;; esac ;;
  -) case "$2" in */body41_snapshot.json) if [ $# -eq 2 ] && [ ! -e "$2" ]; then cat > /dev/null; echo '{"tables": {"trailer_types": [{"id": 41, "name": "Manni RIGIDS CB [deleted-41]"}]}}' > "$2"; echo "[snapshot] stub"; exit 0; fi ;; esac ;;
esac
exec python3 "$@"
PY
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb" && echo 'DATABASE_URL=postgresql+psycopg://x:y@localhost/icb_platform' > "$SIM/etc/icb/backend.env"
echo 0051 > "$SIM/state/alembic"

cat > "$SIM/bin/psql" <<'PS'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only"; exit 3;; esac
case "$*" in *current_database*) echo icb_platform ;; *alembic_version*) cat "$SIMSTATE/alembic" ;; *) exit 3 ;; esac
PS
cat > "$SIM/bin/curl" <<'CU'
#!/bin/bash
# GET only: refuse anything that is not a plain GET; write a header file; print "status bytes type"
h=""; url=""
while [ $# -gt 0 ]; do case "$1" in -D) h=$2; shift 2;; -X|--request|-d|--data*|-F|--form) echo "curl stub: NOT a GET" >&2; exit 9;; -w|-o|--max-time) shift 2;; -*) shift;; *) url=$1; shift;; esac; done
echo "$url" >> "$SIMSTATE/curl.log"
case "$url" in *mes.icecoldgrp.online*) printf 'HTTP/2 200\r\ncf-cache-status: DYNAMIC\r\n\r\n' > "$h" ;; *) printf 'HTTP/1.1 200 OK\r\n\r\n' > "$h" ;; esac
printf '200 10 application/json'
CU
chmod +x "$SIM/bin/psql" "$SIM/bin/curl"
run() { sleep 1; : > "$SIM/state/curl.log"
        unshare -m bash -c "mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/tmp' /tmp &&
          export PATH='$SIM/bin':\$PATH SIMSTATE='$SIM/state' ${EXTRA:-} && bash /tmp/icb-rt4-export41/rt4_export41.sh" > "$SIM/last.log" 2>&1
        grep -E '^######## (STOP|DONE)' "$SIM/last.log" | head -n 1; }
P=0; F=0
expect() { local got; got=$(run); if [[ "$got" =~ $2 ]]; then echo "PASS  $1 :: $got"; P=$((P+1)); else echo "FAIL  $1 :: $got"; F=$((F+1)); sed 's/^/   | /' "$SIM/last.log" | tail -n 12; fi; }
GOOD='{"lines": [{"bom_id": 1, "body_id": 41}], "draft41": {"payload": "{}"}}'
echo "$GOOD" > "$SIM/state/export41.json"
expect "over v1.60.0"              'DONE'
grep -q 'gate ok: test_snapshot_has_no_email_addresses' "$SIM/last.log" && grep -q 'gate ok: no email-shaped value in export41.json' "$SIM/last.log" \
  && echo "PASS  export + both gates" && P=$((P+1)) || { echo "FAIL  export / gates"; F=$((F+1)); }
T=$(ls -t "$SIM/tmp/icb-rt4-export41/"out-*.tar | head -n1)
tar -tf "$T" | grep -q 'export41.json' && tar -tf "$T" | grep -q 'body41_snapshot.json' && echo "PASS  the output tar carries the files" && P=$((P+1)) || { echo "FAIL  tar"; F=$((F+1)); }
[ ! -s "$SIM/state/curl.log" ] && echo "PASS  no HTTP request at all" && P=$((P+1)) || { echo "FAIL  curl was called"; F=$((F+1)); }
echo '{"draft41": {"payload": "{\"label\": \"ask jan.smit@example.co.za\"}"}}' > "$SIM/state/export41.json"
expect "email-shaped value"        'STOP \[GATE\]'
echo "$GOOD" > "$SIM/state/export41.json"
echo 0050 > "$SIM/state/alembic"
expect "alembic not 0051"          'STOP \[DB\]'
echo 0051 > "$SIM/state/alembic"
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved"           'STOP \[CODE\]'
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD"
echo x >> "$SIM/tmp/icb-rt4-export41/rt4_export41.py"
expect "tampered kit"              'STOP \[KIT\]'
echo "== $P passed, $F failed · SIM=$SIM"
