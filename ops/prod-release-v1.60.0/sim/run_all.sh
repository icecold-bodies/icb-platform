#!/bin/bash
# Every v1.60.0 release-kit scenario, one line each (run as root in WSL):  bash run_all.sh [kit-branch]
# A scenario passes when the deploy's banner is the expected one and the final state matches.
HERE=$(cd "$(dirname "$0")" && pwd)
KIT=${1:-rt3/families}
P=0; F=0
row() { # $1 scenario, $2 regex over the whole log
  local log; log=$(bash "$HERE/run_sim.sh" "$1" "$KIT" 2>&1)
  if [[ "$log" =~ $2 ]]; then echo "PASS  $1"; P=$((P+1)); else echo "FAIL  $1"; F=$((F+1)); echo "$log" | tail -n 40 | sed 's/^/      | /'; fi
}
row happy        'PREFLIGHT PASSED.*######## VERIFY: [1-9][0-9]* check\(s\) failed.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed.*######## ALREADY DEPLOYED'
row notag        'STOP \[TAG_ON_ORIGIN\]|PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[TAG\]'
row moved        'STOP \[ANCHORS\]'
row bootfail     'STOP \[BOOTSTRAP_FAILED\]'
row traceback    'STOP \[TRACEBACKS\]'
row stalecache   'STOP \[LOCAL_calculator\]'
row resume       'STOP \[DEPLOY\].*RESUME.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed'
row migfail      'STOP \[DEPLOY\].*RESUME.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed'
row nobackup     'STOP \[BACKUP\]'
row nobuild      'STOP \[SPA_HAS_FAMILY_LOCAL\]'
row groupseeded  'STOP \[BOOTSTRAP_SEEDED_GROUPS\]'
echo "== $P passed, $F failed"
