#!/bin/bash
# RT11 install kit, PowerShell 5.1 sim — bring up ONE persistent fake prod for run_blocks.ps1 (as root, in the Ubuntu
# 24.04 clone icb-noble-rt11), or take it down:
#     bash fakeprod_up.sh up <lane commit> | down | hostname <name> | ls | log
# The fake prod is ../../../sim/fakeprod.sh's (prod's /tmp rule, sudo user mickeyger) at <lane commit> (the RT11 code,
# fetched read-only from Michael's clone's object store), its venv owned by icb (uid 1600). It is recorded in
# /root/rt11ps51.current, so the check kit's forward.sh (ops/prod-rt11/sim/ps51) serves it unchanged. apt and pip are
# real: `down` removes libharfbuzz-subset0 again, so the clone is left as found.
set -u
SIMDIR=$(cd "$(dirname "$0")/../../../sim" && pwd)
CUR=/root/rt11ps51.current
APT_PKG=libharfbuzz-subset0
case "${1:-}" in
  up)
    LANE=${2:?lane commit}
    [ -e "$CUR" ] && { echo "a PS 5.1 sim is already up: $(cat "$CUR") - run 'down' first"; exit 1; }
    dpkg -s "$APT_PKG" >/dev/null 2>&1 && { echo "$APT_PKG is installed in the clone: remove it first"; exit 1; }
    SIM=/root/rt11ips51-$(date +%s); mkdir -p "$SIM" || exit 1
    mkdir -p "$SIM/simkit" && cp -a "$SIMDIR/." "$SIM/simkit/" || exit 1
    # shellcheck disable=SC1091
    . "$SIM/simkit/fakeprod.sh"
    fp_prod || { rm -rf "$SIM"; exit 1; }
    ( cd "$SIM/opt/icb-platform" && git -c protocol.file.allow=always fetch -q --depth 1 "file://$REPO_WIN" "$LANE" \
        && git -c advice.detachedHead=false checkout -q --detach FETCH_HEAD ) || { rm -rf "$SIM"; echo "could not fetch $LANE"; exit 1; }
    git -C "$SIM/opt/icb-platform" rev-parse HEAD > "$SIMSTATE/head"
    echo 'icb:x:1600:1600:sim venv owner:/nonexistent:/usr/sbin/nologin' >> "$SIM/etc/passwd"; echo 'icb:x:1600:' >> "$SIM/etc/group"
    chown -R 1600:1600 "$SIM/opt/icb-platform/.venv"
    echo "$SIM" > "$CUR"
    echo "SIM=$SIM"; echo "HEAD=$(cat "$SIMSTATE/head")" ;;
  hostname)
    SIM=$(cat "$CUR") || exit 1; echo "${2:?name}" > "$SIM/state/hostname" ;;
  ls)
    SIM=$(cat "$CUR") || exit 1; ( cd "$SIM/tmp" && ls -A ) ;;
  log)
    # no forward.log before the first ssh: no lines (a grep error here once counted as a command)
    SIM=$(cat "$CUR") || exit 1; { grep -- '-> remote command:' "$SIM/forward.log" 2>/dev/null || true; } | sed 's/^ *-> remote command: //' ;;
  down)
    DEBIAN_FRONTEND=noninteractive apt-get remove -y -qq "$APT_PKG" >/dev/null 2>&1
    SIM=$(cat "$CUR" 2>/dev/null) || { echo "no PS 5.1 sim is up"; exit 0; }
    rm -rf "$SIM" "$CUR"; echo "removed $SIM; $APT_PKG $(dpkg -s "$APT_PKG" >/dev/null 2>&1 && echo 'STILL INSTALLED' || echo 'not installed')" ;;
  *) echo "usage: fakeprod_up.sh up <lane commit> | down | hostname <name> | ls | log"; exit 1 ;;
esac
