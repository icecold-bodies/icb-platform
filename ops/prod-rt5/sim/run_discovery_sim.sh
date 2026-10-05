#!/bin/bash
# rt5_discovery.sh simulation, run as root in WSL:  bash run_discovery_sim.sh [branch]
# The REAL rt5_discovery.sh + mkstage_discovery.sh in a private mount namespace (fake /opt, /etc, /tmp); psql and the
# prod-only python steps are stubs that refuse a session that is not read-only (the real rt5_discovery.py ran
# read-only against the prod mirror and dev; the audit run is the tool's own CLI, as in RT2/RT4); git is real.
# Cleans its own folder at the end (the RT4 disk lesson).
set -u
BR=${1:-rt5/discovery}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt5simD-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout,state}
trap 'rm -rf "$SIM"' EXIT
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
$G fetch -q "$WIN/icb-platform" "$BR" "refs/tags/v1.60.1:refs/tags/v1.60.1" && git -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
bash ops/prod-rt5/mkstage_discovery.sh "$SIM/stageout" HEAD > "$SIM/stage.log" 2>&1 || { cat "$SIM/stage.log"; exit 1; }
grep -m1 '^staged' "$SIM/stage.log"
tar -xf "$SIM/stageout/icb-rt5-discovery.tar" -C "$SIM/tmp" || exit 1
PROD=$(git rev-parse "v1.60.1^{commit}")
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "refs/tags/v1.60.1:refs/tags/v1.60.1" \
  && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD" || exit 1
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'PY'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "python stub: NOT read-only"; exit 3;; esac
case "$1" in
  */rt5_discovery.py)
    cat "$SIMSTATE/discovery.json" > "$3/discovery.json"; echo "== 1 · the families (stub)" | tee "$3/discovery.txt"; exit 0 ;;
  -c) case "$2" in
        *"import tools.costing_audit"*) echo "$PWD/tools/costing_audit/__init__.py"; exit 0 ;;
        *"import app"*) cat "$SIMSTATE/app_where"; exit 0 ;;
      esac ;;
  -m) # python -m tools.costing_audit run --pack P --env prod --out DIR --stem STEM
      out=""; stem=""; while [ $# -gt 0 ]; do case "$1" in --out) out=$2; shift 2;; --stem) stem=$2; shift 2;; *) shift;; esac; done
      echo "$stem" >> "$SIMSTATE/runs.log"
      rc=$(cat "$SIMSTATE/run_rc"); [ "$rc" = 2 ] && { echo "Traceback (stub)"; exit 2; }
      printf -- '- Cells: ACCEPTED 24, PASS 549, SKIP 117\n' > "$out/$stem.md"; echo '{"cells": []}' > "$out/$stem.json"; exit "$rc" ;;
esac
exec python3 "$@"
PY
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb" && echo 'DATABASE_URL=postgresql+psycopg://x:y@localhost/icb_platform' > "$SIM/etc/icb/backend.env"
echo 0051 > "$SIM/state/alembic"; echo 0 > "$SIM/state/run_rc"
echo /opt/icb-platform/backend/app/__init__.py > "$SIM/state/app_where"
OK='{"database": "icb_platform", "costings": [{"quote_number": "A1/10/2026", "rule": "CHILLER"}]}'
echo "$OK" > "$SIM/state/discovery.json"
cat > "$SIM/bin/psql" <<'PS'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only"; exit 3;; esac
case "$*" in *current_database*) echo icb_platform ;; *alembic_version*) cat "$SIMSTATE/alembic" ;; *) exit 3 ;; esac
PS
chmod +x "$SIM/bin/psql"
run() { sleep 1; : > "$SIM/state/runs.log"
        unshare -m bash -c "mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/tmp' /tmp &&
          export PATH='$SIM/bin':\$PATH SIMSTATE='$SIM/state' ${EXTRA:-} && bash /tmp/icb-rt5-discovery/rt5_discovery.sh" > "$SIM/last.log" 2>&1
        grep -E '^######## (STOP|DONE)' "$SIM/last.log" | head -n 1; }
P=0; F=0
expect() { local got; got=$(run); if [[ "$got" =~ $2 ]]; then echo "PASS  $1 :: $got"; P=$((P+1)); else echo "FAIL  $1 :: $got"; F=$((F+1)); sed 's/^/   | /' "$SIM/last.log" | tail -n 12; fi; }
check() { if eval "$2"; then echo "PASS  $1"; P=$((P+1)); else echo "FAIL  $1"; F=$((F+1)); fi; }

expect "over v1.60.1"                      'DONE'
T=$(ls -t "$SIM/tmp/icb-rt5-discovery/"out-*.tar | head -n1)
check "both packs ran, freezers then smoke"  '[ "$(tr "\n" " " < "$SIM/state/runs.log")" = "prod_freezers prod_smoke " ]'
check "the output tar carries discovery + both reports" \
  'tar -tf "$T" | grep -q discovery.json && tar -tf "$T" | grep -q reports/prod_freezers.json && tar -tf "$T" | grep -q reports/prod_smoke.json'
check "the staged tool is the roof_floor_eps prototype" 'grep -q roof_floor_eps "$SIM/tmp/icb-rt5-discovery/stage/backend/tools/costing_audit/scenarios.py"'
echo 1 > "$SIM/state/run_rc"
expect "unaccepted cells (exit 1) are reported, not a stop" 'DONE'
echo 2 > "$SIM/state/run_rc"
expect "the audit run crashes"             'STOP \[RUN\]'
echo 0 > "$SIM/state/run_rc"
echo /root/elsewhere/app/__init__.py > "$SIM/state/app_where"
expect "app imports from somewhere else"   'STOP \[IMPORT\]'
echo /opt/icb-platform/backend/app/__init__.py > "$SIM/state/app_where"
echo '{"costings": [{"note": "ask jan.smit@example.co.za"}]}' > "$SIM/state/discovery.json"
expect "email-shaped value in the output"  'STOP \[GATE\]'
N=$(ls "$SIM"/tmp/icb-rt5-discovery/out-*/discovery.json 2>/dev/null | wc -l)
check "the gated discovery.json was deleted (only the 2 DONE runs + 2 later stops keep one)" '[ "$N" = 4 ]'
echo "$OK" > "$SIM/state/discovery.json"
echo 0050 > "$SIM/state/alembic"
expect "alembic not 0051"                  'STOP \[DB\]'
echo 0051 > "$SIM/state/alembic"
EXTRA="PGOPTIONS=" expect "the stubs see read-only sessions even when the caller's PGOPTIONS is empty" 'DONE'
echo "# tampered" >> "$SIM/tmp/icb-rt5-discovery/rt5_discovery.py"
expect "a staged file was edited"          'STOP \[KIT\]'
sed -i '$ d' "$SIM/tmp/icb-rt5-discovery/rt5_discovery.py"
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved"                   'STOP \[CODE\]'
echo "RESULT: $P passed, $F failed"
