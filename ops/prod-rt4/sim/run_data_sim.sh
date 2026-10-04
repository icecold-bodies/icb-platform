#!/bin/bash
# rt4_data.sh simulation, run as root in WSL:  bash run_data_sim.sh [kit-branch]
# The REAL rt4_data.sh + mkstage_data.sh run in a private mount namespace where /opt, /etc, /var/backups and /tmp are
# bind-mounted from $SIM. The tool is a stand-in (fake_s_tool.py) that keeps the real tool's output contract; psql,
# pg_dump and the venv python are stubs; git is real. The sim origin is backport/v1.39-base + the RT4 branch, tagged
# v1.60.1 (an annotated sim tag), so the staged manifest is the COMMITTED manifest_s.yaml.
set -u
KIT=${1:-rt4/build}
WIN=/mnt/c/Users/micge/Documents
HERE=$(cd "$(dirname "$0")" && pwd)
SIM=/root/rt4simD-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,varbackups,tmp,state,stageout}
export SIMSTATE=$SIM/state

echo "== sim origin: origin/backport/v1.39-base + $KIT, tagged v1.60.1"
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
$G -C "$SIM/origin.git" fetch -q "$WIN/icb-platform" "+refs/remotes/origin/backport/v1.39-base:refs/heads/backport/v1.39-base" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$WIN/icb-platform" "$KIT" && git -c user.email=sim@x -c user.name=sim merge -q --no-edit FETCH_HEAD || exit 1
git push -q origin backport/v1.39-base && git fetch -q origin
TARGET=$(git rev-parse HEAD)
git -c user.email=sim@x -c user.name=sim tag -f -a v1.60.1 -m sim "$TARGET" > /dev/null && git push -q -f origin v1.60.1
bash ops/prod-rt4/mkstage_data.sh "$SIM/stageout" "$TARGET" | head -n 1 || exit 1
tar -xf "$SIM/stageout/icb-rt4-data.tar" -C "$SIM/tmp" || exit 1

echo "== the fake prod at ${TARGET:0:7} (v1.60.1 deployed, alembic 0051)"
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TARGET"
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<EOF
#!/bin/bash
case "\$*" in
  *"import yaml, psycopg, app.formula_engine, app.db_guard, app.services.sections"*)
     [ -f /opt/icb-platform/backend/app/services/sections.py ] && exit 0 || exit 1 ;;
esac
case "\$1" in
  *audit_pricing_corrections.py) shift; exec python3 "$HERE/fake_s_tool.py" "\$@" ;;
esac
exec python3 "\$@"
EOF
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo 'DATABASE_URL=postgresql+psycopg://icb_app:sim@localhost:5432/icb_platform' > "$SIM/etc/icb/backend.env"
echo 0051 > "$SIMSTATE/alembic"
cat > "$SIM/bin/psql" <<'EOF'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only"; exit 3;; esac
sql=; while [ $# -gt 0 ]; do [ "$1" = -c ] && sql=$2; shift; done
case "$sql" in *current_database*) echo icb_platform ;; *alembic_version*) cat "$SIMSTATE/alembic" ;; *) echo "unknown SQL"; exit 3 ;; esac
EOF
cat > "$SIM/bin/pg_dump" <<'EOF'
#!/bin/bash
echo "-- stub data-only dump: $*"; echo "COPY ... FROM stdin;"
EOF
chmod +x "$SIM/bin/"*

run() { # run the staged kit as prod would; prints its first banner line
  sleep 1
  unshare -m bash -c "
    mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/varbackups' /var/backups &&
    mount --bind '$SIM/tmp' /tmp && export PATH='$SIM/bin':\$PATH SIMSTATE='$SIMSTATE' &&
    bash /tmp/icb-rt4-data/rt4_data.sh $*" > "$SIM/last.log" 2>&1
  grep -E '^######## ' "$SIM/last.log" | head -n 1
}
PASSES=0; FAILS=0
expect() { # $1 label, $2 regex the banner must match, rest = rt4_data.sh args
  local label=$1 want=$2; shift 2
  local got; got=$(run "$@")
  if [[ "$got" =~ $want ]]; then echo "PASS  $label  :: $got"; PASSES=$((PASSES+1))
  else echo "FAIL  $label  :: $got  (wanted /$want/)"; FAILS=$((FAILS+1)); sed 's/^/        | /' "$SIM/last.log" | tail -n 25; fi
}
jr() { ls -t "$SIM/varbackups/icb-rt4-2026-10/"journal_S_*.json 2>/dev/null | head -n1 | sed "s#$SIM/varbackups#/var/backups#"; }

echo; echo "== the window sequence"
expect "dryrun S"                     'DONE \(dryrun S: 46 to apply, 0 already applied\.; drafts: 2 to apply' dryrun
expect "apply S"                      'DONE \(apply S\)'                     apply
ls "$SIM/varbackups/icb-rt4-2026-10/" | sed 's/^/        kept: /'
grep -q 'they are unused now' "$SIM/last.log" && echo "PASS  second dry-run: 0 to apply + 83/84/85 unused" && PASSES=$((PASSES+1)) \
  || { echo "FAIL  second dry-run lines"; FAILS=$((FAILS+1)); }
expect "dryrun S again = already"     'already applied'                      dryrun
expect "apply S again = already"      'already applied'                      apply
expect "revert S"                     'DONE \(revert S\)'                    revert "$(jr)"
expect "revert S again (moved)"       'STOP \[REVERT\]'                      revert "$(jr)"
echo; echo "== the guards"
touch "$SIMSTATE/unused_fail"
expect "another line names 83 = STOP" 'STOP \[UNUSED\]'                      dryrun
expect "... and apply refuses too"    'STOP \[UNUSED\]'                      apply
rm -f "$SIMSTATE/unused_fail"; touch "$SIMSTATE/guard_fail"
expect "guard mismatch"               'STOP \[GUARD\]'                       dryrun
rm -f "$SIMSTATE/guard_fail"; touch "$SIMSTATE/plan_short"
expect "plan not the reviewed size"   'STOP \[PLAN\]'                        dryrun
rm -f "$SIMSTATE/plan_short"
echo 0050 > "$SIMSTATE/alembic"
expect "wrong alembic"                'STOP \[DB\]'                          dryrun
echo 0051 > "$SIMSTATE/alembic"
mv "$SIM/opt/icb-platform/backend/app/services/sections.py" "$SIMSTATE/sections.py.bak"
expect "the v1.60.1 app missing"      'STOP \[IMPORT\]'                      dryrun
mv "$SIMSTATE/sections.py.bak" "$SIM/opt/icb-platform/backend/app/services/sections.py"
echo tampered >> "$SIM/tmp/icb-rt4-data/stage/docs/audit/rt4_2026-10/manifest_s/manifest_s.yaml"
expect "tampered manifest"            'STOP \[KIT\]'                         dryrun
tar -xf "$SIM/stageout/icb-rt4-data.tar" -C "$SIM/tmp" --overwrite   # restage the untampered kit
expect "revert with a foreign journal" 'STOP \[USAGE\]'                      revert /etc/hostname
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved (not v1.60.1)" 'STOP \[CODE\]'                       dryrun
echo; echo "== $PASSES passed, $FAILS failed · SIM=$SIM"
