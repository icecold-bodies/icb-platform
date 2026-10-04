#!/bin/bash
# The v1.60.1 release-kit scenarios, one line each (run as root in WSL):
#     bash run_all.sh [kit-branch] [scenario ...]        (no scenario = all ten)
# A scenario passes when its log carries the expected banners in order. Works under bash <(git show …) too: the
# scenario script is read from the kit branch itself.
KIT=${1:-rt4/build}; shift 2>/dev/null
ONLY=" $* "
REPO=/mnt/c/Users/micge/Documents/icb-platform
RUN=$(mktemp); git -C "$REPO" -c safe.directory='*' show "$KIT:ops/prod-release-v1.60.1/sim/run_sim.sh" > "$RUN" || exit 1
P=0; F=0
row() { # $1 scenario, $2 regex over the whole log
  [ "$ONLY" = "  " ] || [[ "$ONLY" == *" $1 "* ]] || return 0
  local log; log=$(bash "$RUN" "$1" "$KIT" 2>&1)
  if [[ "$log" =~ $2 ]]; then echo "PASS  $1"; P=$((P+1)); else echo "FAIL  $1"; F=$((F+1)); echo "$log" | tail -n 40 | sed 's/^/      | /'; fi
}
row happy        'PREFLIGHT PASSED.*######## VERIFY: [0-9]+ check\(s\) failed.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed.*######## ALREADY DEPLOYED'
row notag        'STOP \[TAG_ON_ORIGIN\]|PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[TAG\]'
row moved        'STOP \[ANCHORS\]'
# icb-deploy.sh's own verify catches a failed bootstrap first (STOP DEPLOY)
row bootfail     'BOOTSTRAP FAILED.*STOP \[DEPLOY\]'
row traceback    'STOP \[TRACEBACKS\]'
row stalecache   'STOP \[STAT_LOCAL\]'
row resume       'STOP \[DEPLOY\].*RESUME.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed'
row stillopen    'STOP \[NOAUTH_LOCAL\]: got .?/api/materials=200/401'
row cfstale      'STOP \[VERSION_CF\]: got .?v1\.60\.0'
row nobackup     'STOP \[BACKUP\]: no configurator_drafts'
echo "== $P passed, $F failed"
rm -f "$RUN"
