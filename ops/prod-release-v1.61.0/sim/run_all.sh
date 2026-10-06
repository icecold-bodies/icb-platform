#!/bin/bash
# The v1.61.0 release-kit scenarios, one line each (run as root in WSL):
#     bash run_all.sh [kit-branch] [scenario ...]        (no scenario = all)
# A scenario passes when its log carries the expected banners in order. The scenario script is read from the kit
# branch itself. Each run removes its own /root/relsim7-* folder (the RT4 disk lesson).
KIT=${1:-rt6/enforce}; shift 2>/dev/null
ONLY=" $* "
REPO=/mnt/c/Users/micge/Documents/icb-platform
RUN=$(mktemp); git -C "$REPO" -c safe.directory='*' show "$KIT:ops/prod-release-v1.61.0/sim/run_sim.sh" > "$RUN" || exit 1
P=0; F=0
row() { # $1 scenario, $2 regex over the whole log
  [ "$ONLY" = "  " ] || [[ "$ONLY" == *" $1 "* ]] || return 0
  local log; log=$(bash "$RUN" "$1" "$KIT" 2>&1)
  if [[ "$log" =~ $2 ]]; then echo "PASS  $1"; P=$((P+1)); else echo "FAIL  $1"; F=$((F+1)); echo "$log" | tail -n 50 | sed 's/^/      | /'; fi
}
VB=${VB:-24}   # verify BEFORE the deploy (and before the env step): exactly these 24 not-yet-deployed checks
FIRST='######## RT6 release v1.61.0 preflight · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head a429404'
row happy        "$FIRST.*PREFLIGHT PASSED.*######## VERIFY: $VB check\(s\) failed.*DONE \(env: ICB_ENVIRONMENT=prod, read back.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed.*DONE \(env: already ICB_ENVIRONMENT=prod\).*######## ALREADY DEPLOYED.*1 line\(s\) added: ICB_ENVIRONMENT=prod .*earlier lines unchanged: yes; mode 600.*pg_dump ran at alembic 0052.*npm builds: [1-9]"
row notag        'STOP \[TAG_ON_ORIGIN\]|PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[TAG\]'
row moved        'STOP \[WHERE\]: WRONG PLACE — code is at [0-9a-f]{7}, this step expects a429404 [0-9a-f]{7}; nothing was run.*sim state: prod HEAD [0-9a-f]+, describe v1\.60\.2, alembic 0052'   # RT6: the safe-paste line refuses before ANCHORS
row bootfail     'BOOTSTRAP FAILED.*STOP \[DEPLOY\]'
row traceback    'STOP \[TRACEBACKS\]'
row stalecache   'STOP \[LOCAL_calculator\]'
row resume       'STOP \[DEPLOY\].*RESUME.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed'
row migfail      'STOP \[DEPLOY\].*RESUME.*######## DEPLOYED.*######## VERIFY: 0 check\(s\) failed'
row nobackup     'STOP \[BACKUP\]: backup [^ ]*: holds no icb_costings.calculations data'
row pgdumpfail   'STOP \[BACKUP\]: backup [^ ]*: pg_dump exited 1'
row cfstale      'STOP \[VERSION_CF\]: got .?v1\.60\.2'
row famchanged   'STOP \[FAMILIES_UNCHANGED\]'
row nobuild      'STOP \[SPA_REBUILT\]'
row autologin    'FAIL AUTOLOGIN_EMPTY = .no.*PREFLIGHT: [0-9]+ check\(s\) FAILED.*STOP \[AUTOLOGIN\]: MES_DEMO_AUTOLOGIN_USER is NOT empty'
row noenv        'STOP \[ENV\]: /etc/icb/backend.env has .absent.: run .release.sh env. first'
row envother     "STOP \[ENV\]: ICB_ENVIRONMENT is 'ICB_ENVIRONMENT=dev' in /etc/icb/backend.env — not overwritten"
row wrongplace   "STOP \[WHERE\]: WRONG PLACE — machine is 'icb-mes-dev', this step runs on 'icb-mes-prod'"
echo "== $P passed, $F failed"
rm -f "$RUN"
