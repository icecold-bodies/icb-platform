#!/bin/bash
# v1.59.2 release-kit simulation, run as root in WSL:  bash run_sim.sh <scenario>
# Scenarios: happy | notag | moved | bootfail | traceback | stalecache | resume
# Builds a throw-away prod (repo at de74796 WITHOUT the v1.59.0 tag, as the real VM; fake venv/dist/env/
# backups/deploy record) under $SIM and runs the STAGED kit (built by the real mkstage.sh from a sim
# origin that carries the release branch + an annotated v1.59.2 tag) inside a private mount namespace
# where /opt, /etc, /var/tmp, /var/backups and /tmp are bind-mounted from $SIM — nothing outside $SIM is
# touched. The REAL deploy/prod/icb-deploy.sh (unchanged since de74796) runs; systemd, postgres, curl,
# sudo, npm and the venv are stubs.
set -u
SCEN=${1:-happy}
WIN=/mnt/c/Users/micge/Documents
HERE=$(cd "$(dirname "$0")" && pwd)
SIM=/root/relsim2-$SCEN-$(date +%s)
G="git -c safe.directory=*"
PREV=$($G -C $WIN/icb-platform rev-parse de74796)
[ -e "$SIM" ] && { echo "exists: $SIM"; exit 1; }
mkdir -p "$SIM"/{bin,work,opt,vartmp,varbackups/postgres,tmp,state,stageout}
export SIMSTATE=$SIM/state

echo "== the sim origin: backport/v1.39-base + the release branch (fast-forward), annotated tag v1.59.2"
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" || exit 1
cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$WIN/icb-platform" release/v1.59.2 || exit 1
git merge -q --ff-only FETCH_HEAD || exit 1
git push -q origin backport/v1.39-base && git fetch -q origin
TARGET=$(git rev-parse HEAD); echo "$TARGET" > "$SIMSTATE/target"
git -c user.email=sim@x -c user.name=sim tag -f -a v1.59.2 -m "sim v1.59.2" "$TARGET" > /dev/null && git push -q -f origin v1.59.2   # -f: the clone carries the real tag
echo "   prev ${PREV:0:7}  target ${TARGET:0:7}  tag $(git rev-parse v1.59.2 | cut -c1-12)"

echo "== stage the kit with the real mkstage.sh"
bash ops/prod-release-v1.59.2/mkstage.sh "$SIM/stageout" "$TARGET" "$PREV" | tail -n 3 || exit 1
[ -f "$SIM/stageout/icb-release-v1.59.2.tar" ] || { echo "SIM: mkstage produced no tar"; exit 1; }
tar -xf "$SIM/stageout/icb-release-v1.59.2.tar" -C "$SIM/tmp" || exit 1
git cat-file blob "$PREV:backend/app/static/js/calculator.js" > "$SIMSTATE/calc_prev.js"

echo "== the fake prod at ${PREV:0:7}"
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" || exit 1
cd "$SIM/opt/icb-platform" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base "$PREV" && git branch -q -u origin/backport/v1.39-base
for t in $(git tag --contains "$PREV"); do git tag -d "$t" > /dev/null; done   # prod's fetch predates these tags
git tag -d v1.59.2 > /dev/null 2>&1
echo "   prod describe: $(git describe --tags --abbrev=0 HEAD)"
mkdir -p frontend/dist/assets .venv/bin
echo 'console.log("spa")' > frontend/dist/assets/index-Be8qL-PA.js
echo '<script type="module" src="/mes-app/assets/index-Be8qL-PA.js"></script>' > frontend/dist/index.html
cat > .venv/bin/python <<'EOF'
#!/bin/bash
a="$*"
case "$a" in
  *"import yaml"*) echo 6.0.2 ;;
  *tools.costing_audit*) echo ok ;;
  --version) echo "Python 3.12.3" ;;
  *) exec python3 "$@" ;;
