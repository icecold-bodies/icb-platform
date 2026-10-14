#!/bin/bash
# v1.61.0 release-kit simulation, run as root in WSL:  bash run_sim.sh <scenario> [kit-branch]
# Scenarios: happy | notag | moved | bootfail | traceback | stalecache | resume | migfail | nobackup | cfstale |
#            famchanged | autologin | noenv | envother | wrongplace | nobuild | pgdumpfail
# Builds a throw-away prod (repo at v1.60.2 a429404 with the v1.60.2 tag but WITHOUT v1.61.0, as the real VM; fake
# venv / dist / env / backups / deploy record; a fake database at alembic 0052) under $SIM and runs the STAGED kit (built
# by the real mkstage.sh from a sim origin whose backport/v1.39-base carries the RT6 branch, and an annotated v1.61.0
# tag) inside private mount + UTS namespaces (hostname icb-mes-prod) where /opt, /etc, /var/tmp, /var/backups and /tmp
# are bind-mounted from $SIM — nothing outside $SIM is touched, and the folder is removed at the end (the RT4 disk
# lesson). The REAL deploy/prod/icb-deploy.sh runs, its migration and SPA build steps included; systemd, postgres,
# alembic, curl, sudo, npm and the venv are stubs. The three doors answer for the code the fake service RUNS.
set -u
SCEN=${1:-happy}
KIT=${2:-rt6/enforce}
WIN=/mnt/c/Users/micge/Documents
REPO=$WIN/icb-platform
SIM=/root/relsim7-$SCEN-$(date +%s)
G="git -c safe.directory=*"
PREV=$($G -C "$REPO" rev-parse "v1.60.2^{commit}")
[ "${PREV:0:7}" = a429404 ] || { echo "SIM: v1.60.2 is ${PREV:0:7}, prod runs a429404"; exit 1; }
[ -e "$SIM" ] && { echo "exists: $SIM"; exit 1; }
mkdir -p "$SIM"/{bin,work,opt,vartmp,varbackups/postgres,tmp,state,stageout}
trap 'rm -rf "$SIM"' EXIT
export SIMSTATE=$SIM/state

echo "== the sim origin: backport/v1.39-base + $KIT (merge), annotated tag v1.61.0"
$G clone -q --bare --single-branch --branch backport/v1.39-base "$REPO" "$SIM/origin.git" || exit 1
$G -C "$SIM/origin.git" fetch -q "$REPO" "+refs/remotes/origin/backport/v1.39-base:refs/heads/backport/v1.39-base" || exit 1
$G -C "$SIM/origin.git" fetch -q "$REPO" "+refs/tags/v1.60.2:refs/tags/v1.60.2" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" || exit 1
cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$REPO" "$KIT" || exit 1
git -c user.email=sim@x -c user.name=sim merge -q --no-edit FETCH_HEAD || exit 1
git push -q origin backport/v1.39-base && git fetch -q origin --tags
TARGET=$(git rev-parse HEAD); echo "$TARGET" > "$SIMSTATE/target"
git -c user.email=sim@x -c user.name=sim tag -f -a v1.61.0 -m "sim v1.61.0" "$TARGET" > /dev/null && git push -q -f origin v1.61.0
echo "   prev ${PREV:0:7}  target ${TARGET:0:7}  tag $(git rev-parse v1.61.0 | cut -c1-12)"

echo "== stage the kit with the real mkstage.sh"
bash ops/prod-release-v1.61.0/mkstage.sh "$SIM/stageout" "$TARGET" "$PREV" | grep -E '^staged|^STATIC|^ALEMBIC|^SPA_MARK|^N_PROBES|^EXPECT|^STOP' || true
[ -f "$SIM/stageout/icb-release-v1.61.0.tar" ] || { echo "SIM: mkstage produced no tar"; exit 1; }
tar -xf "$SIM/stageout/icb-release-v1.61.0.tar" -C "$SIM/tmp" || exit 1
git cat-file blob "$PREV:backend/app/static/js/calculator.js" > "$SIMSTATE/calc_prev.js"

