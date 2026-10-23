#!/usr/bin/env bash
# RT10 (dispatch default 13, F6) — test_preview_formats_journey::test_banner_length_live, N runs against the rt10
# side server (:8012, icb_test), CPU-throttled. Usage: bash flake10.sh <label> [runs] [throttle]
LABEL=${1:?label}; RUNS=${2:-10}; THR=${3:-6}
OUT="C:/Users/micge/AppData/Local/Temp/claude/C--Users-micge-Documents-icb-platform/51f8f4ef-619b-4381-8cce-99ecf61033d6/scratchpad/rt10_step0/flake_${LABEL}.txt"
cd C:/Users/micge/Documents/icb-platform-rt10/backend || exit 2
: > "$OUT"
pass=0; fail=0
for i in $(seq 1 "$RUNS"); do
  r=$(DATABASE_URL="postgresql+psycopg://icb_app:icb_app_dev@localhost:5432/icb_test" SESSION_SECRET=x MES_BASE=http://127.0.0.1:8012 \
      MES_JOURNEY_CPU_THROTTLE=$THR RT10_DELAY_TRAILERS_MS=${DELAY:-0} RT10_NC=${NC:-} PYTHONDONTWRITEBYTECODE=1 timeout 300 \
      C:/Users/micge/Documents/icb-platform/backend/.venv/Scripts/python.exe -m pytest \
      tests/journeys/test_preview_formats_journey.py -k test_banner_length_live -p no:cacheprovider -W ignore -q -rf 2>&1); rc=$?
  if [ "$rc" = 0 ]; then pass=$((pass+1)); echo "run $i PASS" >> "$OUT"
  else fail=$((fail+1)); echo "run $i FAIL: $(echo "$r" | grep -E "^E |AssertionError" | head -3 | tr '\n' ' ')" >> "$OUT"; fi
done
echo "== $LABEL: $pass passed, $fail failed of $RUNS (CPU throttle ${THR}x, /api/trailers delay ${DELAY:-0} ms, NC=${NC:-none})" >> "$OUT"
tail -1 "$OUT"
