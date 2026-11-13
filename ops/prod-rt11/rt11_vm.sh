#!/usr/bin/env bash
# RT11 prod check — the VM side of Michael's laptop line (run_check.ps1). The line first copies THIS file to prod as
# /tmp/icb-rt11-vm.sh and then runs it BY PATH (RT8, 21 Oct: an inline script handed to ssh as one argument from
# Windows PowerShell 5.1 lost its double quotes and bash ran nothing). Nothing here takes a quoted argument; every
# name it acts on is fixed below.
#
#     bash /tmp/icb-rt11-vm.sh where       this machine, prod's HEAD, the boot time (3 lines; read only)
#     bash /tmp/icb-rt11-vm.sh unpack      /tmp/icb-rt11-check.tar -> /tmp/icb-rt11-check/, SHA256SUMS checked, stamped
#     bash /tmp/icb-rt11-vm.sh readback    remove the fetched report, check every name below is absent, remove itself
#
# Deliberately no bare `set -e`: every failure prints a STOP line and exits 1.
set -u
KIT=icb-rt11-check
SELF=/tmp/icb-rt11-vm.sh
REPORT=/tmp/icb-rt11-check-report.txt
REPO=/opt/icb-platform
# every /tmp name the check creates, by exact name — never a glob
NAMES="/tmp/icb-rt11-check /tmp/icb-rt11-check.tar $REPORT"
stop() { echo "######## STOP [$1]: $2"; exit 1; }

case "${1:-}" in
  where)
    hostname -s
    git -c safe.directory="$REPO" -C "$REPO" rev-parse HEAD 2>/dev/null || echo '?'
    b=$(awk '$1 == "btime" { print $2; exit }' /proc/stat)
    date -d "@$b" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || echo '?'
    ;;
  unpack)
    [ -f "/tmp/$KIT.tar" ] || stop COPY "/tmp/$KIT.tar is not on prod"
    [ -e "/tmp/$KIT" ] && { rm -rf --one-file-system -- "/tmp/$KIT" 2>/dev/null; [ -e "/tmp/$KIT" ] && stop COPY "an older /tmp/$KIT is still there and is not mine to remove: tell the CA"; }
    ( cd /tmp && tar -xf "$KIT.tar" ) || stop COPY "$KIT.tar did not unpack"
    ( cd "/tmp/$KIT" && sha256sum -c --quiet SHA256SUMS ) || stop COPY "the unpacked files do not match the kit's SHA256SUMS"
    date +%s > "/tmp/$KIT/.staged_at" || stop COPY "cannot write the kit's staging stamp"
    echo "   $KIT unpacked, verified (SHA256SUMS) and stamped on prod"
    ;;
  readback)
    if [ -e "$REPORT" ]; then rm -f -- "$REPORT" || true; fi
    left=0
    for p in $NAMES; do
      if [ -e "$p" ] || [ -L "$p" ]; then echo "   STILL THERE $p"; left=$((left + 1)); else echo "   absent      $p"; fi
    done
    [ "$left" = 0 ] || stop READBACK "$left name(s) still in prod /tmp"
    rm -f -- "$SELF"; [ -e "$SELF" ] && stop READBACK "$SELF could not remove itself"
    echo "   absent      $SELF (removed itself)"
    ;;
  *) echo "usage: bash $SELF where | unpack | readback"; exit 1 ;;
esac
