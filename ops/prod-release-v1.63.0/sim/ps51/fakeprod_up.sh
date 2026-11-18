#!/bin/bash
# RT12 PowerShell 5.1 sim — bring up ONE persistent fake prod for run_blocks.ps1 (as root in WSL):
#     bash fakeprod_up.sh <kit-branch-or-sha> <windows stage ROOT, as /mnt/c/...>     (-> <root>/window)
# Builds the sim origin, stages the window with the REAL mkstage_window.sh and the fake prod at v1.62.0
# (sim/fakeprod.sh: sticky /tmp, the ssh user mickeyger uid 1500), leaves in the fake /tmp what the real one holds
# since RT9's close (22 Oct): only icb-deploy.sh's own rollback anchors, copies the stage to the Windows folder, and
# records the sim in /root/rt12ps51.current for forward.sh. fakeprod_down.sh removes it.
set -u
KIT=${1:?kit branch}
WINSTAGE=${2:?windows stage dir}
REPO=/mnt/c/Users/micge/Documents/icb-platform
export RT12SIM_CACHE=/root/rt12ps51-cache
[ -e /root/rt12ps51.current ] && { echo "a PS 5.1 sim is already up: $(cat /root/rt12ps51.current) — run fakeprod_down.sh first"; exit 1; }
SIM=/root/rt12ps51-$(date +%s)
mkdir -p "$SIM" || exit 1
HERE=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck disable=SC1091
. "$HERE/fakeprod.sh"
fp_origin || exit 1
fp_stage || exit 1
fp_prod || exit 1
# prod /tmp since RT9's close: no kit; the deploy tool's own anchors (left alone by every cleanup)
echo "a29db35" > "$SIM/tmp/icb-rollback-20261022-123540.txt"
touch -d '2026-10-22 12:35:40' "$SIM/tmp/icb-rollback-20261022-123540.txt"
mkdir -p "$WINSTAGE" && cp -a "$SIM/stageout/." "$WINSTAGE/" || exit 1
echo "$SIM" > /root/rt12ps51.current
echo "SIM=$SIM"
echo "TARGET=$TARGET"
echo "PREV=$PREV"
