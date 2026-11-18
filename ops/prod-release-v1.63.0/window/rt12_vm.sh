#!/usr/bin/env bash
# RT12 window — the VM side of Michael's laptop lines (run_window_*.ps1). Each laptop line first copies THIS file to
# prod as /tmp/icb-rt12-vm.sh and then runs it BY PATH: RT8's lesson (21 Oct) — an inline script handed to ssh as one
# argument from Windows PowerShell 5.1 lost its double quotes and bash ran nothing. Nothing here takes a quoted
# argument; every name it acts on is fixed below or checked against a pattern.
#
#     bash /tmp/icb-rt12-vm.sh where                  this machine, prod's HEAD, the boot time (3 lines; read only)
#     bash /tmp/icb-rt12-vm.sh unpack <kit>...         /tmp/<kit>.tar -> /tmp/<kit>/, SHA256SUMS checked, stamped
#     bash /tmp/icb-rt12-vm.sh fetch <name>            this window's out-* folders -> /tmp/<name>.tar (read only else)
#     bash /tmp/icb-rt12-vm.sh rmfetch <name>          remove /tmp/<name>.tar once the laptop holds it
#     sudo bash /tmp/icb-rt12-vm.sh cleanup            the close: remove the window's /tmp entries BY EXACT NAME
#     bash /tmp/icb-rt12-vm.sh readback                each of those names: absent? then this file removes itself
#
# prod's /tmp is sticky with fs.protected_regular=2 (RT10's lesson, 23 Oct): every file this helper writes in /tmp
# (the kits it unpacks, their .staged_at, the window mark, the fetch tar) is created and owned by the ssh user
# (mickeyger), who also removes them; root only runs the cleanup (rm) and the kits, which write under their own
# folders. Nothing here appends to a /tmp file another user owns, and nothing is chowned.
# Deliberately no bare `set -e`: every failure prints a STOP line and exits 1.
set -u
KITS="icb-release-v1.63.0 icb-rt2-all icb-rt2-doors"
MARK=/tmp/icb-rt12-window.started         # written by the FIRST unpack only: fetch takes the out-* folders newer than it
SELF=/tmp/icb-rt12-vm.sh
REPO=/opt/icb-platform
# The close (cleanup): every /tmp entry this window creates, by exact name — never a glob. RT9's close (22 Oct) left
# prod /tmp clean of RT7's and RT9's kits; RT10's and RT11's read-only checks removed themselves. Not listed, and left
# alone: /tmp/icb-rollback-<ts>.txt, which the repo's own icb-deploy.sh writes on every deploy (its rollback anchor).
NAMES="/tmp/icb-release-v1.63.0 /tmp/icb-release-v1.63.0.tar /tmp/icb-rt2-all /tmp/icb-rt2-all.tar
/tmp/icb-rt2-doors /tmp/icb-rt2-doors.tar $MARK"
stop() { echo "######## STOP [$1]: $2"; exit 1; }
is_kit() { case " $KITS " in *" $1 "*) return 0 ;; esac; return 1; }

case "${1:-}" in
  where)
    hostname -s
    git -c safe.directory="$REPO" -C "$REPO" rev-parse HEAD 2>/dev/null || echo '?'
    b=$(awk '$1 == "btime" { print $2; exit }' /proc/stat)
    date -d "@$b" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || echo '?'
    ;;
  unpack)
    shift
    [ $# -gt 0 ] || stop KIT "unpack: name the kits"
    for k in "$@"; do
      is_kit "$k" || stop KIT "unpack: '$k' is not one of: $KITS"
      [ -f "/tmp/$k.tar" ] || stop COPY "/tmp/$k.tar is not on prod"
      ( cd /tmp && tar -xf "$k.tar" ) || stop COPY "$k.tar did not unpack"
      ( cd "/tmp/$k" && sha256sum -c --quiet SHA256SUMS ) || stop COPY "$k: the unpacked files do not match its SHA256SUMS"
      date +%s > "/tmp/$k/.staged_at" || stop COPY "$k: cannot write its staging stamp"
      echo "   $k unpacked, verified (SHA256SUMS) and stamped on prod"
    done
    [ -e "$MARK" ] || date +%s > "$MARK" || stop COPY "cannot write $MARK"
    echo "   window start mark: $(date -d "@$(cat "$MARK")" '+%Y-%m-%d %H:%M:%S %Z') (fetch takes the out-* folders written after it)"
    ;;
  fetch)
    n=${2:-}
    [[ "$n" =~ ^rt12-window-back-[0-9]{8}-[0-9]{6}$ ]] || stop FETCH "fetch: the name must be rt12-window-back-<yyyymmdd-hhmmss>"
    [ -e "$MARK" ] || stop FETCH "no window start mark ($MARK): was the copy line run on this boot?"
    [ -e "/tmp/$n.tar" ] && stop FETCH "/tmp/$n.tar already exists"
    list=$(cd /tmp && for k in $KITS; do [ -d "$k" ] && find "$k" -mindepth 1 -maxdepth 1 -type d -name 'out-*' -newer "$MARK"; done | LC_ALL=C sort)
    [ -n "$list" ] || stop FETCH "no out-* folder written since the window started"
    echo "$list" | sed 's/^/   /'
    ( cd /tmp && printf '%s\n' "$list" | tar -cf "$n.tar" -T - ) || stop FETCH "could not pack the out-* folders"
    echo "   packed $(echo "$list" | wc -l) folder(s): /tmp/$n.tar $(stat -c %s "/tmp/$n.tar") bytes"
    ;;
  rmfetch)
    n=${2:-}
    [[ "$n" =~ ^rt12-window-back-[0-9]{8}-[0-9]{6}$ ]] || stop FETCH "rmfetch: the name must be rt12-window-back-<yyyymmdd-hhmmss>"
    rm -f -- "/tmp/$n.tar" && [ ! -e "/tmp/$n.tar" ] && echo "   /tmp/$n.tar removed from prod" || stop FETCH "could not remove /tmp/$n.tar"
    ;;
  cleanup)
    [ "$(id -u)" = 0 ] || stop CLEANUP "run with sudo (the kits' out-* folders are root's)"
    for p in $NAMES; do
      case "$p" in /tmp/icb-*) ;; *) stop CLEANUP "refusing a name outside /tmp/icb-*: $p" ;; esac
      if [ -e "$p" ] || [ -L "$p" ]; then rm -rf --one-file-system -- "$p" && echo "   removed $p" || stop CLEANUP "could not remove $p"
      else echo "   absent  $p"; fi
    done
    ;;
  readback)
    left=0
    for p in $NAMES; do if [ -e "$p" ] || [ -L "$p" ]; then echo "   STILL THERE $p"; left=$((left + 1)); else echo "   absent      $p"; fi; done
    [ "$left" = 0 ] || stop READBACK "$left name(s) still in /tmp"
    rm -f -- "$SELF"; [ -e "$SELF" ] && stop READBACK "$SELF could not remove itself"
    echo "   absent      $SELF (removed itself)"
    ;;
  *) echo "usage: bash $SELF where | unpack <kit>... | fetch <name> | rmfetch <name> | cleanup | readback"; exit 1 ;;
esac
