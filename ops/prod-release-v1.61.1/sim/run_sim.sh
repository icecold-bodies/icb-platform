#!/bin/bash
# v1.61.1 release-kit simulation, run as root in WSL:  bash run_sim.sh <scenario> [kit-branch]
# Scenarios: happy | factor | notag | moved | traceback | resume | nobackup | pgdumpfail | cfstale | autologin |
#            wrongplace | staleboot | unstamped | noenv
# Builds a throw-away prod (repo at v1.61.0 5e37b0a with the v1.61.0 tag but WITHOUT v1.61.1, as the real VM; fake
# venv / dist / env / backups / deploy record; a fake database at alembic 0053 with the 4G factor) under $SIM and runs
# the STAGED kit (built by the real mkstage.sh from a sim origin whose backport/v1.39-base carries the RT7 branch, and
# an annotated v1.61.1 tag) inside private mount + UTS namespaces (hostname icb-mes-prod) where /opt, /etc, /var/tmp,
# /var/backups and /tmp are bind-mounted from $SIM — nothing outside $SIM is touched, and the folder is removed at the
# end (the WSL disk lesson). The REAL deploy/prod/icb-deploy.sh runs; systemd, postgres, curl, sudo, npm and the venv
# are stubs. The three doors answer for the code the fake service RUNS. The kit is stamped as the copy line stamps it
# (KIT_DIR/.staged_at), except where a scenario tests the reboot guard.
set -u
SCEN=${1:-happy}
KIT=${2:-rt7/audit-truth}
WIN=/mnt/c/Users/micge/Documents
REPO=$WIN/icb-platform
SIM=/root/relsim8-$SCEN-$(date +%s)
G="git -c safe.directory=*"
PREV=$($G -C "$REPO" rev-parse "v1.61.0^{commit}")
[ "${PREV:0:7}" = 5e37b0a ] || { echo "SIM: v1.61.0 is ${PREV:0:7}, prod runs 5e37b0a"; exit 1; }
[ -e "$SIM" ] && { echo "exists: $SIM"; exit 1; }
mkdir -p "$SIM"/{bin,work,opt,vartmp,varbackups/postgres,tmp,state,stageout}
trap 'rm -rf "$SIM"' EXIT
export SIMSTATE=$SIM/state

echo "== the sim origin: backport/v1.39-base + $KIT (merge), annotated tag v1.61.1"
$G clone -q --bare --single-branch --branch backport/v1.39-base "$REPO" "$SIM/origin.git" || exit 1
$G -C "$SIM/origin.git" fetch -q "$REPO" "+refs/remotes/origin/backport/v1.39-base:refs/heads/backport/v1.39-base" || exit 1
$G -C "$SIM/origin.git" fetch -q "$REPO" "+refs/tags/v1.61.0:refs/tags/v1.61.0" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" || exit 1
cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$REPO" "$KIT" || exit 1
git -c user.email=sim@x -c user.name=sim merge -q --no-edit FETCH_HEAD || exit 1
git push -q origin backport/v1.39-base && git fetch -q origin --tags
TARGET=$(git rev-parse HEAD); echo "$TARGET" > "$SIMSTATE/target"
git -c user.email=sim@x -c user.name=sim tag -f -a v1.61.1 -m "sim v1.61.1" "$TARGET" > /dev/null && git push -q -f origin v1.61.1
echo "   prev ${PREV:0:7}  target ${TARGET:0:7}  tag $(git rev-parse v1.61.1 | cut -c1-12)"

echo "== stage the kit with the real mkstage.sh"
bash ops/prod-release-v1.61.1/mkstage.sh "$SIM/stageout" "$TARGET" "$PREV" | grep -E '^staged|^audit:|^LIST|^PAIR|^GOLDEN|^FACTOR|^N_PROBES|^STOP' || true
[ -f "$SIM/stageout/icb-release-v1.61.1.tar" ] || { echo "SIM: mkstage produced no tar"; exit 1; }
tar -xf "$SIM/stageout/icb-release-v1.61.1.tar" -C "$SIM/tmp" || exit 1
KITD=$SIM/tmp/icb-release-v1.61.1
BOOT=$(awk '/^btime/{print $2}' /proc/stat)
case "$SCEN" in
  staleboot) echo $((BOOT - 60)) > "$KITD/.staged_at" ;;     # copied before the (simulated) last boot
  unstamped) ;;                                                 # never stamped by the copy line
  *) date +%s > "$KITD/.staged_at" ;;                           # what run_window_copy.ps1 writes after unpacking
