#!/bin/bash
# RT11 PowerShell 5.1 sim — bring up ONE persistent fake prod for run_block.ps1, or take it down (as root in WSL):
#     bash fakeprod_up.sh up | down | state <flag> on|off | hostname <name> | ls
# The fake prod (../fakeprod.sh) is recorded in /root/rt11ps51.current for forward.sh; `down` removes it all.
set -u
HERE=$(cd "$(dirname "$0")/.." && pwd)
CUR=/root/rt11ps51.current
case "${1:-}" in
  up)
    [ -e "$CUR" ] && { echo "a PS 5.1 sim is already up: $(cat "$CUR") - run 'down' first"; exit 1; }
    SIM=/root/rt11ps51-$(date +%s); mkdir -p "$SIM" || exit 1
    mkdir -p "$SIM/simkit" && cp -a "$HERE/." "$SIM/simkit/" || exit 1
    # shellcheck disable=SC1091
    . "$SIM/simkit/fakeprod.sh"
    fp_prod || { rm -rf "$SIM"; exit 1; }
    echo "$SIM" > "$CUR"
    echo "SIM=$SIM"; echo "HEAD=$(cat "$SIM/state/head")" ;;
  state)
    SIM=$(cat "$CUR") || exit 1
    if [ "${3:-}" = on ]; then touch "$SIM/state/$2"; else rm -f "$SIM/state/$2"; fi ;;
  hostname)
    SIM=$(cat "$CUR") || exit 1; echo "${2:?name}" > "$SIM/state/hostname" ;;
  ls)
    SIM=$(cat "$CUR") || exit 1; ( cd "$SIM/tmp" && ls -A ) ;;
  log)
    SIM=$(cat "$CUR") || exit 1; grep -- '-> remote command:' "$SIM/forward.log" | sed 's/^ *-> remote command: //' ;;
  down)
    SIM=$(cat "$CUR" 2>/dev/null) || { echo "no PS 5.1 sim is up"; exit 0; }
    rm -rf "$SIM" "$CUR"; echo "removed $SIM" ;;
  *) echo "usage: fakeprod_up.sh up | down | state <flag> on|off | hostname <name> | ls | log"; exit 1 ;;
esac
