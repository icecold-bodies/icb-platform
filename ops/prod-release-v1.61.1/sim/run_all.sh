#!/bin/bash
# The v1.61.1 release-kit scenarios, one line each (run as root in WSL):
#     bash run_all.sh [kit-branch] [scenario ...]        (no scenario = all)
# A scenario passes when its log carries the expected banners in order. The scenario script is read from the kit
# branch itself. Each run removes its own /root/relsim8-* folder (the WSL disk lesson).
KIT=${1:-rt7/audit-truth}; shift 2>/dev/null
ONLY=" $* "
REPO=/mnt/c/Users/micge/Documents/icb-platform
RUN=$(mktemp); git -C "$REPO" -c safe.directory='*' show "$KIT:ops/prod-release-v1.61.1/sim/run_sim.sh" > "$RUN" || exit 1
P=0; F=0
row() { # $1 scenario, $2 regex over the whole log
  [ "$ONLY" = "  " ] || [[ "$ONLY" == *" $1 "* ]] || return 0
  local log; log=$(bash "$RUN" "$1" "$KIT" 2>&1)
  if [[ "$log" =~ $2 ]]; then echo "PASS  $1"; P=$((P+1)); else echo "FAIL  $1"; F=$((F+1)); echo "$log" | tail -n 60 | sed 's/^/      | /'; fi
}
VB=${VB:-7}   # verify BEFORE the deploy: exactly HEAD, TAG_LOCAL, DESCRIBE, LIST and VERSION_LOCAL / _LAN / _CF
FIRST='######## RT7 release v1.61.1 preflight · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head 5e37b0a · boot [0-9]{4}-'
row happy       "$FIRST.*PASS FACTOR = 1.3170731707317074.*PREFLIGHT PASSED.*######## VERIFY: $VB check\(s\) failed.*PASS LIST = 7 [0-9a-f]{64} pair=snapshot.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed.*######## ALREADY DEPLOYED.*pg_dump ran at alembic 0053\); npm builds: 0"
row factor      "FAIL FACTOR = '1.317073170731707'.*PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[FACTOR\]: costings.pu_foam_4g_factor reads '1.317073170731707', not exactly '1.3170731707317074'"
row notag       'STOP \[TAG_ON_ORIGIN\]|PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[TAG\]'
row moved       'STOP \[WHERE\]: WRONG PLACE — code is at [0-9a-f]{7}, this step expects 5e37b0a [0-9a-f]{7}; nothing was run'
row traceback   'STOP \[TRACEBACKS\]'
row resume      'STOP \[DEPLOY\].*RESUME.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed'
row nobackup    'STOP \[BACKUP\]: backup [^ ]*: holds no icb_costings.calculations data'
row pgdumpfail  'STOP \[BACKUP\]: backup [^ ]*: pg_dump exited 1'
row cfstale     'STOP \[VERSION_CF\]: got .?v1\.61\.0'
row autologin   'FAIL AUTOLOGIN_EMPTY = .no.*PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[AUTOLOGIN\]: MES_DEMO_AUTOLOGIN_USER is NOT empty'
row noenv       "FAIL ENV_KEY = 'absent'.*STOP \[ENV\]: /etc/icb/backend.env has 'absent'"
row wrongplace  "STOP \[WHERE\]: WRONG PLACE — machine is 'icb-mes-dev', this step runs on 'icb-mes-prod'"
row staleboot   "STOP \[WHERE\]: WRONG PLACE — the kit was staged .*, before this machine's last boot .* — copy it again"
row unstamped   'STOP \[WHERE\]: WRONG PLACE — the kit has no staging stamp'
echo "== $P passed, $F failed"
rm -f "$RUN"