esac
: > "$SIMSTATE/absent_prev"; : > "$SIMSTATE/absent_target"      # v1.61.1 adds and removes no route

echo "== the fake prod at ${PREV:0:7}"
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" || exit 1
cd "$SIM/opt/icb-platform" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base "$PREV" && git branch -q -u origin/backport/v1.39-base
git tag -d v1.61.1 > /dev/null 2>&1
echo "   prod describe: $(git describe --tags --abbrev=0 HEAD)"
mkdir -p frontend/dist/assets frontend/node_modules .venv/bin
echo 'console.log("spa v1.61.0")' > frontend/dist/assets/index-BBI2d9Oo.js
echo '<script type="module" src="/mes-app/assets/index-BBI2d9Oo.js"></script>' > frontend/dist/index.html
cat > .venv/bin/python <<'EOF'
#!/bin/bash
# the deployed audit list, read as the real tool would (release.sh's list_report sends a program on stdin)
if [ "${1:-}" = - ]; then
  prog=$(cat)
  case "$prog" in *load_accepted_doc*)
    R=/opt/icb-platform/backend
    grep -q 'def load_accepted_doc' "$R/tools/costing_audit/accepted.py" \
      || { echo "ImportError: cannot import name 'load_accepted_doc' from 'tools.costing_audit.accepted'"; exit 1; }
    L=$R/tests/costing_audit/accepted_differences.prod.yaml
    n=$(grep -c '^- body:' "$L"); pair=$(sed -n 's/^ *snapshot_sha256: *\([0-9a-f]*\).*/\1/p' "$L" | head -n1)
    have=$(tr -d '\r' < "$R/tests/costing_audit/mes_snapshot/all.json" | sha256sum | cut -d' ' -f1)
    [ "$pair" = "$have" ] && echo "$n $pair pair=snapshot" || echo "$n $pair pair!=snapshot"
    exit 0 ;;
  esac
  echo "python stub: unknown stdin program"; exit 4
fi
case "$*" in
  *"import yaml"*) echo 6.0.2 ;;
  --version) echo "Python 3.12.3" ;;
  *) exec python3 "$@" ;;
esac
EOF
cat > .venv/bin/alembic <<'EOF'
#!/bin/bash
# v1.61.1 migrates nothing: icb-deploy.sh's RESUME path still runs `alembic upgrade head` (a no-op at head)
case "$1" in
  upgrade) echo "INFO  [alembic] (stub) already at head $(cat "$SIMSTATE/alembic")" ;;
  current) echo "$(cat "$SIMSTATE/alembic") (head)" ;;