esac
EOF
cat > .venv/bin/alembic <<'EOF'
#!/bin/bash
case "$1" in upgrade) echo "INFO  (stub) already at head";; current) echo "0049 (head)";; esac
EOF
chmod +x .venv/bin/*
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo "export PATH=$SIM/bin:\$PATH SIMSTATE=$SIMSTATE" >> "$SIM/etc/profile"   # login shells (bash -lc) keep the stubs
echo 'DATABASE_URL=postgresql+psycopg://icb_app:sim@localhost:5432/icb_platform' > "$SIM/etc/icb/backend.env"
echo "completed $PREV" > "$SIM/vartmp/icb-deploy-state"
echo x > "$SIM/varbackups/postgres/icb_platform_20260930-0230.dump.gz"
echo 0049 > "$SIMSTATE/alembic"; echo 149619 > "$SIMSTATE/pid"; echo "Mon 2026-09-28 15:28:30 SAST" > "$SIMSTATE/aet"
echo "$PREV" > "$SIMSTATE/live_code"
sleep 3   # the fake service starts AFTER the fake prod's last HEAD move, as on the real VM (ff 15:28:2x, start 15:28:30)
awk '{ printf "%d\n", $1 * 1000000 }' /proc/uptime > "$SIMSTATE/mono"
now=$(date +%s); : > "$SIMSTATE/journal"; for i in 1 2 3 4; do echo "$now INFO:     Application startup complete." >> "$SIMSTATE/journal"; done
sleep 3   # ... and the window opens a few seconds later (prod: days later)
bash "$HERE/stubs.sh" "$SIM/bin"
cat > "$SIM/bin/npm" <<'EOF'
#!/bin/bash
echo "(stub) npm $*"
EOF
chmod +x "$SIM/bin/npm"
case "$SCEN" in
  bootfail) touch "$SIMSTATE/fail_bootstrap" ;;
  traceback) touch "$SIMSTATE/traceback" ;;
  stalecache) touch "$SIMSTATE/stalecache" ;;
  notag) git -C "$SIM/origin.git" tag -d v1.59.2 > /dev/null && echo "   (notag) the tag is removed from origin after staging" ;;
  resume) touch "$SIMSTATE/fail_restart" ;;
esac

run() { # run the staged kit inside the private mount namespace, as prod would
  unshare -m bash -c "
    mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/vartmp' /var/tmp &&
    mount --bind '$SIM/varbackups' /var/backups && mount --bind '$SIM/tmp' /tmp &&
    export PATH='$SIM/bin':\$PATH SIMSTATE='$SIMSTATE' && bash /tmp/icb-release-v1.59.2/release.sh $1"
}
echo; echo "################ preflight"; run preflight; echo "   -> exit $?"
echo; echo "################ verify BEFORE the deploy (must fail on exactly the 6 not-yet-deployed checks)"; run verify; echo "   -> exit $?"
[ "$SCEN" = moved ] && git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit on prod"
echo; echo "################ deploy"; run deploy; echo "   -> exit $?"
if [ "$SCEN" = resume ]; then
  rm -f "$SIMSTATE/fail_restart"
  echo; echo "################ deploy AGAIN after the failed restart (must RESUME and pass)"; run deploy; echo "   -> exit $?"
fi
echo; echo "################ verify AFTER the deploy"; run verify; echo "   -> exit $?"
echo; echo "################ deploy again (must say ALREADY DEPLOYED and verify)"; run deploy; echo "   -> exit $?"
echo; echo "== sim state: prod HEAD $(git -C "$SIM/opt/icb-platform" rev-parse --short HEAD), describe $(git -C "$SIM/opt/icb-platform" describe --tags --abbrev=0 HEAD 2>/dev/null), record '$(cat "$SIM/vartmp/icb-deploy-state")'"
echo "== backups: $(ls "$SIM/varbackups/postgres" | tr '\n' ' ')"
echo "== root-owned __pycache__ the kit left in the repo (want 0): $(find "$SIM/opt/icb-platform" -name __pycache__ -newer "$SIMSTATE/target" | wc -l)"
echo "SIM=$SIM"
