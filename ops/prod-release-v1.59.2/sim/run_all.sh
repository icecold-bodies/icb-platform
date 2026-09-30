#!/bin/bash
for s in happy notag moved bootfail traceback stalecache resume; do
  bash $(dirname "$0")/run_sim.sh "$s" > $(dirname "$0")/sim_$s.log 2>&1
  echo "$s done"
done