esac
EOF
chmod +x .venv/bin/*
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo "export PATH=$SIM/bin:\$PATH SIMSTATE=$SIMSTATE" >> "$SIM/etc/profile"
# prod's env file since RT6: ICB_ENVIRONMENT=prod; MES_DEMO_AUTOLOGIN_USER present and EMPTY; a duplicate key
printf '%s\n' 'DATABASE_URL=postgresql+psycopg://icb_app:sim-not-real@127.0.0.1:5432/icb_platform' \
  'SESSION_SECRET=sim-not-real' 'SMTP_URL=' 'SMTP_URL=smtp://x' 'MES_DEMO_AUTOLOGIN_USER=' 'ICB_ENVIRONMENT=prod' > "$SIM/etc/icb/backend.env"
chmod 600 "$SIM/etc/icb/backend.env"
echo "completed $PREV" > "$SIM/vartmp/icb-deploy-state"
echo x > "$SIM/varbackups/postgres/icb_platform_20261019-0230.dump.gz"
echo 0053 > "$SIMSTATE/alembic"; echo 1.3170731707317074 > "$SIMSTATE/factor"
echo 34561 > "$SIMSTATE/pid"; echo "Wed 2026-10-15 13:01:18 SAST" > "$SIMSTATE/aet"
echo "$PREV" > "$SIMSTATE/live_code"; echo prod > "$SIMSTATE/live_env"
sleep 3
awk '{ printf "%d\n", $1 * 1000000 }' /proc/uptime > "$SIMSTATE/mono"
now=$(date +%s); : > "$SIMSTATE/journal"; for i in 1 2 3 4; do echo "$now INFO:     Application startup complete." >> "$SIMSTATE/journal"; done
sleep 3
bash "$SIM/work/ops/prod-release-v1.61.1/sim/stubs.sh" "$SIM/bin"
HOSTNAME_SIM=icb-mes-prod
case "$SCEN" in
  factor) echo 1.317073170731707 > "$SIMSTATE/factor" ;;      # a hand-typed rounding: the pins would be off
  traceback) touch "$SIMSTATE/traceback" ;;
  notag) git -C "$SIM/origin.git" tag -d v1.61.1 > /dev/null && echo "   (notag) the tag is removed from origin after staging" ;;
  resume) touch "$SIMSTATE/fail_restart" ;;
  nobackup) touch "$SIMSTATE/backup_no_calcs" ;;
  pgdumpfail) touch "$SIMSTATE/fail_pgdump" ;;
  cfstale) touch "$SIMSTATE/cfstale" ;;
  autologin) sed -i 's/^MES_DEMO_AUTOLOGIN_USER=$/MES_DEMO_AUTOLOGIN_USER=admin/' "$SIM/etc/icb/backend.env" ;;
  noenv) sed -i '/^ICB_ENVIRONMENT=/d' "$SIM/etc/icb/backend.env" ;;
  wrongplace) HOSTNAME_SIM=icb-mes-dev ;;
esac

run() { # the staged kit inside private mount + UTS namespaces, as prod would (1 s apart: each run's folder is per-second)
  sleep 1
  unshare -m -u bash -c "
    hostname '$HOSTNAME_SIM' &&
    mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/vartmp' /var/tmp &&
    mount --bind '$SIM/varbackups' /var/backups && mount --bind '$SIM/tmp' /tmp &&
    export PATH='$SIM/bin':\$PATH SIMSTATE='$SIMSTATE' && bash /tmp/icb-release-v1.61.1/release.sh $1"
}
echo; echo "################ preflight"; run preflight; echo "   -> exit $?"
echo; echo "################ verify BEFORE the deploy (must fail on exactly the not-yet-deployed checks)"; run verify; echo "   -> exit $?"
[ "$SCEN" = moved ] && git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit on prod"
echo; echo "################ deploy"; run deploy; echo "   -> exit $?"
if [ "$SCEN" = resume ]; then
  rm -f "$SIMSTATE/fail_restart"
  echo; echo "################ deploy AGAIN after the failure (must RESUME and pass)"; run deploy; echo "   -> exit $?"
fi
echo; echo "################ verify AFTER the deploy"; run verify; echo "   -> exit $?"
echo; echo "################ deploy again (must say ALREADY DEPLOYED and verify)"; run deploy; echo "   -> exit $?"
echo; echo "== sim state: prod HEAD $(git -C "$SIM/opt/icb-platform" rev-parse --short HEAD), describe $(git -C "$SIM/opt/icb-platform" describe --tags --abbrev=0 HEAD 2>/dev/null), alembic $(cat "$SIMSTATE/alembic"), record '$(cat "$SIM/vartmp/icb-deploy-state")', spa $(grep -o 'index-[A-Za-z0-9_-]*' "$SIM/opt/icb-platform/frontend/dist/index.html")"
echo "== backups: $(ls "$SIM/varbackups/postgres" | tr '\n' ' ')  (the kit's pg_dump ran at alembic $(cat "$SIMSTATE/backup_at_alembic" 2>/dev/null || echo -)); npm builds: $(cat "$SIMSTATE/npm.log" 2>/dev/null | wc -l)"
echo "== root-owned __pycache__ the kit left in the repo (want 0): $(find "$SIM/opt/icb-platform" -name __pycache__ -newer "$SIMSTATE/target" | wc -l)"
