#!/bin/bash
# All v1.59.3 release-kit scenarios, one log each:  bash run_all.sh [part-branch] [kit-branch]
for s in happy notag moved bootfail traceback stalecache resume migfail nobackup; do
  bash "$(dirname "$0")/run_sim.sh" "$s" "$@" > "$(dirname "$0")/sim_$s.log" 2>&1
  echo "$s done"
done
