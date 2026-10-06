#!/bin/bash
# v1.60.2 release-kit simulation, run as root in WSL:  bash run_sim.sh <scenario> [kit-branch]
# Scenarios: happy | notag | moved | bootfail | traceback | stalecache | resume | migfail | nobackup | cfstale | famchanged
# Builds a throw-away prod (repo at v1.60.1 01751fa with the v1.60.1 tag but WITHOUT v1.60.2, as the real VM; fake
# venv/dist/env/backups/deploy record; a fake database at alembic 0051) under $SIM and runs the STAGED kit (built by
# the real mkstage.sh from a sim origin whose backport/v1.39-base carries the RT5 branch, and an annotated v1.60.2
# tag) inside a private mount namespace where /opt, /etc, /var/tmp, /var/backups and /tmp are bind-mounted from
# $SIM — nothing outside $SIM is touched, and the folder is removed at the end (the RT4 disk lesson). The REAL
# deploy/prod/icb-deploy.sh (unchanged since v1.59.0) runs, its migration step included; systemd, postgres, alembic,
# curl, sudo, npm and the venv are stubs. The three doors answer for the code the fake service is RUNNING.
set -u
SCEN=${1:-happy}
KIT=${2:-rt5/build}
WIN=/mnt/c/Users/micge/Documents
REPO=$WIN/icb-platform          # the main checkout: WSL git cannot follow a worktree's Windows .git path; same refs
SIM=/root/relsim6-$SCEN-$(date +%s)
G="git -c safe.directory=*"
PREV=$($G -C "$REPO" rev-parse "v1.60.1^{commit}")
[ "${PREV:0:7}" = 01751fa ] || { echo "SIM: v1.60.1 is ${PREV:0:7}, prod runs 01751fa"; exit 1; }
[ -e "$SIM" ] && { echo "exists: $SIM"; exit 1; }
mkdir -p "$SIM"/{bin,work,opt,vartmp,varbackups/postgres,tmp,state,stageout}
trap 'rm -rf "$SIM"' EXIT
export SIMSTATE=$SIM/state

echo "== the sim origin: backport/v1.39-base + $KIT (merge), annotated tag v1.60.2"
$G clone -q --bare --single-branch --branch backport/v1.39-base "$REPO" "$SIM/origin.git" || exit 1
$G -C "$SIM/origin.git" fetch -q "$REPO" "+refs/remotes/origin/backport/v1.39-base:refs/heads/backport/v1.39-base" || exit 1
$G -C "$SIM/origin.git" fetch -q "$REPO" "+refs/tags/v1.60.1:refs/tags/v1.60.1" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" || exit 1
cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$REPO" "$KIT" || exit 1
git -c user.email=sim@x -c user.name=sim merge -q --no-edit FETCH_HEAD || exit 1
git push -q origin backport/v1.39-base && git fetch -q origin --tags
TARGET=$(git rev-parse HEAD); echo "$TARGET" > "$SIMSTATE/target"
git -c user.email=sim@x -c user.name=sim tag -f -a v1.60.2 -m "sim v1.60.2" "$TARGET" > /dev/null && git push -q -f origin v1.60.2
echo "   prev ${PREV:0:7}  target ${TARGET:0:7}  tag $(git rev-parse v1.60.2 | cut -c1-12)"

echo "== stage the kit with the real mkstage.sh"
bash ops/prod-release-v1.60.2/mkstage.sh "$SIM/stageout" "$TARGET" "$PREV" | grep -E '^staged|^STATIC|^RULE|^N_PROBES|^STOP' || true
[ -f "$SIM/stageout/icb-release-v1.60.2.tar" ] || { echo "SIM: mkstage produced no tar"; exit 1; }
tar -xf "$SIM/stageout/icb-release-v1.60.2.tar" -C "$SIM/tmp" || exit 1
git cat-file blob "$PREV:backend/app/static/js/calculator.js" > "$SIMSTATE/calc_prev.js"

echo "== the fake prod at ${PREV:0:7}"
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" || exit 1
cd "$SIM/opt/icb-platform" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base "$PREV" && git branch -q -u origin/backport/v1.39-base
git tag -d v1.60.2 > /dev/null 2>&1     # prod's last fetch (the v1.60.1 window) predates it; v1.60.1 stays
echo "   prod describe: $(git describe --tags --abbrev=0 HEAD)"
mkdir -p frontend/dist/assets frontend/node_modules .venv/bin
echo 'console.log("spa v1.60.1")' > frontend/dist/assets/index-Bd_exvgd.js
echo '<script type="module" src="/mes-app/assets/index-Bd_exvgd.js"></script>' > frontend/dist/index.html
cat > .venv/bin/python <<'EOF'
#!/bin/bash
a="$*"
case "$a" in
  *"import yaml"*) echo 6.0.2 ;;
  *tools.costing_audit*)
    if grep -q '^RULE_NOTE_INK' /opt/icb-platform/backend/app/services/body_family.py 2>/dev/null; then echo '#D12424'
    else echo "ImportError: cannot import name 'RULE_NOTE_INK' from 'app.services.body_family'"; fi ;;
  --version) echo "Python 3.12.3" ;;
  *) exec python3 "$@" ;;
