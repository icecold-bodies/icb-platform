#!/bin/bash
# RT9 PowerShell 5.1 sim — report the fake prod's /tmp and state for run_blocks.ps1, then remove the sim and its
# origin cache (the WSL disk lesson). As root in WSL:  bash fakeprod_down.sh [report-only]
SIM=$(cat /root/rt9ps51.current 2>/dev/null) || { echo "no PS 5.1 sim is up"; exit 0; }
echo "== fake prod /tmp at the end:"; ( cd "$SIM/tmp" && ls -A | sed 's/^/   /' )
echo "== fake prod HEAD $(git -C "$SIM/opt/icb-platform" rev-parse --short HEAD), describe $(git -C "$SIM/opt/icb-platform" describe --tags --abbrev=0 HEAD 2>/dev/null)"
echo "== the remote commands the stubs ran:"; grep -- '-> remote command:' "$SIM/forward.log" | sed 's/^ *-> remote command: /   /'
[ "${1:-}" = report-only ] && exit 0
rm -rf "$SIM" /root/rt9ps51-cache /root/rt9ps51.current
echo "== removed $SIM and the cache"
