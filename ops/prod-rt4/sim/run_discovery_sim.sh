#!/bin/bash
# rt4_discovery.sh simulation, run as root in WSL:  bash run_discovery_sim.sh [branch]
# The REAL rt4_discovery.sh + mkstage_discovery.sh in a private mount namespace (fake /opt, /etc, /tmp); psql, curl
# and the prod-only python steps are stubs (the real rt4_discovery.py ran read-only against the prod mirror; the
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
bash ops/prod-rt4/mkstage_discovery.sh "$SIM/stageout" HEAD > "$SIM/stage.log" 2>&1 || { cat "$SIM/stage.log"; exit 1; }
head -n 1 "$SIM/stage.log"
tar -xf "$SIM/stageout/icb-rt4-discovery.tar" -C "$SIM/tmp" || exit 1
PROD=$(git rev-parse "v1.60.0^{commit}")
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "refs/tags/v1.60.0:refs/tags/v1.60.0" \
  && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD" || exit 1
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'PY'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "python stub: NOT read-only"; exit 3;; esac
case "$1" in
  */rt4_discovery.py)
    cat "$SIMSTATE/discovery.json" > "$3/discovery.json"; echo "== 1 · bodies named MANNI (stub)" | tee "$3/discovery.txt"; exit 0 ;;
  -c) case "$2" in *"print(t.__file__)"*) echo "$PWD/tools/costing_audit/__init__.py"; exit 0 ;; esac ;;
  -) case "$2" in */manni_snapshot.json) if [ $# -eq 3 ]; then cat > /dev/null; echo '{"tables": {"trailer_types": [{"id": 3, "name": "MANNI RIGIDS CB"}]}}' > "$2"; echo "[snapshot] stub"; exit 0; fi ;; esac ;;
esac
exec python3 "$@"
PY
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb" && echo 'DATABASE_URL=postgresql+psycopg://x:y@localhost/icb_platform' > "$SIM/etc/icb/backend.env"
echo 0051 > "$SIM/state/alembic"
FIVE='{"bodies": [{"id": 3, "name": "MANNI RIGIDS CB"}, {"id": 4, "name": "MANNI BAKKI RIGIDS"}, {"id": 5, "name": "MANNI RIGIDS FB"}, {"id": 6, "name": "MANNI TRAILERS"}, {"id": 7, "name": "MANNI DF"}, {"id": 41, "name": "Manni RIGIDS CB [deleted-41]"}]}'
echo "$FIVE" > "$SIM/state/discovery.json"
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
          export PATH='$SIM/bin':\$PATH SIMSTATE='$SIM/state' ${EXTRA:-} && bash /tmp/icb-rt4-discovery/rt4_discovery.sh" > "$SIM/last.log" 2>&1
        grep -E '^######## (STOP|DONE)' "$SIM/last.log" | head -n 1; }
P=0; F=0
expect() { local got; got=$(run); if [[ "$got" =~ $2 ]]; then echo "PASS  $1 :: $got"; P=$((P+1)); else echo "FAIL  $1 :: $got"; F=$((F+1)); sed 's/^/   | /' "$SIM/last.log" | tail -n 12; fi; }

expect "over v1.60.0"              'DONE'
T=$(ls -t "$SIM/tmp/icb-rt4-discovery/"out-*.tar | head -n1)
grep -q 'gate ok: test_snapshot_has_no_email_addresses' "$SIM/last.log" && grep -q 'ids: 4,7,3,5,6' "$SIM/last.log" \
  && echo "PASS  export ran with the five ids + the real no-people gate" && P=$((P+1)) || { echo "FAIL  export / gate"; F=$((F+1)); }
N=$(grep -vc '^#' "$SIM/tmp/icb-rt4-discovery/noauth_probe_paths.txt"); C=$(wc -l < "$SIM/state/curl.log")
[ "$C" = $((N * 3)) ] && echo "PASS  probe: $N paths x 3 doors = $C GETs" && P=$((P+1)) || { echo "FAIL  probe: $C GETs for $N paths"; F=$((F+1)); }
tar -tf "$T" | grep -q 'noauth_probe.txt' && tar -tf "$T" | grep -q 'manni_snapshot.json' && echo "PASS  the output tar carries the files" && P=$((P+1)) || { echo "FAIL  tar"; F=$((F+1)); }
echo '{"bodies": [{"id": 3, "name": "MANNI RIGIDS CB"}]}' > "$SIM/state/discovery.json"
expect "Manni names missing -> export skipped, still DONE" 'DONE'
grep -q 'SKIPPED: the five Manni names' "$SIM/last.log" && echo "PASS  skip message" && P=$((P+1)) || { echo "FAIL  skip message"; F=$((F+1)); }
echo "$FIVE" > "$SIM/state/discovery.json"
echo 0050 > "$SIM/state/alembic"
expect "alembic not 0051"          'STOP \[DB\]'
echo 0051 > "$SIM/state/alembic"
EXTRA="RT4_DISCOVERY_TEST_IDS=15" expect "test seam set"   'STOP \[KIT\]'
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved"           'STOP \[CODE\]'
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD"
echo x >> "$SIM/tmp/icb-rt4-discovery/rt4_discovery.py"
expect "tampered kit"              'STOP \[KIT\]'
echo "== $P passed, $F failed · SIM=$SIM"
