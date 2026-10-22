#!/bin/bash
# The v1.62.0 release-kit scenarios, one line each (run as root in WSL, from PowerShell — Git Bash mangles the path):
#     wsl -u root -- bash /mnt/c/Users/micge/Documents/icb-platform/ops/prod-release-v1.62.0/sim/run_all.sh [kit-branch] [scenario ...]
# (no scenario = all). A scenario passes when its log carries the expected lines in order. The scenario script is read
# from the kit branch itself. Each run removes its own /root/rt9relsim-* folder, and the origin cache at the end
# (the WSL disk lesson).
KIT=${1:-rt9/release-v1.62.0}; shift 2>/dev/null
ONLY=" $* "
REPO=/mnt/c/Users/micge/Documents/icb-platform
D=$(mktemp -d); trap 'rm -rf "$D" /root/rt9sim-cache' EXIT
for f in run_sim.sh fakeprod.sh stubs.sh; do git -C "$REPO" -c safe.directory='*' show "$KIT:ops/prod-release-v1.62.0/sim/$f" > "$D/$f" || exit 1; done
P=0; F=0
row() { # $1 scenario, $2 regex over the whole log
  [ "$ONLY" = "  " ] || [[ "$ONLY" == *" $1 "* ]] || return 0
  local log; log=$(bash "$D/run_sim.sh" "$1" "$KIT" 2>&1)
  mkdir -p /root/rt9sim-logs && printf '%s\n' "$log" > "/root/rt9sim-logs/$1.log"
  if [[ "$log" =~ $2 ]]; then echo "PASS  $1"; P=$((P+1)); else echo "FAIL  $1"; F=$((F+1)); echo "$log" | tail -n 60 | sed 's/^/      | /'; fi
}
# verify BEFORE the deploy fails on exactly: HEAD, TAG_LOCAL, DESCRIBE, CALCJS_V, CALCJS_DISK, and per door VERSION_x
# and CALCJS_x (not probed: the new bytes are not on disk) — 3 + 2 + 3 x 2
VB=${VB:-11}
FIRST='######## RT9 release v1.62.0 preflight · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head 5511355 · boot [0-9]{4}-'
NEWR='new in this release, 404 before the deploy: POST /api/calculations/1/reprice-preview'
PRE='pre-existing  [A-Z][a-z]{2} [0-9]{2} [0-9:]{8}  starlette.requests.ClientDisconnect'
row happy       "$FIRST.*PASS CALCJS_CF = [0-9a-f]{64}.*PASS NOAUTH_CF = all 47 as expected \($NEWR\).*$PRE.*pre-existing tracebacks since the running service started: 1.*PREFLIGHT PASSED.*$PRE.*FAIL CALCJS_CF = 'not probed.*######## VERIFY: $VB check\(s\) failed.*asked for calculator.js\?v=191 before the deploy \(want 0\): 0.*ok   backup size [0-9]+ and sha256 [0-9a-f]{16} read back.*$PRE.*$PRE.*before this deploy's restart \(listed, not counted\): 2.*PASS TRACEBACKS_SINCE_RESTART = 0.*PASS CALCJS_V = 191.*PASS VERSION_LOCAL = v1.62.0.*PASS NOAUTH_LOCAL = all 47 as expected.*PASS VERSION_LAN.*PASS VERSION_CF = v1.62.0.*PASS CALCJS_CF = [0-9a-f]{64}.*######## DEPLOYED.*PASS QUOTES_UNCHANGED_SINCE_DEPLOY = 72 .*######## VERIFY: 0 check\(s\) failed.*######## ALREADY DEPLOYED.*pg_dump ran at alembic 0053\); npm builds: 0.*first request per door for /health/version\): 127.0.0.1 192.168.0.251 mes.icecoldgrp.online"
row moved       'STOP \[WHERE\]: WRONG PLACE — code is at [0-9a-f]{7}, this step expects 5511355 [0-9a-f]{7}; nothing was run'
row wrongplace  "STOP \[WHERE\]: WRONG PLACE — machine is 'icb-mes-dev', this step runs on 'icb-mes-prod'"
row wrongdb     "STOP \[WHERE\]: WRONG PLACE — database is 'icb', this step runs on 'icb_platform'"
row staleboot   "STOP \[WHERE\]: WRONG PLACE — the kit was staged .*, before this machine's last boot .* — copy it again"
row unstamped   'STOP \[WHERE\]: WRONG PLACE — the kit has no staging stamp'
row nobackup    'STOP \[BACKUP\]: backup [^ ]*: holds no icb_costings.calculations data'
row pgdumpfail  'STOP \[BACKUP\]: backup [^ ]*: pg_dump exited 1'
row traceback   'pre-existing  .*ClientDisconnect.*since the restart: +1 KeyError.*STOP \[TRACEBACKS_SINCE_RESTART\]: got .1., want 0'
row routeopen   'STOP \[NOAUTH_LOCAL\]: got .POST /api/calculations/1/reprice-preview=200/401.'
row cfstale     'PASS VERSION_LAN = v1.62.0.*STOP \[VERSION_CF\]: got .v1\.61\.1.'
row cfcached    'the edge now holds v1.61.1.s bytes under \?v=191.*PASS CALCJS_LAN = [0-9a-f]{64}.*STOP \[CALCJS_CF\]: got .[0-9a-f]{64}., want [0-9a-f]{64}'
row resume      'STOP \[DEPLOY\].*RESUME.*plan: RESUME.*rebuilt by the resume.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed.*npm builds: 1'
row saved       '######## DEPLOYED.*a quote is saved after the deploy.*FAIL QUOTES_UNCHANGED_SINCE_DEPLOY = .73 .*######## VERIFY: 1 check\(s\) failed'
row factor      "FAIL FACTOR = '1.317073170731707'.*PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[FACTOR\]: costings.pu_foam_4g_factor reads '1.317073170731707', not exactly '1.3170731707317074'"
row autologin   'FAIL AUTOLOGIN_EMPTY = .no.*PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[AUTOLOGIN\]: MES_DEMO_AUTOLOGIN_USER is NOT empty'
row noenv       "FAIL ENV_KEY = 'absent'.*STOP \[ENV\]: /etc/icb/backend.env has 'absent'"
row notag       'FAIL TAG_ON_ORIGIN = .missing.*PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[TAG\]'
# the close's read-only quotes check (RT9_RETURN_1b Q1): 3 rows saved after the deploy are proven to be exactly the
# additions; and the negative control: a deploy-time row changed too -> the rest-digest no longer matches -> STOP
# (no `$` mid-pattern: in bash's [[ =~ ]] it anchors only at the very end of the whole log)
row quotes        '######## RT9 quotes check \(read only\) · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head [0-9a-f]{7} · boot.*ok   /var/backups/postgres/icb_platform_pre-v1.62.0_[0-9-]+\.dump  [0-9]+ bytes  sha256 [0-9a-f]{16}\.\.\. = the deploy.s.*at the deploy  72 0f1e2d3c4b5a69788796a5b4c3d2e1f0.*now +75 9cc317a6.*== the backup: 72 rows \(max id 1172\); now: 75 rows \(max id 1240\).*== added since the backup: 3.*1238 \| N10022/10/2026 \| 2026-10-22 13:02:10 \| 4 \| pending \| N \| 389120\.00 \| 389120\.00.*== changed since the backup: 0.*== removed since the backup: 0.*created on [0-9-]+ .*newest first: 3.*1240 \| N10022/10/2026 \| 2026-10-22 13:04:10 \| 6 \| pending \| N \| 389120\.00 \| 389120\.00   <- added since the backup.*######## DONE \(read only\): the backup compared row by row: added 3, changed 0, removed 0; created today 3.*G4: contact or customer names in the kit.s output \(want 0\): 0.*nothing extracted to the fake /tmp by the check \(want NONE\): NONE'
row quoteschanged '== added since the backup: 3.*== changed since the backup: 1.*1107 \| R-2003 \| contact_name.*== removed since the backup: 0.*######## DONE \(read only\): the backup compared row by row: added 3, changed 1, removed 0.*G4: contact or customer names in the kit.s output \(want 0\): 0.*nothing extracted to the fake /tmp by the check \(want NONE\): NONE'
echo "== $P passed, $F failed"