echo "== the fake prod at ${PREV:0:7}"
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" || exit 1
cd "$SIM/opt/icb-platform" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base "$PREV" && git branch -q -u origin/backport/v1.39-base
git tag -d v1.61.0 > /dev/null 2>&1
echo "   prod describe: $(git describe --tags --abbrev=0 HEAD)"
mkdir -p frontend/dist/assets frontend/node_modules .venv/bin
echo 'console.log("spa v1.60.2")' > frontend/dist/assets/index-Bd_exvgd.js
echo '<script type="module" src="/mes-app/assets/index-Bd_exvgd.js"></script>' > frontend/dist/index.html
cat > .venv/bin/python <<'EOF'
#!/bin/bash
a="$*"
case "$a" in
  *"import yaml"*) echo 6.0.2 ;;
  *insulation_rules*)
    if [ -f /opt/icb-platform/backend/app/services/insulation_rules.py ]; then
      [ "${ICB_ENVIRONMENT:-}" = prod ] && echo "6 True" || echo "6 False"
    else echo "ModuleNotFoundError: No module named 'app.services.insulation_rules'"; fi ;;
  --version) echo "Python 3.12.3" ;;
  *) exec python3 "$@" ;;
esac
EOF
cat > .venv/bin/alembic <<'EOF'
#!/bin/bash
S=$SIMSTATE
case "$1" in
  upgrade) [ -f "$S/fail_migrate" ] && { echo "ERROR [alembic] (stub) the migration failed"; exit 1; }
           if [ "$(cat "$S/alembic")" = 0053 ]; then echo "INFO  [alembic] (stub) already at head"
           else echo "INFO  [alembic.runtime.migration] Running upgrade 0052 -> 0053, Body families: a machine-readable insulation rule"; echo 0053 > "$S/alembic"; fi ;;
  current) echo "$(cat "$S/alembic") (head)" ;;
