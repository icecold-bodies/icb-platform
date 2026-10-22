#!/bin/bash
# RT9 PowerShell 5.1 sim — bring up ONE persistent fake prod for run_blocks.ps1 (as root in WSL):
#     bash fakeprod_up.sh <kit-branch> <windows stage ROOT, as /mnt/c/...>     (-> <root>/window and <root>/close)
# Builds the sim origin, stages the window with the REAL mkstage_window.sh (and the close with mkstage_close.sh when
# the kit branch carries it) and the fake prod at v1.61.1 (sim/fakeprod.sh),
# puts RT7's leftovers in the fake /tmp as the real one holds them since 20 Oct (the v1.61.1 release kit, the All and
# door kits with RT7's old out-* folders), copies the stage to the Windows folder, and records the sim in
# /root/rt9ps51.current for forward.sh. fakeprod_down.sh removes it.
set -u
KIT=${1:?kit branch}
WINSTAGE=${2:?windows stage dir}
REPO=/mnt/c/Users/micge/Documents/icb-platform
export RT9SIM_CACHE=/root/rt9ps51-cache
[ -e /root/rt9ps51.current ] && { echo "a PS 5.1 sim is already up: $(cat /root/rt9ps51.current) — run fakeprod_down.sh first"; exit 1; }
SIM=/root/rt9ps51-$(date +%s)
mkdir -p "$SIM" || exit 1
HERE=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck disable=SC1091
. "$HERE/fakeprod.sh"
fp_origin || exit 1
fp_stage || exit 1
fp_prod || exit 1
# RT7's window leftovers (20 Oct): the release kit + tar; the All / door kit folders with root's old out-* folders
T=$SIM/tmp
mkdir -p "$T/icb-release-v1.61.1/out-deploy-20261020-131234" "$T/icb-rt2-all/out-pre-20261020-131116" \
         "$T/icb-rt2-all/out-post-20261020-131725" "$T/icb-rt2-doors/out-20261020-131910"
echo "rt7" > "$T/icb-release-v1.61.1/out-deploy-20261020-131234/OUTCOME.txt"; echo "rt7" > "$T/icb-rt2-all/out-pre-20261020-131116/run.log"
echo "rt7 kit" > "$T/icb-rt2-all/rt2_all.sh"; echo "x" > "$T/icb-release-v1.61.1.tar"; echo "x" > "$T/icb-rt2-all.tar"; echo "x" > "$T/icb-rt2-doors.tar"
find "$T" -mindepth 1 -exec touch -d '2026-10-20 13:20:00' {} +
mkdir -p "$WINSTAGE" && cp -a "$SIM/stageout/." "$WINSTAGE/" || exit 1
echo "$SIM" > /root/rt9ps51.current
echo "SIM=$SIM"
echo "TARGET=$TARGET"
echo "PREV=$PREV"
