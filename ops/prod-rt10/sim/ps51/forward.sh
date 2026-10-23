#!/bin/bash
# RT10 PowerShell 5.1 sim — the WSL side of the ssh.exe / scp.exe stand-ins (RT9's sim/ps51/stub.cs). Run as root:
#     bash forward.sh <request file>          (NUL-separated: the tool, then the arguments it received)
# ssh: the options are skipped, the host must be the sim's (stubuser@127.0.0.9: anything else is refused), and the
#      remaining words are joined with single spaces and run by bash -c — what OpenSSH does — inside the fake prod
#      (fakeprod.sh fp_run). scp: a Windows path (C:\...) is the laptop's; host:/tmp/... is the fake prod's /tmp.
set -u
REQ=${1:?request file}
HOST=stubuser@127.0.0.9
SIM=$(cat /root/rt10ps51.current 2>/dev/null) || { echo "forward: no sim is up (/root/rt10ps51.current)" >&2; exit 255; }
# shellcheck disable=SC1091
. "$SIM/fp.env" && . "$SIM/simkit/fakeprod.sh" || { echo "forward: the sim at $SIM is broken" >&2; exit 255; }
mapfile -d '' -t A < "$REQ"
tool=${A[0]}; args=("${A[@]:1}")
echo "$tool $(printf '[%s] ' "${args[@]}")" >> "$SIM/forward.log"
winpath() { local p=${1//\\//}; local d=${p:0:1}; echo "/mnt/${d,,}${p:2}"; }
remote() { [[ "$1" =~ ^[^/\\:@]+@[^/\\:]+: ]]; }
fakepath() {
  local h=${1%%:*} p=${1#*:}
  [ "$h" = "$HOST" ] || { echo "scp stub: host '$h' is not the sim's $HOST - refusing" >&2; return 1; }
  case "$p" in /tmp/*) echo "$SIM/tmp${p#/tmp}" ;; *) echo "scp stub: only /tmp exists in the sim: $p" >&2; return 1 ;; esac
}
case "$tool" in
  ssh)
    i=0; n=${#args[@]}
    while [ $i -lt $n ]; do
      case "${args[$i]}" in
        -o|-p|-i|-l|-F|-E) i=$((i + 2)) ;;
        -t|-T|-q|-v|-tt) i=$((i + 1)) ;;
        -*) echo "ssh stub: option ${args[$i]} not modelled" >&2; exit 255 ;;
        *) break ;;
      esac
    done
    host=${args[$i]:-}; i=$((i + 1))
    [ "$host" = "$HOST" ] || { echo "ssh stub: host '$host' is not the sim's $HOST - refusing" >&2; exit 255; }
    cmd="${args[*]:$i}"
    [ -n "$cmd" ] || { echo "ssh stub: an interactive login is not modelled" >&2; exit 255; }
    echo "   -> remote command: $cmd" >> "$SIM/forward.log"
    fp_run "$cmd"
    exit $? ;;
  scp)
    files=(); i=0; n=${#args[@]}
    while [ $i -lt $n ]; do
      case "${args[$i]}" in
        -o|-P|-i|-F) i=$((i + 2)) ;;
        -q|-r|-p|-B|-C) i=$((i + 1)) ;;
        -*) echo "scp stub: option ${args[$i]} not modelled" >&2; exit 255 ;;
        *) files+=("${args[$i]}"); i=$((i + 1)) ;;
      esac
    done
    [ ${#files[@]} = 2 ] || { echo "scp stub: need one source and one destination" >&2; exit 255; }
    if remote "${files[1]}"; then
      d=$(fakepath "${files[1]}") || exit 255
      remote "${files[0]}" && { echo "scp stub: remote to remote" >&2; exit 255; }
      cp -f -- "$(winpath "${files[0]}")" "$d" || exit 1
    else
      remote "${files[0]}" || { echo "scp stub: neither side is the sim's host" >&2; exit 255; }
      s=$(fakepath "${files[0]}") || exit 255
      [ -f "$s" ] || { echo "scp: $s: No such file or directory" >&2; exit 1; }
      cp -f -- "$s" "$(winpath "${files[1]}")" || exit 1
    fi
    exit 0 ;;
  *) echo "forward: unknown tool '$tool'" >&2; exit 255 ;;
esac
