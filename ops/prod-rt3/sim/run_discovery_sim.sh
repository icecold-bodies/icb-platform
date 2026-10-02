#!/bin/bash
# rt3_discovery.sh simulation, run as root in WSL:  bash run_discovery_sim.sh [branch]
# The REAL rt3_discovery.sh + mkstage_discovery.sh in a private mount namespace (fake /opt, /etc, /tmp); psql and the
# venv python are stubs (the real rt3_discovery.py ran against the prod mirror); git is real.
set -u
BR=${1:-rt3/discovery}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt3simX-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout,state}
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
$G fetch -q "$WIN/icb-platform" "$BR" "refs/tags/v1.59.3:refs/tags/v1.59.3" && git -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
bash ops/prod-rt3/mkstage_discovery.sh "$SIM/stageout" HEAD | head -n 1 || exit 1
tar -xf "$SIM/stageout/icb-rt3-discovery.tar" -C "$SIM/tmp" || exit 1
PROD=$(git rev-parse "v1.59.3^{commit}")
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "refs/tags/v1.59.3:refs/tags/v1.59.3" \
  && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD" || exit 1
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'PY'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "python stub: NOT read-only"; exit 3;; esac
case "$1" in */rt3_discovery.py) echo "== trailer groups (stub)"; echo "   #1 EXPLOSIVE bodies 3 / 3"; exit 0 ;; esac
exec python3 "$@"
PY
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb" && echo 'DATABASE_URL=postgresql+psycopg://x:y@localhost/icb_platform' > "$SIM/etc/icb/backend.env"
echo 0050 > "$SIM/state/alembic"
cat > "$SIM/bin/psql" <<'PS'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only"; exit 3;; esac
case "$*" in *current_database*) echo icb_platform ;; *alembic_version*) cat "$SIMSTATE/alembic" ;; *) exit 3 ;; esac
PS
chmod +x "$SIM/bin/psql"
run() { sleep 1; unshare -m bash -c "mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/tmp' /tmp &&
          export PATH='$SIM/bin':\$PATH SIMSTATE='$SIM/state' && bash /tmp/icb-rt3-discovery/rt3_discovery.sh" > "$SIM/last.log" 2>&1
        grep -E '^######## ' "$SIM/last.log" | head -n 1; }
P=0; F=0
expect() { local got; got=$(run); if [[ "$got" =~ $2 ]]; then echo "PASS  $1 :: $got"; P=$((P+1)); else echo "FAIL  $1 :: $got"; F=$((F+1)); sed 's/^/   | /' "$SIM/last.log" | tail -n 8; fi; }
expect "over v1.59.3"        'DONE'
echo 0049 > "$SIM/state/alembic"
expect "alembic not 0050"    'STOP \[DB\]'
echo 0050 > "$SIM/state/alembic"
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved"     'STOP \[CODE\]'
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD"
echo x >> "$SIM/tmp/icb-rt3-discovery/rt3_discovery.py"
expect "tampered kit"        'STOP \[KIT\]'
echo "== $P passed, $F failed · SIM=$SIM"
