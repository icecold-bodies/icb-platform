#!/bin/bash
# rt2_data.sh simulation, run as root in WSL:  bash run_data_sim.sh <manifest_p.yaml> [part-branch] [kit-branch]
# The REAL rt2_data.sh + mkstage_data.sh run in a private mount namespace where /opt, /etc, /var/backups and /tmp are
# bind-mounted from $SIM. Both tools are stand-ins (fake_tools.py) that keep the real tools' output contracts; psql,
# pg_dump and the venv python are stubs; git is real. The sim origin is backport/v1.39-base + the RT2 code + the kit
# + a sim commit carrying the given manifest_p.yaml, tagged v1.59.3.
set -u
MP_SRC=${1:?usage: bash run_data_sim.sh <manifest_p.yaml> [part-branch] [kit-branch]}
PART=${2:-rt2/part2-golden}
KIT=${3:-rt2/release-v1.59.3}
WIN=/mnt/c/Users/micge/Documents
HERE=$(cd "$(dirname "$0")" && pwd)
SIM=/root/rt2simD-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,varbackups,tmp,state,stageout}
export SIMSTATE=$SIM/state

echo "== sim origin: origin/backport/v1.39-base + $PART + $KIT + the manifest, tagged v1.59.3"
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
$G -C "$SIM/origin.git" fetch -q "$WIN/icb-platform" "+refs/remotes/origin/backport/v1.39-base:refs/heads/backport/v1.39-base" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$WIN/icb-platform" "$PART" && git merge -q --ff-only FETCH_HEAD || exit 1
$G fetch -q "$WIN/icb-platform" "$KIT" && git -c user.email=sim@x -c user.name=sim merge -q --no-edit FETCH_HEAD || exit 1
MP=docs/audit/rt2_2026-10/manifest_p/manifest_p.yaml
mkdir -p "$(dirname "$MP")" && tr -d '\r' < "$MP_SRC" > "$MP" && git add "$MP" \
  && git -c user.email=sim@x -c user.name=sim commit -qm "sim: manifest P" || exit 1
git push -q origin backport/v1.39-base && git fetch -q origin
TARGET=$(git rev-parse HEAD)
git -c user.email=sim@x -c user.name=sim tag -f -a v1.59.3 -m sim "$TARGET" > /dev/null && git push -q -f origin v1.59.3
bash ops/prod-rt2/mkstage_data.sh "$SIM/stageout" "$TARGET" | head -n 1 || exit 1
tar -xf "$SIM/stageout/icb-rt2-data.tar" -C "$SIM/tmp" || exit 1
P_N=$(grep -c '^- finding:' "$MP")

echo "== the fake prod at ${TARGET:0:7} (v1.59.3 deployed, alembic 0050)"
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TARGET"
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<EOF
#!/bin/bash
case "\$*" in
  *"import yaml, psycopg, app.formula_engine, app.db_guard"*) exit 0 ;;
esac
case "\$1" in
  *audit_pricing_corrections.py) shift; exec python3 "$HERE/fake_tools.py" P "\$@" ;;
  *rt2_defaults.py) shift; exec python3 "$HERE/fake_tools.py" D "\$@" ;;
esac
exec python3 "\$@"
EOF
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo 'DATABASE_URL=postgresql+psycopg://icb_app:sim@localhost:5432/icb_platform' > "$SIM/etc/icb/backend.env"
echo 0050 > "$SIMSTATE/alembic"
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
    bash /tmp/icb-rt2-data/rt2_data.sh $*" > "$SIM/last.log" 2>&1
  grep -E '^######## ' "$SIM/last.log" | head -n 1
}
PASSES=0; FAILS=0
expect() { # $1 label, $2 regex the banner must match, rest = rt2_data.sh args
  local label=$1 want=$2; shift 2
  local got; got=$(run "$@")
  if [[ "$got" =~ $want ]]; then echo "PASS  $label  :: $got"; PASSES=$((PASSES+1))
  else echo "FAIL  $label  :: $got  (wanted /$want/)"; FAILS=$((FAILS+1)); sed 's/^/        | /' "$SIM/last.log" | tail -n 25; fi
}
jr() { ls -t "$SIM/varbackups/icb-rt2-2026-10/"journal_"$1"_*.json 2>/dev/null | head -n1 | sed "s#$SIM/varbackups#/var/backups#"; }

echo; echo "== the window sequence (P: $P_N entries)"
expect "dryrun D before P"            'STOP \[ORDER\]'                       dryrun D
expect "apply D before P"             'STOP \[ORDER\]'                       apply D
expect "dryrun P"                     "DONE \(dryrun P: $P_N to apply"       dryrun P
expect "apply P"                      'DONE \(apply P\)'                     apply P
ls "$SIM/varbackups/icb-rt2-2026-10/" | sed 's/^/        kept: /'
expect "apply P again = already"      'already applied'                      apply P
expect "dryrun D (P on)"              'DONE \(dryrun D: 4 to apply'          dryrun D
expect "apply D"                      'DONE \(apply D\)'                     apply D
ls "$SIM/varbackups/icb-rt2-2026-10/" | grep -E '_D_' | sed 's/^/        kept: /'
expect "apply D again = already"      'already applied'                      apply D
expect "revert P while D is on"       'STOP \[ORDER\]'                       revert "$(jr P)"
expect "revert D"                     'DONE \(revert D\)'                    revert "$(jr D)"
expect "revert P (D off)"             'DONE \(revert P\)'                    revert "$(jr P)"
expect "revert P again (moved)"       'STOP \[REVERT\]'                      revert "$(jr P)"
expect "dryrun D after P reverted"    'STOP \[ORDER\]'                       dryrun D
echo; echo "== the guards"
expect "re-apply P"                   'DONE \(apply P\)'                     apply P
touch "$SIMSTATE/others_4g"
expect "another body already 4G"      'STOP \[OTHERS\]'                      dryrun D
rm -f "$SIMSTATE/others_4g"
touch "$SIMSTATE/guard_fail_p"
expect "P guard mismatch"             'STOP \[ORDER\]'                       dryrun D
expect "P guard mismatch (dryrun P)"  'STOP \[GUARD\]'                       dryrun P
rm -f "$SIMSTATE/guard_fail_p"; echo 0 > "$SIMSTATE/applied_p"; touch "$SIMSTATE/plan_short_p"
expect "P plan not the reviewed size" 'STOP \[PLAN\]'                        dryrun P
rm -f "$SIMSTATE/plan_short_p"
echo 0049 > "$SIMSTATE/alembic"
expect "before the deploy (0049)"     'STOP \[DB\]'                          dryrun P
echo 0050 > "$SIMSTATE/alembic"
echo tampered >> "$SIM/tmp/icb-rt2-data/stage/$MP"
expect "tampered manifest"            'STOP \[KIT\]'                         dryrun P
tar -xf "$SIM/stageout/icb-rt2-data.tar" -C "$SIM/tmp" --overwrite   # restage the untampered kit
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved"              'STOP \[CODE\]'                        dryrun P
echo; echo "== $PASSES passed, $FAILS failed · SIM=$SIM"
