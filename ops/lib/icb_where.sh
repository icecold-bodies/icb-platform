# shellcheck shell=bash
# RT6 safe pastes (RT6 dispatch, default 8): every kit's FIRST output line names the machine, the database (name and
# host) and the git HEAD it is about to act on, and the kit REFUSES when they are not what the step expects. Three
# pastes ran in the wrong place in two days (RT4 step 6; the 5 Oct dev paste; the 6 Oct paste in a Command Prompt);
# each was caught only by a read-back. This line is the read-back, before anything runs.
#
# Sourced, never run:
#     . "$KIT_DIR/lib/icb_where.sh"
#     icb_where "<step>" "<repo dir>" "<database url, or empty>"   # prints the line; sets WHERE_* ; never exits
#     icb_where_check || stop WHERE "$WHERE_WHY"                    # refuses on any mismatch
#
# Expectations (from the kit's expected.env):
#     EXPECT_MACHINE   the hostname (`hostname -s`), e.g. icb-mes-prod
#     EXPECT_DB        the database name, e.g. icb_platform — checked against the LIVE session, not only the URL
#     EXPECT_DBHOST    the host in the URL (host[:port]); unset = printed, not checked (a discovery learns it)
#     EXPECT_HEADS     space-separated full commit shas the repo may be at
# Prints only the URL's host and database name — never a user, a password or any other part of it.
#
# RT7 reboot guard (RT7 dispatch, default 8; G1): the line also prints the machine's BOOT TIME — the kernel's own
# `btime` in /proc/stat (epoch seconds; `uptime -s` is derived from the clock minus the uptime and can move by a
# second between calls). When the kit sets KIT_DIR, the check REFUSES a kit staged before the last boot: the copy
# step writes KIT_DIR/.staged_at (the VM's epoch seconds at unpack), and prod's unplanned 11 Oct reboot emptied /tmp
# under RT6's staged kits. ICB_LANE names the lane on the line (default RT6, whose kits predate it).

icb_boot_epoch() { awk '$1 == "btime" { print $2; exit }' "${ICB_PROC_STAT:-/proc/stat}" 2>/dev/null; }

icb_where() {
  local step=$1 repo=$2 url=${3:-} rest hostport
  WHERE_BOOT=$(icb_boot_epoch); WHERE_BOOT_TXT='?'
  [ -n "$WHERE_BOOT" ] && WHERE_BOOT_TXT=$(date -d "@$WHERE_BOOT" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || echo "@$WHERE_BOOT")
  WHERE_MACHINE=$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo '?')
  WHERE_HEAD=$(git -c safe.directory="$repo" -C "$repo" rev-parse HEAD 2>/dev/null || echo '?')
  WHERE_DB='?'; WHERE_DBHOST='?'; WHERE_DB_URL='?'
  if [ -n "$url" ]; then
    rest=${url#*://}
    case "$rest" in *@*) rest=${rest#*@} ;; esac          # drop any user:password@
    hostport=${rest%%/*}
    WHERE_DBHOST=${hostport:-socket}
    WHERE_DB_URL=${rest#*/}; WHERE_DB_URL=${WHERE_DB_URL%%\?*}
    WHERE_DB=$(psql "$url" -XAtc "select current_database()" 2>/dev/null) || WHERE_DB='?'
    [ -n "$WHERE_DB" ] || WHERE_DB='?'
  fi
  echo "######## ${ICB_LANE:-RT6} $step · machine $WHERE_MACHINE · db $WHERE_DB @ $WHERE_DBHOST · head ${WHERE_HEAD:0:7} · boot $WHERE_BOOT_TXT · $(date '+%Y-%m-%d %H:%M:%S %Z')"
}

icb_where_check() {
  WHERE_WHY=''
  [ -n "${EXPECT_MACHINE:-}" ] && [ "$WHERE_MACHINE" != "$EXPECT_MACHINE" ] \
    && WHERE_WHY="$WHERE_WHY machine is '$WHERE_MACHINE', this step runs on '$EXPECT_MACHINE';"
  if [ -n "${EXPECT_DB:-}" ]; then
    [ "$WHERE_DB" != "$EXPECT_DB" ] && WHERE_WHY="$WHERE_WHY database is '$WHERE_DB', this step runs on '$EXPECT_DB';"
    [ "$WHERE_DB_URL" != "$EXPECT_DB" ] && WHERE_WHY="$WHERE_WHY the URL names database '$WHERE_DB_URL', not '$EXPECT_DB';"
  fi
  [ -n "${EXPECT_DBHOST:-}" ] && [ "$WHERE_DBHOST" != "$EXPECT_DBHOST" ] \
    && WHERE_WHY="$WHERE_WHY database host is '$WHERE_DBHOST', this step expects '$EXPECT_DBHOST';"
  if [ -n "${EXPECT_HEADS:-}" ]; then
    case " $EXPECT_HEADS " in *" $WHERE_HEAD "*) ;; *)
      WHERE_WHY="$WHERE_WHY code is at ${WHERE_HEAD:0:7}, this step expects $(for h in $EXPECT_HEADS; do printf '%s\n' "${h:0:7}"; done | paste -sd' ');" ;;
    esac
  fi
  if [ -n "${KIT_DIR:-}" ]; then
    local staged=''
    [ -r "$KIT_DIR/.staged_at" ] && staged=$(tr -cd '0-9' < "$KIT_DIR/.staged_at")
    if [ -z "$WHERE_BOOT" ]; then
      WHERE_WHY="$WHERE_WHY the boot time cannot be read (${ICB_PROC_STAT:-/proc/stat});"
    elif [ -z "$staged" ]; then
      WHERE_WHY="$WHERE_WHY the kit has no staging stamp ($KIT_DIR/.staged_at) — copy it with the copy line;"
    elif [ "$staged" -lt "$WHERE_BOOT" ]; then
      WHERE_WHY="$WHERE_WHY the kit was staged $(date -d "@$staged" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || echo "@$staged"), before this machine's last boot ($WHERE_BOOT_TXT) — copy it again;"
    fi
  fi
  [ -z "$WHERE_WHY" ] && return 0
  WHERE_WHY="WRONG PLACE —${WHERE_WHY} nothing was run"
  return 1
}
