#!/bin/bash
# The v1.63.0 release-kit scenarios, one line each (run as root in WSL, from PowerShell — Git Bash mangles the path):
#     wsl -u root -- bash /mnt/c/Users/micge/Documents/icb-platform/ops/prod-release-v1.63.0/sim/run_all.sh [kit-branch] [scenario ...]
# (no scenario = all). A scenario passes when its log carries the expected lines in order. The scenario script is read
# from the kit branch itself — at the START of the batch, once: a branch that moves mid-batch does not change later
# scenarios' kit (RT9's lesson, 22 Oct). Each run removes its own /root/rt12relsim-* folder, and the origin cache at
# the end (the WSL disk lesson).
KIT=${1:-rt12/release-v1.63.0}; shift 2>/dev/null
ONLY=" $* "
REPO=/mnt/c/Users/micge/Documents/icb-platform
KITSHA=$(git -C "$REPO" -c safe.directory='*' rev-parse "$KIT^{commit}") || exit 1
D=$(mktemp -d); trap 'rm -rf "$D" /root/rt12sim-cache' EXIT
for f in run_sim.sh fakeprod.sh stubs.sh; do git -C "$REPO" -c safe.directory='*' show "$KITSHA:ops/prod-release-v1.63.0/sim/$f" > "$D/$f" || exit 1; done
echo "== kit $KIT = ${KITSHA:0:7} (every scenario stages from this commit)"
P=0; F=0
row() { # $1 scenario, $2 regex over the whole log
  [ "$ONLY" = "  " ] || [[ "$ONLY" == *" $1 "* ]] || return 0
  local log; log=$(bash "$D/run_sim.sh" "$1" "$KITSHA" 2>&1)
  mkdir -p /root/rt12sim-logs && printf '%s\n' "$log" > "/root/rt12sim-logs/$1.log"
  if [[ "$log" =~ $2 ]]; then echo "PASS  $1"; P=$((P+1)); else echo "FAIL  $1"; F=$((F+1)); echo "$log" | tail -n 60 | sed 's/^/      | /'; fi
}
# verify BEFORE the deploy fails on exactly: HEAD, TAG_LOCAL, DESCRIBE; V_ + DISK_ for the two statics (4);
# SPA_MARK_DISK; and per door VERSION_x, calculator.js_x, calculator2.js_x (not probed: the new bytes are not on disk)
# and SPA_MARK_x (0) — 3 + 4 + 1 + 3 x 4 = 20
VB=${VB:-20}
NL=$'\n'
FIRST='######## RT12 release v1.63.0 preflight · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head a29db35 · boot [0-9]{4}-'
PRE='pre-existing  [A-Z][a-z]{2} [0-9]{2} [0-9:]{8}  starlette.requests.ClientDisconnect'
# the chain of three before the service started (listed by the deploy's 14-day look-back, every class named)
CHAIN='pre-existing  [A-Z][a-z]{2} [0-9]{2} [0-9:]{8}  anyio.WouldBlock.*pre-existing  [A-Z][a-z]{2} [0-9]{2} [0-9:]{8}  anyio.EndOfStream.*pre-existing  [A-Z][a-z]{2} [0-9]{2} [0-9:]{8}  starlette.requests.ClientDisconnect'
row happy       "$FIRST.*PASS calculator.js_CF = [0-9a-f]{64}.*PASS calculator2.js_CF = [0-9a-f]{64}.*PASS SPA_CF = [0-9a-f]{64}.*PASS SPA_MARK_NOT_YET = 0.*PASS NOAUTH_CF = all 47 as expected.*routes new in this release .*: none.*$PRE.*pre-existing tracebacks since the running service started: 1.*PASS NPM = present.*PASS NODE_MODULES = present.*PREFLIGHT PASSED.*$PRE.*FAIL calculator2.js_CF = 'not probed.*FAIL SPA_MARK_CF = '0'.*######## VERIFY: $VB check\(s\) failed.*before the deploy \(want 0\): 0.*ok   saved costings: 72 [0-9a-f]{32}; 72 rows recorded by id and md5.*ok   calculator.js\?v=191 [0-9a-f]{16} = disk on 127.0.0.1, LAN, Cloudflare.*ok   calculator2.js\?v=128 [0-9a-f]{16} = disk on 127.0.0.1, LAN, Cloudflare.*ok   SPA assets/index-BBI2d9Oo.js [0-9a-f]{16} = disk on the three doors, without RT10.s text.*ok   npm present, node_modules present.*ok   backup size [0-9]+ and sha256 [0-9a-f]{16} read back.*frontend file\(s\) \(the SPA rebuild\), static = the two calculators only.*ok   plan: no migration, SPA rebuild, restart.*ok   SPA bundle assets/index-BBI2d9Oo.js -> assets/index-RT12[0-9]+.js.*$CHAIN.*$PRE.*before this deploy's restart \(listed, not counted\): 4.*PASS TRACEBACKS_SINCE_RESTART = 0.*PASS V_calculator.js = 192.*PASS V_calculator2.js = 129.*PASS SPA_REBUILT = yes.*PASS SPA_MARK_DISK = 1.*PASS VERSION_LOCAL = v1.63.0.*PASS calculator.js_LOCAL = [0-9a-f]{64}.*PASS SPA_MARK_LOCAL = 1.*PASS NOAUTH_LOCAL = all 47 as expected.*PASS VERSION_LAN.*PASS VERSION_CF = v1.63.0.*PASS calculator2.js_CF = [0-9a-f]{64}.*PASS SPA_CF = [0-9a-f]{64}.*PASS SPA_MARK_CF = 1.*######## DEPLOYED.*PASS QUOTES_UNCHANGED_SINCE_DEPLOY = 72 .*######## VERIFY: 0 check\(s\) failed.*######## ALREADY DEPLOYED.*pg_dump ran at alembic 0053\); npm builds: 1.*first request per door for /health/version\): 127.0.0.1 192.168.0.251 mes.icecoldgrp.online.*__pycache__ the kit left in the repo \(want 0\): 0.*'Permission denied' anywhere .* 0${NL}== files the kit wrote directly in /tmp \(want none\): ${NL}.*'exception line not found' in the kit.s out folders \(want 0\): 0"
row moved       'STOP \[WHERE\]: WRONG PLACE — code is at [0-9a-f]{7}, this step expects a29db35 [0-9a-f]{7}; nothing was run'
row wrongplace  "STOP \[WHERE\]: WRONG PLACE — machine is 'icb-mes-dev', this step runs on 'icb-mes-prod'"
row wrongdb     "STOP \[WHERE\]: WRONG PLACE — database is 'icb', this step runs on 'icb_platform'"
row staleboot   "STOP \[WHERE\]: WRONG PLACE — the kit was staged .*, before this machine's last boot .* — copy it again"
row unstamped   'STOP \[WHERE\]: WRONG PLACE — the kit has no staging stamp'
row nobackup    'STOP \[BACKUP\]: backup [^ ]*: holds no icb_costings.calculations data'
row pgdumpfail  'STOP \[BACKUP\]: backup [^ ]*: pg_dump exited 1'
row traceback   "$CHAIN.*since the restart:  [A-Z][a-z]{2} [0-9]{2} [0-9:]{8}  KeyError.*STOP \[TRACEBACKS_SINCE_RESTART\]: got .1., want 0"
row routeopen   'STOP \[NOAUTH_LOCAL\]: got ./api/calculations=200/401.'
row cfstale     'PASS VERSION_LAN = v1.63.0.*STOP \[VERSION_CF\]: got .v1\.62\.0.'
row cfcached    'the edge now holds v1.62.0.s bytes under \?v=192.*PASS calculator.js_LAN = [0-9a-f]{64}.*STOP \[calculator.js_CF\]: got .[0-9a-f]{64}., want [0-9a-f]{64}'
row resume      'STOP \[DEPLOY\].*RESUME.*plan: RESUME.*rebuilt by the resume.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed.*npm builds: 2'
# the rows named by id (RT9's lesson): three saved after the deploy -> added, by id, quote, created, version; a
# soft-deleted deploy-time row -> changed, deleted Y. The repair's quote number prints its first word only (G4).
row saved       "######## DEPLOYED.*three N10022 revisions are saved after the deploy.*FAIL QUOTES_UNCHANGED_SINCE_DEPLOY = '75 [0-9a-f]{32}'.*since the deploy: added 3 row\(s\), changed 0, removed 0.*-- added: 1238,1239,1240.*1238 \| N10022/10/2026 \| 2026-10-22 13:02:10 \| 4 \| pending \| N.*1240 \| N10022/10/2026 \| 2026-10-22 13:04:10 \| 6 \| pending \| N.*######## VERIFY: 1 check\(s\) failed"
row deleted     "######## DEPLOYED.*the repair row 1107 is soft-deleted after the deploy.*FAIL QUOTES_UNCHANGED_SINCE_DEPLOY = '72 [0-9a-f]{32}'.*since the deploy: added 0 row\(s\), changed 1, removed 0.*-- changed: 1107.*1107 \| R-2003 \| 2026-10-08 09:00:07 \| 1 \| pending \| Y.*######## VERIFY: 1 check\(s\) failed"
row factor      "FAIL FACTOR = '1.317073170731707'.*PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[FACTOR\]: costings.pu_foam_4g_factor reads '1.317073170731707', not exactly '1.3170731707317074'"
row autologin   'FAIL AUTOLOGIN_EMPTY = .no.*PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[AUTOLOGIN\]: MES_DEMO_AUTOLOGIN_USER is NOT empty'
row noenv       "FAIL ENV_KEY = 'absent'.*STOP \[ENV\]: /etc/icb/backend.env has 'absent'"
row notag       'FAIL TAG_ON_ORIGIN = .missing.*PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[TAG\]'
# the SPA rebuild's own controls: no node_modules -> preflight FAIL + deploy STOP before anything moves; a build that
# writes nothing -> SPA_REBUILT STOP (the code moved: the RESUME path applies)
row nonpm       "FAIL NODE_MODULES = 'missing'.*PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[TOOLING\]: /opt/icb-platform/frontend/node_modules is missing"
row nobuild     'npm run build will do nothing.*ok   plan: no migration, SPA rebuild, restart.*STOP \[SPA_REBUILT\]: the SPA bundle is still assets/index-BBI2d9Oo.js'
echo "== $P passed, $F failed"
