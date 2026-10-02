#!/bin/bash
# rt3_families.sh simulation, run as root in WSL:  bash run_families_sim.sh [kit-branch]
# The REAL rt3_families.sh + mkstage_window.sh run in a private mount namespace where /opt, /etc, /var/backups and
# /tmp are bind-mounted from $SIM. The tool is a stand-in (fake_families.py) that keeps the real tool's output
# contract; psql, pg_dump and the venv python are stubs; git is real. The sim origin is backport/v1.39-base + the
# kit branch, tagged v1.60.0 (the families kit stages only once the tag is on origin).
set -u
KIT=${1:-rt3/families}
WIN=/mnt/c/Users/micge/Documents
REPO=$WIN/icb-platform-rt3
HERE=$(cd "$(dirname "$0")" && pwd)
SIM=/root/rt3simF-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,varbackups,tmp,state,stageout}
export SIMSTATE=$SIM/state

echo "== sim origin: origin/backport/v1.39-base + $KIT, tagged v1.60.0"
$G clone -q --bare --single-branch --branch backport/v1.39-base "$REPO" "$SIM/origin.git" || exit 1
$G -C "$SIM/origin.git" fetch -q "$REPO" "+refs/remotes/origin/backport/v1.39-base:refs/heads/backport/v1.39-base" || exit 1
$G -C "$SIM/origin.git" fetch -q "$REPO" "+refs/tags/v1.59.3:refs/tags/v1.59.3" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$REPO" "$KIT" && git -c user.email=sim@x -c user.name=sim merge -q --no-edit FETCH_HEAD || exit 1
git push -q origin backport/v1.39-base && git fetch -q origin
TARGET=$(git rev-parse HEAD)
git -c user.email=sim@x -c user.name=sim tag -f -a v1.60.0 -m sim "$TARGET" > /dev/null && git push -q -f origin v1.60.0
bash ops/prod-rt3/mkstage_window.sh "$SIM/stageout" "$TARGET" | head -n 1 || exit 1
[ -f "$SIM/stageout/icb-rt3-families.tar" ] || { echo "SIM: mkstage_window produced no families tar"; exit 1; }
tar -xf "$SIM/stageout/icb-rt3-families.tar" -C "$SIM/tmp" || exit 1

echo "== the fake prod at ${TARGET:0:7} (v1.60.0 deployed, alembic 0051)"
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TARGET"
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<EOF
#!/bin/bash
case "\$*" in
  "-c import psycopg") exit 0 ;;
esac
case "\$1" in
  *rt3_families.py) shift; exec python3 "$HERE/fake_families.py" x "\$@" ;;
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

run() { # run the staged kit as prod would; prints its banner line
  sleep 1
  unshare -m bash -c "
    mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/varbackups' /var/backups &&
    mount --bind '$SIM/tmp' /tmp && export PATH='$SIM/bin':\$PATH SIMSTATE='$SIMSTATE' &&
    bash /tmp/icb-rt3-families/rt3_families.sh $*" > "$SIM/last.log" 2>&1
  grep -E '^######## ' "$SIM/last.log" | head -n 1
}
PASSES=0; FAILS=0
expect() { # $1 label, $2 regex the banner must match, rest = rt3_families.sh args
  local label=$1 want=$2; shift 2
  local got; got=$(run "$@")
  if [[ "$got" =~ $want ]]; then echo "PASS  $label  :: $got"; PASSES=$((PASSES+1))
  else echo "FAIL  $label  :: $got  (wanted /$want/)"; FAILS=$((FAILS+1)); sed 's/^/        | /' "$SIM/last.log" | tail -n 25; fi
}
jr() { ls -t "$SIM/varbackups/icb-rt3-2026-10/"journal_families_*.json 2>/dev/null | head -n1 | sed "s#$SIM/varbackups#/var/backups#"; }

echo; echo "== the window sequence"
echo 0050 > "$SIMSTATE/alembic"
expect "dryrun before the deploy (0050)" 'STOP \[DB\]'                          dryrun
echo 0051 > "$SIMSTATE/alembic"
expect "dryrun"                          'DONE \(dryrun: 40 to apply'           dryrun
expect "apply"                           'DONE \(apply\)'                       apply
ls "$SIM/varbackups/icb-rt3-2026-10/" | sed 's/^/        kept: /'
expect "apply again = already"           'already applied'                      apply
expect "dryrun after = already (the restart check, step f)" 'already applied'   dryrun
expect "revert"                          'DONE \(revert'                        revert "$(jr)"
expect "revert again (idempotent)"       'DONE \(revert'                        revert "$(jr)"
expect "re-apply"                        'DONE \(apply\)'                       apply
echo; echo "== the guards"
touch "$SIMSTATE/moved"
expect "revert after a row moved"        'STOP \[REVERT\]'                      revert "$(jr)"
rm -f "$SIMSTATE/moved" "$SIMSTATE/applied"
touch "$SIMSTATE/guard_fail"
expect "prod moved since the discovery"  'STOP \[GUARD\]'                       dryrun
rm -f "$SIMSTATE/guard_fail"; touch "$SIMSTATE/plan_short"
expect "plan not the reviewed size"      'STOP \[PLAN\]'                        dryrun
rm -f "$SIMSTATE/plan_short"; touch "$SIMSTATE/guard_line_bad"
expect "guard names another set"         'STOP \[GUARD\]'                       dryrun
rm -f "$SIMSTATE/guard_line_bad"; touch "$SIMSTATE/apply_refuse"
N0=$(ls "$SIM/varbackups/icb-rt3-2026-10/" | grep -c journal_ || true)
expect "the apply's own guard refuses"   'STOP \[APPLY\]'                       apply
N1=$(ls "$SIM/varbackups/icb-rt3-2026-10/" | grep -c journal_ || true)
[ "$N0" = "$N1" ] && { echo "PASS  no journal from a refused apply"; PASSES=$((PASSES+1)); } || { echo "FAIL  a refused apply left a journal"; FAILS=$((FAILS+1)); }
rm -f "$SIMSTATE/apply_refuse"
expect "usage"                           '^$|STOP'                              bogus
echo tampered >> "$SIM/tmp/icb-rt3-families/rt3_families.py"
expect "tampered tool"                   'STOP \[KIT\]'                         dryrun
tar -xf "$SIM/stageout/icb-rt3-families.tar" -C "$SIM/tmp" --overwrite   # restage the untampered kit
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved"                 'STOP \[CODE\]'                        dryrun
echo; echo "== $PASSES passed, $FAILS failed · SIM=$SIM"
