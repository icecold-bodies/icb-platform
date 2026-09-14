#!/usr/bin/env bash
# v1.53.1 prod deploy kit - READ-ONLY verification. Changes nothing on the server.
#   bash verify.sh [RUN_ID] [target|baseline]
#     baseline = today's prod (04b332f): run BEFORE the deploy - should pass green
#     target   = 94ed70b: run AFTER the deploy (default)
# The Cloudflare door is probed only when the files on disk already match the expectation,
# so a pre-deploy check can never cache the wrong bundle under the new ?v= URL.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$KIT/lib.sh"
. "$KIT/checks.sh"
RUN_ARG=""; EXPECT="target"
for a in "$@"; do
  case "$a" in
    target|baseline) EXPECT="$a" ;;
    "") ;;
    *[!0-9-]*) echo "unknown argument: $a (use target or baseline)"; exit 2 ;;
    *) RUN_ARG="$a" ;;
  esac
done
init_run "verify-$EXPECT" "$RUN_ARG"

run_checks "$EXPECT"
if [ "$FAILS" = "0" ] && [ "$EXPECT" = "target" ]; then
  if record_matches_head; then say ""; say "deploy record: $(cat "$RECORD")"; else say ""; say "  NOTE no deploy record for this HEAD in $KIT (fine if the deploy ran from another account)"; fi
fi
[ "$FAILS" = "0" ] || die "$FAILS verification check(s) failed"
RC=0
exit 0
