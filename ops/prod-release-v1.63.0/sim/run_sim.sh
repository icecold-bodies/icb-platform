#!/bin/bash
# v1.63.0 release-kit simulation, run as root in WSL:  bash run_sim.sh <scenario> [kit-branch]
# Scenarios: happy | moved | wrongplace | wrongdb | staleboot | unstamped | nobackup | pgdumpfail | traceback |
#            routeopen | cfstale | cfcached | resume | saved | deleted | factor | autologin | noenv | notag |
#            nonpm | nobuild | weasyprint (the venv gains it after the deploy: verify FAILs) |
#            weasyprintpre (it is there before: preflight FAILs, the deploy STOPs before anything moves)
# Builds a throw-away prod (sim/fakeprod.sh: v1.62.0 a29db35 with the v1.62.0 tag but WITHOUT v1.63.0, as the real VM;
# sticky /tmp, uid 1500 for the ssh user) and runs the STAGED kit — staged by the real mkstage_window.sh (and through
# it mkstage.sh) from a sim origin whose backport/v1.39-base carries the kit branch and an annotated v1.63.0 tag. The
# REAL deploy/prod/icb-deploy.sh runs; systemd, postgres, curl, sudo, npm and the venv are stubs (sim/stubs.sh). The
# three doors answer for the code the fake service RUNS; Cloudflare keeps the first bytes it fetched per /static and
# /mes-app/assets URL. The kit is unpacked as the ssh user would (owned by uid 1500) and stamped as the copy line
# stamps it (KIT_DIR/.staged_at), except where a scenario tests the reboot guard. The folder is removed at the end.
set -u
SCEN=${1:-happy}
KIT=${2:-rt12/release-v1.63.0}
REPO=/mnt/c/Users/micge/Documents/icb-platform
SIM=/root/rt12relsim-$SCEN-$(date +%s)
HERE=$(cd "$(dirname "$0")" && pwd)
[ -e "$SIM" ] && { echo "exists: $SIM"; exit 1; }
mkdir -p "$SIM"
trap 'rm -rf "$SIM"' EXIT
case "$SCEN" in wrongplace) HOSTNAME_SIM=icb-mes-dev ;; esac
# shellcheck disable=SC1091
. "$HERE/fakeprod.sh"

echo "== the sim origin, the stage (the real mkstage_window.sh), the fake prod at v1.62.0"
fp_origin || exit 1
fp_stage || exit 1
fp_prod || exit 1
tar -xf "$SIM/stageout/window/icb-release-v1.63.0.tar" -C "$SIM/tmp" || exit 1
KITD=$SIM/tmp/icb-release-v1.63.0
BOOT=$(awk '/^btime/{print $2}' /proc/stat)
case "$SCEN" in
  staleboot) echo $((BOOT - 60)) > "$KITD/.staged_at" ;;     # copied before the (simulated) last boot
  unstamped) ;;                                                 # never stamped by the copy line
  *) date +%s > "$KITD/.staged_at" ;;                           # what rt12_vm.sh unpack writes
esac
chown -R "$SIM_UID:$SIM_UID" "$KITD"                             # unpacked by the ssh user, as on prod
grep -E '^(N_PROBES|NEW_PROBES|N_FRONTEND|STATIC_1|STATIC_2|SPA_MARK)=' "$KITD/expected.env" | sed 's/^/   /'
case "$SCEN" in
  factor) echo 1.317073170731707 > "$SIMSTATE/factor" ;;      # a hand-typed rounding: the pins would be off
  wrongdb) echo icb > "$SIMSTATE/dbname" ;;
  traceback) touch "$SIMSTATE/traceback" ;;
  notag) git -C "$SIM/origin.git" tag -d v1.63.0 > /dev/null && echo "   (notag) the tag is removed from origin after staging" ;;
  resume) touch "$SIMSTATE/fail_restart" ;;
  nobackup) touch "$SIMSTATE/backup_no_calcs" ;;
  pgdumpfail) touch "$SIMSTATE/fail_pgdump" ;;
  cfstale) touch "$SIMSTATE/cfstale" ;;
  routeopen) touch "$SIMSTATE/routeopen" ;;
  autologin) sed -i 's/^MES_DEMO_AUTOLOGIN_USER=$/MES_DEMO_AUTOLOGIN_USER=admin/' "$SIM/etc/icb/backend.env" ;;
  noenv) sed -i '/^ICB_ENVIRONMENT=/d' "$SIM/etc/icb/backend.env" ;;
  nonpm) rm -rf "$SIM/opt/icb-platform/frontend/node_modules" && echo "   (nonpm) frontend/node_modules removed from the fake prod" ;;
  nobuild) touch "$SIMSTATE/npm_noop" && echo "   (nobuild) npm run build will do nothing" ;;
  weasyprintpre) touch "$SIMSTATE/weasyprint" && echo "   (weasyprintpre) the fake venv already holds weasyprint" ;;
