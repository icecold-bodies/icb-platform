#!/bin/bash
# RT9 PowerShell 5.1 sim — AFTER the fake deploy (run_blocks.ps1 calls it between the window's lines and the close's):
# stage the close with the REAL mkstage_close.sh from the kit branch's head, against the fake prod's own deploy backup
# (its path, size and sha256 are pinned into expected.env), and copy it to the Windows stage root's close/ folder.
#     bash stage_close.sh <windows stage ROOT, as /mnt/c/...>
set -u
WINSTAGE=${1:?windows stage root}
SIM=$(cat /root/rt9ps51.current 2>/dev/null) || { echo "no PS 5.1 sim is up"; exit 1; }
# shellcheck disable=SC1091
. "$SIM/fp.env" && . "$SIM/work/ops/prod-release-v1.62.0/sim/fakeprod.sh" || exit 1
KITHEAD=$(git -C "$SIM/work" rev-parse HEAD)
fp_stage_close || exit 1
mkdir -p "$WINSTAGE/close" && cp -a "$SIM/stageout/close/." "$WINSTAGE/close/" || exit 1
echo "the close staged against $(ls "$SIM"/varbackups/postgres/icb_platform_pre-v1.62.0_*.dump | head -n1 | xargs -n1 basename)"
