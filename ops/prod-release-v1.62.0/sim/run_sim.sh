#!/bin/bash
# v1.62.0 release-kit simulation, run as root in WSL:  bash run_sim.sh <scenario> [kit-branch]
# Scenarios: happy | moved | wrongplace | wrongdb | staleboot | unstamped | nobackup | pgdumpfail | traceback |
#            routeopen | cfstale | cfcached | resume | saved | factor | autologin | noenv | notag
#            quotes | quoteschanged   (the close's read-only quotes check after 3 saves; and with a changed row)
# Builds a throw-away prod (sim/fakeprod.sh: v1.61.1 5511355 with the v1.61.1 tag but WITHOUT v1.62.0, as the real VM)
# and runs the STAGED kit — staged by the real mkstage_window.sh (and through it mkstage.sh) from a sim origin whose
# backport/v1.39-base carries the kit branch and an annotated v1.62.0 tag. The REAL deploy/prod/icb-deploy.sh runs;
# systemd, postgres, curl, sudo, npm and the venv are stubs (sim/stubs.sh). The three doors answer for the code the
# fake service RUNS; Cloudflare keeps the first bytes it fetched per /static URL. The kit is stamped as the copy line
# stamps it (KIT_DIR/.staged_at), except where a scenario tests the reboot guard. The folder is removed at the end.
set -u
SCEN=${1:-happy}
KIT=${2:-rt9/release-v1.62.0}
REPO=/mnt/c/Users/micge/Documents/icb-platform
SIM=/root/rt9relsim-$SCEN-$(date +%s)
HERE=$(cd "$(dirname "$0")" && pwd)
[ -e "$SIM" ] && { echo "exists: $SIM"; exit 1; }
mkdir -p "$SIM"
trap 'rm -rf "$SIM"' EXIT
case "$SCEN" in wrongplace) HOSTNAME_SIM=icb-mes-dev ;; esac
# shellcheck disable=SC1091
. "$HERE/fakeprod.sh"

echo "== the sim origin, the stage (the real mkstage_window.sh), the fake prod at v1.61.1"
fp_origin || exit 1
fp_stage || exit 1
fp_prod || exit 1
tar -xf "$SIM/stageout/window/icb-release-v1.62.0.tar" -C "$SIM/tmp" || exit 1
KITD=$SIM/tmp/icb-release-v1.62.0
BOOT=$(awk '/^btime/{print $2}' /proc/stat)
case "$SCEN" in
  staleboot) echo $((BOOT - 60)) > "$KITD/.staged_at" ;;     # copied before the (simulated) last boot
  unstamped) ;;                                                 # never stamped by the copy line
  *) date +%s > "$KITD/.staged_at" ;;                           # what rt9_vm.sh unpack writes
esac
grep -E '^(N_PROBES|NEW_PROBES|CALC_V|CALC_V_PREV)=' "$KITD/expected.env" | sed 's/^/   /'
case "$SCEN" in
  factor) echo 1.317073170731707 > "$SIMSTATE/factor" ;;      # a hand-typed rounding: the pins would be off
  wrongdb) echo icb > "$SIMSTATE/dbname" ;;
  traceback) touch "$SIMSTATE/traceback" ;;
  notag) git -C "$SIM/origin.git" tag -d v1.62.0 > /dev/null && echo "   (notag) the tag is removed from origin after staging" ;;
  resume) touch "$SIMSTATE/fail_restart" ;;
  nobackup) touch "$SIMSTATE/backup_no_calcs" ;;
  pgdumpfail) touch "$SIMSTATE/fail_pgdump" ;;
  cfstale) touch "$SIMSTATE/cfstale" ;;
  routeopen) touch "$SIMSTATE/routeopen" ;;
  autologin) sed -i 's/^MES_DEMO_AUTOLOGIN_USER=$/MES_DEMO_AUTOLOGIN_USER=admin/' "$SIM/etc/icb/backend.env" ;;
  noenv) sed -i '/^ICB_ENVIRONMENT=/d' "$SIM/etc/icb/backend.env" ;;
esac
R="sudo bash /tmp/icb-release-v1.62.0/release.sh"

