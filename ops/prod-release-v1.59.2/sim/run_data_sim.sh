#!/bin/bash
# rt1_data.sh simulation, run as root in WSL:  bash run_sim.sh
# The REAL rt1_data.sh + mkstage_data.sh (from the release branch) run in a private mount namespace where /opt,
# /etc, /var/backups and /tmp are bind-mounted from $SIM. The correction tool is a stand-in (fake_tool.py) that
# keeps the real tool's output contract; psql, pg_dump and the venv python are stubs; git is real.
set -u
WIN=/mnt/c/Users/micge/Documents
HERE=$(cd "$(dirname "$0")" && pwd)
SIM=/root/relsim3-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,varbackups,tmp,state,stageout}
export SIMSTATE=$SIM/state

echo "== sim origin + a target commit carrying the kit, a stand-in manifest_b.yaml, and the annotated tag"
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$WIN/icb-platform" release/v1.59.2 && git merge -q --ff-only FETCH_HEAD || exit 1
D=docs/audit/srd_rear_frame_2026-09
{ echo "note: sim stand-in"; echo "changes:"; for i in 1 2 3 4 5 6 7; do echo "- finding: B$i"; echo "  bom_id: $i"; done; } > $D/manifest_b.yaml
git add $D/manifest_b.yaml && git -c user.email=sim@x -c user.name=sim commit -qm "sim: stand-in manifest B"
git push -q origin backport/v1.39-base && git fetch -q origin
TARGET=$(git rev-parse HEAD)
git -c user.email=sim@x -c user.name=sim tag -a v1.59.2 -m sim "$TARGET" && git push -q origin v1.59.2
bash ops/prod-rt1/mkstage_data.sh "$SIM/stageout" "$TARGET" | head -n 3 || exit 1
tar -xf "$SIM/stageout/icb-rt1-data.tar" -C "$SIM/tmp" || exit 1

echo "== the fake prod at ${TARGET:0:7} (the v1.59.2 code is live)"
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TARGET"
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<EOF
#!/bin/bash
case "\$*" in
  *"import yaml, app.formula_engine, app.db_guard"*) exit 0 ;;
esac
case "\$1" in
  *audit_pricing_corrections.py) shift; exec python3 "$HERE/fake_tool.py" "\$@" ;;
esac
exec python3 "\$@"
EOF
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo 'DATABASE_URL=postgresql+psycopg://icb_app:sim@localhost:5432/icb_platform' > "$SIM/etc/icb/backend.env"
cat > "$SIM/bin/psql" <<'EOF'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only"; exit 3;; esac
sql=; while [ $# -gt 0 ]; do [ "$1" = -c ] && sql=$2; shift; done
case "$sql" in *current_database*) echo icb_platform ;; *alembic_version*) echo 0049 ;; *) echo "unknown SQL"; exit 3 ;; esac
EOF
cat > "$SIM/bin/pg_dump" <<'EOF'
#!/bin/bash
echo "-- stub data-only dump of bill_of_materials + bom_override_history"; echo "COPY icb_costings.bill_of_materials FROM stdin;"
EOF
chmod +x "$SIM/bin/"*

run() { # run the staged kit as prod would; prints its last banner line
  unshare -m bash -c "
    mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/varbackups' /var/backups &&
    mount --bind '$SIM/tmp' /tmp && export PATH='$SIM/bin':\$PATH SIMSTATE='$SIMSTATE' &&
    bash /tmp/icb-rt1-data/rt1_data.sh $*" > "$SIM/last.log" 2>&1
  grep -E '^######## ' "$SIM/last.log" | head -n 1     # the STOP/DONE banner (a STOP adds a "tell the CA" line)
}
PASSES=0; FAILS=0
expect() { # $1 label, $2 regex the banner must match, rest = rt1_data.sh args
  local label=$1 want=$2; shift 2
  local got; got=$(run "$@")
  if [[ "$got" =~ $want ]]; then echo "PASS  $label  :: $got"; PASSES=$((PASSES+1))
  else echo "FAIL  $label  :: $got  (wanted /$want/)"; FAILS=$((FAILS+1)); sed 's/^/        | /' "$SIM/last.log" | tail -n 25; fi
}
K=/var/backups/icb-rt1-2026-09
jr() { ls "$SIM/varbackups/icb-rt1-2026-09/"journal_"$1"_*.json 2>/dev/null | head -n1 | sed "s#$SIM/varbackups#/var/backups#"; }

echo; echo "== the sequence"
expect "dryrun A (fresh)"             'DONE \(dryrun A: 120 to apply'   dryrun A
expect "apply B before A is refused"  'STOP \[ORDER\]'                   apply B
expect "apply A"                      'DONE \(apply A\)'                 apply A
ls "$SIM/varbackups/icb-rt1-2026-09/" | sed 's/^/        kept: /'
expect "apply A again = already"      'already applied'                  apply A
expect "dryrun B"                     'DONE \(dryrun B: 7 to apply'      dryrun B
expect "apply B"                      'DONE \(apply B\)'                 apply B
expect "revert A while B is on"       'STOP \[ORDER\]'                   revert "$(jr A)"
expect "revert B"                     'DONE \(revert\)'                  revert "$(jr B)"
expect "revert A"                     'DONE \(revert\)'                  revert "$(jr A)"
expect "revert A again (moved)"       'STOP \[REVERT\]'                  revert "$(jr A)"
touch "$SIMSTATE/guard_fail"
expect "guard mismatch"               'STOP \[GUARD\]'                   dryrun A
rm -f "$SIMSTATE/guard_fail"; touch "$SIMSTATE/plan_short"
expect "plan not the reviewed size"   'STOP \[PLAN\]'                    dryrun A
rm -f "$SIMSTATE/plan_short"
echo tampered >> "$SIM/tmp/icb-rt1-data/stage/docs/audit/srd_rear_frame_2026-09/manifest_b.yaml"
expect "tampered manifest"            'STOP \[KIT\]'                     dryrun B
tar -xf "$SIM/stageout/icb-rt1-data.tar" -C "$SIM/tmp" --overwrite   # restage the untampered kit
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved"              'STOP \[CODE\]'                    dryrun A
echo; echo "== $PASSES passed, $FAILS failed · SIM=$SIM"