esac
EOF
cat > .venv/bin/alembic <<'EOF'
#!/bin/bash
S=$SIMSTATE
case "$1" in
  upgrade) [ -f "$S/fail_migrate" ] && { echo "ERROR [alembic] (stub) the migration failed"; exit 1; }
           if [ "$(cat "$S/alembic")" = 0052 ]; then echo "INFO  [alembic] (stub) already at head"
           else echo "INFO  [alembic.runtime.migration] Running upgrade 0051 -> 0052, Body families: a rule note on trailer_groups"; echo 0052 > "$S/alembic"; fi ;;
  current) echo "$(cat "$S/alembic") (head)" ;;
esac
EOF
chmod +x .venv/bin/*
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo "export PATH=$SIM/bin:\$PATH SIMSTATE=$SIMSTATE" >> "$SIM/etc/profile"   # login shells (bash -lc) keep the stubs
echo 'DATABASE_URL=postgresql+psycopg://icb_app:sim@localhost:5432/icb_platform' > "$SIM/etc/icb/backend.env"
echo "completed $PREV" > "$SIM/vartmp/icb-deploy-state"
echo x > "$SIM/varbackups/postgres/icb_platform_20261005-0230.dump.gz"
echo 0051 > "$SIMSTATE/alembic"; echo 152410 > "$SIMSTATE/pid"; echo "Mon 2026-10-05 08:56:09 SAST" > "$SIMSTATE/aet"
echo "$PREV" > "$SIMSTATE/live_code"
sleep 3   # the fake service starts AFTER the fake prod's last HEAD move, as on the real VM
awk '{ printf "%d\n", $1 * 1000000 }' /proc/uptime > "$SIMSTATE/mono"
now=$(date +%s); : > "$SIMSTATE/journal"; for i in 1 2 3 4; do echo "$now INFO:     Application startup complete." >> "$SIMSTATE/journal"; done
sleep 3   # ... and the window opens a few seconds later (prod: days later)
bash "$SIM/work/ops/prod-release-v1.60.2/sim/stubs.sh" "$SIM/bin"
case "$SCEN" in
  bootfail) touch "$SIMSTATE/fail_bootstrap" ;;
  traceback) touch "$SIMSTATE/traceback" ;;
  stalecache) touch "$SIMSTATE/stalecache" ;;
  notag) git -C "$SIM/origin.git" tag -d v1.60.2 > /dev/null && echo "   (notag) the tag is removed from origin after staging" ;;
  resume) touch "$SIMSTATE/fail_restart" ;;
  migfail) touch "$SIMSTATE/fail_migrate" ;;
  nobackup) touch "$SIMSTATE/backup_no_groups" ;;
  cfstale) touch "$SIMSTATE/cfstale" ;;
  famchanged) touch "$SIMSTATE/famchanged" ;;
esac

run() { # run the staged kit inside the private mount namespace, as prod would (1 s apart: each run's folder is per-second)
  sleep 1
  unshare -m bash -c "
    mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/vartmp' /var/tmp &&
    mount --bind '$SIM/varbackups' /var/backups && mount --bind '$SIM/tmp' /tmp &&
    export PATH='$SIM/bin':\$PATH SIMSTATE='$SIMSTATE' && bash /tmp/icb-release-v1.60.2/release.sh $1"
}
echo; echo "################ preflight"; run preflight; echo "   -> exit $?"
echo; echo "################ verify BEFORE the deploy (must fail on exactly the not-yet-deployed checks)"; run verify; echo "   -> exit $?"
[ "$SCEN" = moved ] && git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit on prod"
echo; echo "################ deploy"; run deploy; echo "   -> exit $?"
if [ "$SCEN" = resume ] || [ "$SCEN" = migfail ]; then
  rm -f "$SIMSTATE/fail_restart" "$SIMSTATE/fail_migrate"
  echo; echo "################ deploy AGAIN after the failure (must RESUME and pass)"; run deploy; echo "   -> exit $?"
fi
echo; echo "################ verify AFTER the deploy"; run verify; echo "   -> exit $?"
echo; echo "################ deploy again (must say ALREADY DEPLOYED and verify)"; run deploy; echo "   -> exit $?"
echo; echo "== sim state: prod HEAD $(git -C "$SIM/opt/icb-platform" rev-parse --short HEAD), describe $(git -C "$SIM/opt/icb-platform" describe --tags --abbrev=0 HEAD 2>/dev/null), alembic $(cat "$SIMSTATE/alembic"), record '$(cat "$SIM/vartmp/icb-deploy-state")'"
echo "== backups: $(ls "$SIM/varbackups/postgres" | tr '\n' ' ')  (the kit's pg_dump ran at alembic $(cat "$SIMSTATE/backup_at_alembic" 2>/dev/null || echo -); icb-pg-backup runs: $(wc -l < "$SIMSTATE/pgbackup.log" 2>/dev/null || echo 0)); npm builds: $(wc -l < "$SIMSTATE/npm.log" 2>/dev/null || echo 0)"
echo "== root-owned __pycache__ the kit left in the repo (want 0): $(find "$SIM/opt/icb-platform" -name __pycache__ -newer "$SIMSTATE/target" | wc -l)"
