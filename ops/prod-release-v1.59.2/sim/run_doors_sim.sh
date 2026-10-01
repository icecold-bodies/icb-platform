#!/bin/bash
# rt1_doors.sh simulation, run as root in WSL:  bash run_doors_sim.sh
# The REAL rt1_doors.sh + mkstage_doors.sh run in a private mount namespace (fake /opt, /etc, /tmp); the door report
# itself is a stub (it needs psycopg and prod's drafts — the real report ran on prod at 1b); psql / the venv python
# are stubs; git is real.
set -u
WIN=/mnt/c/Users/micge/Documents
SIM=/root/relsimD-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout}
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
$G fetch -q "$WIN/icb-platform" data/rt1-manifest-m "refs/tags/v1.59.0:refs/tags/v1.59.0" "refs/tags/v1.59.2:refs/tags/v1.59.2" || exit 1
git -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
KIT=$(git rev-parse HEAD); PREV=$(git rev-parse "v1.59.0^{commit}"); TAGC=$(git rev-parse "v1.59.2^{commit}")
bash ops/prod-rt1/mkstage_doors.sh "$SIM/stageout" "$KIT" | sed -n '1,6p' || exit 1
tar -xf "$SIM/stageout/icb-rt1-doors.tar" -C "$SIM/tmp" || exit 1
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PREV"
git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "refs/tags/v1.59.2:refs/tags/v1.59.2" || exit 1
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'EOF'
#!/bin/bash
case "$1" in */rt1_door_report.py) [ -f "$2" ] || true; [ -s "$3" ] || { echo "no snapshot"; exit 1; }
  echo "SUMMARY: 14 OK; no exceptions (stub)"; exit 0 ;; esac
exec python3 "$@"
EOF
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo 'DATABASE_URL=postgresql+psycopg://icb_app:sim@localhost:5432/icb_platform' > "$SIM/etc/icb/backend.env"
cat > "$SIM/bin/psql" <<'EOF'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only"; exit 3;; esac
case "$*" in *current_database*) echo icb_platform ;; *alembic_version*) echo 0049 ;; *) echo "unknown SQL"; exit 3 ;; esac
EOF
chmod +x "$SIM/bin/"*
run() { unshare -m bash -c "mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/tmp' /tmp &&
          export PATH='$SIM/bin':\$PATH && bash /tmp/icb-rt1-doors/rt1_doors.sh" > "$SIM/last.log" 2>&1
        grep -E '^######## ' "$SIM/last.log" | head -n 1; }
P=0; F=0
expect() { local got; got=$(run); if [[ "$got" =~ $2 ]]; then echo "PASS  $1 :: $got"; P=$((P+1)); else echo "FAIL  $1 :: $got"; F=$((F+1)); sed 's/^/   | /' "$SIM/last.log" | tail -n 12; fi; }
expect "over v1.59.0"   'DONE'
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TAGC"
expect "over v1.59.2"   'DONE'
grep -q "SUMMARY: 14 OK" "$SIM/last.log" && echo "        the report's summary is printed"
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "code moved"     'STOP \[CODE\]'
echo x >> "$SIM/tmp/icb-rt1-doors/all.json"
expect "tampered kit"   'STOP \[KIT\]'
echo "== $P passed, $F failed · SIM=$SIM"