esac
chmod 666 "$SIMSTATE"/* 2>/dev/null
R="sudo bash /tmp/icb-release-v1.63.0/release.sh"

echo; echo "################ preflight"; fp_run "$R preflight"; echo "   -> exit $?"
echo; echo "################ verify BEFORE the deploy (must fail on exactly the not-yet-deployed checks)"; fp_run "$R verify"; echo "   -> exit $?"
echo "== Cloudflare asked for calculator.js?v=192 or calculator2.js?v=129 before the deploy (want 0): $(grep -cE 'mes.icecoldgrp.online/static/js/calculator2?.js\?v=(192|129)' "$SIMSTATE/curl.log")"
if [ "$SCEN" = cfcached ]; then   # someone (a browser, an unguarded kit) asked Cloudflare for the NEW ?v= too early
  fp_root "curl -ksS https://mes.icecoldgrp.online/static/js/calculator.js?v=192 > /dev/null" && echo "   (cfcached) the edge now holds v1.62.0's bytes under ?v=192"
fi
[ "$SCEN" = moved ] && git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit on prod"
echo; echo "################ deploy"; fp_run "$R deploy"; echo "   -> exit $?"
if [ "$SCEN" = resume ]; then
  rm -f "$SIMSTATE/fail_restart"
  echo; echo "################ deploy AGAIN after the failure (must RESUME and pass)"; fp_run "$R deploy"; echo "   -> exit $?"
fi
[ "$SCEN" = saved ] && touch "$SIMSTATE/saved3" && echo "   (saved) three N10022 revisions are saved after the deploy"
[ "$SCEN" = deleted ] && touch "$SIMSTATE/deleted" && echo "   (deleted) the repair row 1107 is soft-deleted after the deploy"
[ "$SCEN" = weasyprint ] && touch "$SIMSTATE/weasyprint" && echo "   (weasyprint) the fake venv gains weasyprint after the deploy (RT12_RULING_1: a STOP)"
echo; echo "################ verify AFTER the deploy (and the acceptance)"; fp_run "$R verify"; echo "   -> exit $?"
echo; echo "################ deploy again (must say ALREADY DEPLOYED and verify)"; fp_run "$R deploy"; echo "   -> exit $?"
echo; echo "== sim state: prod HEAD $(git -C "$SIM/opt/icb-platform" rev-parse --short HEAD), describe $(git -C "$SIM/opt/icb-platform" describe --tags --abbrev=0 HEAD 2>/dev/null), alembic $(cat "$SIMSTATE/alembic"), record '$(cat "$SIM/vartmp/icb-deploy-state")', spa $(grep -o 'index-[A-Za-z0-9_-]*' "$SIM/opt/icb-platform/frontend/dist/index.html")"
echo "== backups: $(ls "$SIM/varbackups/postgres" | tr '\n' ' ')  (the kit's pg_dump ran at alembic $(cat "$SIMSTATE/backup_at_alembic" 2>/dev/null || echo -)); npm builds: $(cat "$SIMSTATE/npm.log" 2>/dev/null | wc -l)"
echo "== the doors, in the order the kit asked (first request per door for /health/version): $(grep '/health/version' "$SIMSTATE/curl.log" | sed -E 's#^GET https://([^/]*)/.*#\1#' | awk '!s[$0]++' | tr '\n' ' ')"
echo "== root-owned __pycache__ the kit left in the repo (want 0): $(find "$SIM/opt/icb-platform" -name __pycache__ -newer "$SIMSTATE/target" | wc -l)"
echo "== 'Permission denied' anywhere in the kit's out folders (sticky /tmp, protected_regular=$(sysctl -n fs.protected_regular 2>/dev/null || echo ?); want 0): $(cat "$KITD"/out-*/run.log 2>/dev/null | grep -c 'Permission denied *$')"   # an error ends the line; #231's commit subject quotes the words mid-line
echo "== files the kit wrote directly in /tmp (want none): $(cd "$SIM/tmp" && ls -A | grep -v -E '^icb-release-v1\.63\.0$|^icb-rollback-[0-9-]+\.txt$' | tr '\n' ' ')"
echo "== 'exception line not found' in the kit's out folders (want 0): $(cat "$KITD"/out-*/run.log 2>/dev/null | grep -c 'exception line not found')"
echo "== pip mentioned anywhere in the kit's out folders (want 0): $(cat "$KITD"/out-*/run.log "$KITD"/out-*/icb-deploy*.txt 2>/dev/null | grep -ciE 'pip (install|sync)')"
echo "== 'dependency manifests changed (1)' in the deploy's captured outputs (want 2: the dry run and the deploy): $(cat "$KITD"/out-deploy-*/icb-deploy-dryrun.txt "$KITD"/out-deploy-*/icb-deploy.txt 2>/dev/null | grep -c 'dependency manifests changed (1)')"