echo; echo "################ preflight"; fp_run "$R preflight"; echo "   -> exit $?"
echo; echo "################ verify BEFORE the deploy (must fail on exactly the not-yet-deployed checks)"; fp_run "$R verify"; echo "   -> exit $?"
echo "== Cloudflare asked for calculator.js?v=191 before the deploy (want 0): $(grep -c 'mes.icecoldgrp.online/static/js/calculator.js?v=191' "$SIMSTATE/curl.log")"
if [ "$SCEN" = cfcached ]; then   # someone (a browser, an unguarded kit) asked Cloudflare for the NEW ?v= too early
  fp_run "curl -ksS https://mes.icecoldgrp.online/static/js/calculator.js?v=191 > /dev/null" && echo "   (cfcached) the edge now holds v1.61.1's bytes under ?v=191"
fi
[ "$SCEN" = moved ] && git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit on prod"
echo; echo "################ deploy"; fp_run "$R deploy"; echo "   -> exit $?"
if [ "$SCEN" = resume ]; then
  rm -f "$SIMSTATE/fail_restart"
  echo; echo "################ deploy AGAIN after the failure (must RESUME and pass)"; fp_run "$R deploy"; echo "   -> exit $?"
fi
[ "$SCEN" = saved ] && echo "73 9a8b7c6d5e4f30211203f4e5d6c7b8a9" > "$SIMSTATE/quotes" && echo "   (saved) a quote is saved after the deploy"
echo; echo "################ verify AFTER the deploy (and the acceptance)"; fp_run "$R verify"; echo "   -> exit $?"
if [ "$SCEN" = quotes ] || [ "$SCEN" = quoteschanged ]; then
  # the close: staged now (it pins the deploy's backup); 3 costings saved after the deploy, and, for the negative
  # control, one deploy-time row changed too (the repair's contact_name: the filter names the column, never the value)
  fp_stage_close || exit 1
  touch "$SIMSTATE/saved3"; [ "$SCEN" = quoteschanged ] && touch "$SIMSTATE/changed"
  tar -xf "$SIM/stageout/close/icb-rt9-quotes.tar" -C "$SIM/tmp" && date +%s > "$SIM/tmp/icb-rt9-quotes/.staged_at" || exit 1
  echo; echo "################ the close's quotes check: 3 rows saved after the deploy$( [ "$SCEN" = quoteschanged ] && echo ', and a deploy-time row changed')"
  fp_run "sudo bash /tmp/icb-rt9-quotes/rt9_quotes.sh"; echo "   -> exit $?"
  echo "== G4: contact or customer names in the kit's output (want 0): $(cat "$SIM"/tmp/icb-rt9-quotes/out-*/rows.txt "$SIM"/tmp/icb-rt9-quotes/out-*/run.log 2>/dev/null | grep -c -E 'Person|Example Farming|Never Printed')"
  echo "== nothing extracted to the fake /tmp by the check (want only out-*): $(cd "$SIM/tmp/icb-rt9-quotes" && ls -A | grep -v -E '^(out-|lib$|\.staged_at$|SHA256SUMS$|expected\.env$|rt9_quotes\.sh$|rt9_quotes_filter\.py$)' | tr '\n' ' ')"
fi
echo; echo "################ deploy again (must say ALREADY DEPLOYED and verify)"; fp_run "$R deploy"; echo "   -> exit $?"
echo; echo "== sim state: prod HEAD $(git -C "$SIM/opt/icb-platform" rev-parse --short HEAD), describe $(git -C "$SIM/opt/icb-platform" describe --tags --abbrev=0 HEAD 2>/dev/null), alembic $(cat "$SIMSTATE/alembic"), record '$(cat "$SIM/vartmp/icb-deploy-state")', spa $(grep -o 'index-[A-Za-z0-9_-]*' "$SIM/opt/icb-platform/frontend/dist/index.html")"
echo "== backups: $(ls "$SIM/varbackups/postgres" | tr '\n' ' ')  (the kit's pg_dump ran at alembic $(cat "$SIMSTATE/backup_at_alembic" 2>/dev/null || echo -)); npm builds: $(cat "$SIMSTATE/npm.log" 2>/dev/null | wc -l)"
echo "== the doors, in the order the kit asked (first request per door for /health/version): $(grep '/health/version' "$SIMSTATE/curl.log" | sed -E 's#^GET https://([^/]*)/.*#\1#' | awk '!s[$0]++' | tr '\n' ' ')"
echo "== root-owned __pycache__ the kit left in the repo (want 0): $(find "$SIM/opt/icb-platform" -name __pycache__ -newer "$SIMSTATE/target" | wc -l)"