esac
EOF
chmod +x .venv/bin/*
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo "export PATH=$SIM/bin:\$PATH SIMSTATE=$SIMSTATE" >> "$SIM/etc/profile"
# prod's env file: root:icb 600, a duplicate key, no ICB_ENVIRONMENT, MES_DEMO_AUTOLOGIN_USER present and EMPTY
printf '%s\n' 'DATABASE_URL=postgresql+psycopg://icb_app:sim-not-real@127.0.0.1:5432/icb_platform' \
  'SESSION_SECRET=sim-not-real' 'SMTP_URL=' 'SMTP_URL=smtp://x' 'MES_DEMO_AUTOLOGIN_USER=' > "$SIM/etc/icb/backend.env"
chmod 600 "$SIM/etc/icb/backend.env"
echo "completed $PREV" > "$SIM/vartmp/icb-deploy-state"
echo x > "$SIM/varbackups/postgres/icb_platform_20261006-0230.dump.gz"
echo 0052 > "$SIMSTATE/alembic"; echo 152410 > "$SIMSTATE/pid"; echo "Mon 2026-10-06 07:20:09 SAST" > "$SIMSTATE/aet"
echo "$PREV" > "$SIMSTATE/live_code"; : > "$SIMSTATE/live_env"
sleep 3
awk '{ printf "%d\n", $1 * 1000000 }' /proc/uptime > "$SIMSTATE/mono"
now=$(date +%s); : > "$SIMSTATE/journal"; for i in 1 2 3 4; do echo "$now INFO:     Application startup complete." >> "$SIMSTATE/journal"; done
sleep 3
bash "$SIM/work/ops/prod-release-v1.61.0/sim/stubs.sh" "$SIM/bin"
HOSTNAME_SIM=icb-mes-prod
case "$SCEN" in
  bootfail) touch "$SIMSTATE/fail_bootstrap" ;;
  traceback) touch "$SIMSTATE/traceback" ;;
  stalecache) touch "$SIMSTATE/stalecache" ;;
  notag) git -C "$SIM/origin.git" tag -d v1.61.0 > /dev/null && echo "   (notag) the tag is removed from origin after staging" ;;
  resume) touch "$SIMSTATE/fail_restart" ;;
  migfail) touch "$SIMSTATE/fail_migrate" ;;
  nobackup) touch "$SIMSTATE/backup_no_calcs" ;;
  pgdumpfail) touch "$SIMSTATE/fail_pgdump" ;;
  cfstale) touch "$SIMSTATE/cfstale" ;;
  famchanged) touch "$SIMSTATE/famchanged" ;;
  nobuild) touch "$SIMSTATE/nobuild" ;;
  autologin) sed -i 's/^MES_DEMO_AUTOLOGIN_USER=$/MES_DEMO_AUTOLOGIN_USER=admin/' "$SIM/etc/icb/backend.env" ;;
  envother) echo 'ICB_ENVIRONMENT=dev' >> "$SIM/etc/icb/backend.env" ;;
  wrongplace) HOSTNAME_SIM=icb-mes-dev ;;
esac
cp -p "$SIM/etc/icb/backend.env" "$SIMSTATE/env_before"

run() { # the staged kit inside private mount + UTS namespaces, as prod would (1 s apart: each run's folder is per-second)
  sleep 1
  unshare -m -u bash -c "
    hostname '$HOSTNAME_SIM' &&
    mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/vartmp' /var/tmp &&
    mount --bind '$SIM/varbackups' /var/backups && mount --bind '$SIM/tmp' /tmp &&
    export PATH='$SIM/bin':\$PATH SIMSTATE='$SIMSTATE' && bash /tmp/icb-release-v1.61.0/release.sh $1"
}
echo; echo "################ preflight"; run preflight; echo "   -> exit $?"
echo; echo "################ verify BEFORE the deploy (must fail on exactly the not-yet-deployed checks)"; run verify; echo "   -> exit $?"
if [ "$SCEN" != noenv ]; then echo; echo "################ env (append ICB_ENVIRONMENT=prod by merge, read back)"; run env; echo "   -> exit $?"; fi
[ "$SCEN" = moved ] && git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit on prod"
echo; echo "################ deploy"; run deploy; echo "   -> exit $?"
if [ "$SCEN" = resume ] || [ "$SCEN" = migfail ]; then
  rm -f "$SIMSTATE/fail_restart" "$SIMSTATE/fail_migrate"
  echo; echo "################ deploy AGAIN after the failure (must RESUME and pass)"; run deploy; echo "   -> exit $?"
fi
echo; echo "################ verify AFTER the deploy"; run verify; echo "   -> exit $?"
echo; echo "################ env again (must say already set)"; run env; echo "   -> exit $?"
echo; echo "################ deploy again (must say ALREADY DEPLOYED and verify)"; run deploy; echo "   -> exit $?"
echo; echo "== sim state: prod HEAD $(git -C "$SIM/opt/icb-platform" rev-parse --short HEAD), describe $(git -C "$SIM/opt/icb-platform" describe --tags --abbrev=0 HEAD 2>/dev/null), alembic $(cat "$SIMSTATE/alembic"), record '$(cat "$SIM/vartmp/icb-deploy-state")', spa $(grep -o 'index-[A-Za-z0-9_-]*' "$SIM/opt/icb-platform/frontend/dist/index.html")"
echo "== env file: $(diff <(cat "$SIMSTATE/env_before") "$SIM/etc/icb/backend.env" | grep -c '^>') line(s) added: $(diff "$SIMSTATE/env_before" "$SIM/etc/icb/backend.env" | sed -n 's/^> //p' | tr '\n' ' '); earlier lines unchanged: $(head -c "$(stat -c %s "$SIMSTATE/env_before")" "$SIM/etc/icb/backend.env" | cmp -s - "$SIMSTATE/env_before" && echo yes || echo NO); mode $(stat -c %a "$SIM/etc/icb/backend.env")"
echo "== backups: $(ls "$SIM/varbackups/postgres" | tr '\n' ' ')  (the kit's pg_dump ran at alembic $(cat "$SIMSTATE/backup_at_alembic" 2>/dev/null || echo -)); npm builds: $(cat "$SIMSTATE/npm.log" 2>/dev/null | wc -l)"
echo "== root-owned __pycache__ the kit left in the repo (want 0): $(find "$SIM/opt/icb-platform" -name __pycache__ -newer "$SIMSTATE/target" | wc -l)"
