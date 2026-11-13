#!/usr/bin/env bash
# RT11 — WeasyPrint for the letterhead quote ("Generate Quote") on prod: the apt and pip steps of the release window,
# their read-backs, and their rollback. Michael runs ONE line per step on his laptop (run_install.ps1 <step>): it copies
# this kit to prod /tmp, runs THIS file by path under sudo over `ssh -t`, fetches the report, and reads back that prod
# /tmp holds nothing of it. On the VM itself:
#
#     sudo bash /tmp/icb-rt11-install/rt11_install.sh preflight | apt | pip | verify | rollback
#
#   preflight  READ ONLY: apt-get -s, pip --dry-run (as nobody), whether the deployed code carries the fonts, the gate
#   apt        apt-get -s must show EXACTLY one new package (APT_PKG=APT_VER) and nothing upgraded or removed; then
#              that one install (--no-install-recommends --no-upgrade); read-back: the dpkg list differs by that line only
#   pip        refuses before the RT11 code (the shipped fonts) is deployed or before the apt step (ORDER: a gate that
#              reads True on the old code would offer quotes in a fallback face); --dry-run as the venv owner must show
#              EXACTLY the lock (weasyprint-lock.txt) as new and nothing changed; then `pip install --no-deps -r lock` as
#              the venv owner; read-back: the venv's package list differs by the lock only; weasyprint imports
#   verify     as the venv owner: the five quote templates at REV 0 and REV 1 with the deployed code (rt11_verify.py:
#              pages, label, price, faces exactly Liberation) and the gate True; says whether icb-backend must restart
#   rollback   pip uninstall of the lock (as the venv owner), then apt-get remove of APT_PKG (-s first: that one only)
# The service is never touched here: the release window restarts icb-backend (the gate is read at start-up).
# Its FIRST line names the machine, the HEAD and the boot time, and it refuses unless they are expected.env's. Every
# real outcome is a named STOP; decoration carries `|| true`; no bare `set -e`. The report's last line is written
# BEFORE it is handed to the sudo user (prod runs fs.protected_regular=2: RT11_RULING_0A). The kit removes itself.
set -u
set -o pipefail
BASE=/tmp/icb-rt11-install
KIT_DIR=$BASE
ICB_LANE=RT11
REPO=/opt/icb-platform
PY=$REPO/.venv/bin/python
REPORT=/tmp/icb-rt11-install-report.txt
LOCK=$BASE/weasyprint-lock.txt
MODE=${1:-}
TS=$(date +%Y%m%d-%H%M%S)

stop() { echo; echo "######## STOP [$1]: $2"; echo "######## $3"; exit 1; }
say()  { echo "== $*"; }
lock_names() { sed -n 's/==.*//p' "$LOCK" | tr 'A-Z_' 'a-z-' | sort; }
pip_as() { # $1 = user; the rest: python arguments. A clean environment, no cache, pip's temp + home inside the kit.
  local u=$1; shift
  ( cd "$BASE/pip" && runuser -u "$u" -- env -i PATH=/usr/bin:/bin HOME="$BASE/pip/home" TMPDIR="$BASE/pip/tmp" \
      XDG_CACHE_HOME="$BASE/pip/home/.cache" PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 \
      "$PY" "$@" )
}
venv_list() { pip_as "$1" -m pip list --format=freeze 2>/dev/null | tr 'A-Z_' 'a-z-' | sort; }
apt_sim() { LC_ALL=C apt-get -s -o Debug::NoLocking=1 "$@" 2>&1; }
code_fonts() { # the deployed code carries RT11: every shipped face byte-exact, report.css loads them, the pin is declared
  local f want got
  for f in $FONT_SHAS; do
    want=${f%%:*}; got=$(sha256sum "$REPO/backend/app/static/fonts/${f#*:}" 2>/dev/null | cut -d' ' -f1)
    [ "$got" = "$want" ] || { echo "missing or different: static/fonts/${f#*:}"; return 1; }
  done
  grep -q '@font-face { font-family: "Liberation Sans"' "$REPO/backend/app/static/css/report.css" || { echo "report.css has no @font-face"; return 1; }
  grep -qx 'weasyprint==70.0' "$REPO/backend/requirements.txt" || { echo "requirements.txt does not pin weasyprint==70.0"; return 1; }
  echo "the deployed code carries the shipped faces (5 files byte-exact), report.css loads them, requirements pin weasyprint==70.0"
}
apt_state() { dpkg-query -W -f='${db:Status-Abbrev} ${Version}\n' "$APT_PKG" 2>/dev/null | awk '$1 == "ii" { print $2 }'; }

main() {
  local vown before after delta rc out want got new
  # shellcheck disable=SC1091
  . "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT11 install ($MODE) · machine $(hostname -s) · head ?"; stop KIT "lib/icb_where.sh missing" "nothing was changed on prod. Paste the same line again."; }
  # shellcheck disable=SC1091
  . "$BASE/expected.env" 2>/dev/null || true
  icb_where "install: $MODE" "$REPO" ""
  case "$MODE" in preflight|apt|pip|verify|rollback) ;; *) stop KIT "unknown step '$MODE'" "nothing was changed on prod." ;; esac
  [ "$(id -u)" = 0 ] || stop KIT "run with sudo" "nothing was changed on prod."
  for v in EXPECT_MACHINE EXPECT_HEADS STAGED_FROM APT_PKG APT_VER FONT_SHAS; do
    [ -n "${!v:-}" ] || stop KIT "expected.env has no $v" "nothing was changed on prod. Tell the CA."
  done
  icb_where_check || stop WHERE "$WHERE_WHY" "nothing was changed on prod. Copy the whole window and paste it back to the CA."
  ( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "the kit's files do not match its SHA256SUMS" "nothing was changed on prod. Paste the same line again."
  vown=$(stat -c %U "$REPO/.venv") || stop KIT "cannot stat the venv" "nothing was changed on prod."
  [ "$vown" != root ] || stop KIT "the venv is owned by root: this kit installs as the venv owner only" "nothing was changed on prod. Tell the CA."
  mkdir -p "$BASE/pip/home" "$BASE/pip/tmp" && chown -R "$vown" "$BASE/pip" && chmod -R a+rX "$BASE" || stop KIT "cannot prepare $BASE/pip" "nothing was changed on prod."
  say "kit staged from ${STAGED_FROM:0:7} · venv owner $vown · $APT_PKG wanted at $APT_VER, installed: $(apt_state || true) · $(date '+%Y-%m-%d %H:%M:%S %Z')"

  case "$MODE" in
  preflight)
    say "1. apt-get -s install --no-install-recommends --no-upgrade $APT_PKG=$APT_VER (a simulation)"
    apt_sim install --no-install-recommends --no-upgrade "$APT_PKG=$APT_VER" | grep -E '^(Inst|Remv|E:|[0-9]+ upgraded)' | sed 's/^/   /' || true
    say "2. pip install --dry-run --no-deps -r the lock (as nobody: nothing is installed)"
    chown -R nobody "$BASE/pip"
    pip_as nobody -m pip install --dry-run --no-deps -r "$LOCK" 2>&1 | grep -E '^(Would install|ERROR|Requirement already)' | sed 's/^/   /' || true
    chown -R "$vown" "$BASE/pip"
    say "3. the deployed code"
    echo "   $(code_fonts || echo '(not yet: the pip step will refuse until the RT11 code is deployed)')"
    say "4. the gate in the deployed code, read now (the running workers read it at their start)"
    echo "   $(pip_as "$vown" -I -B -c "import sys; sys.path.insert(0, '$REPO/backend'); from app import report_engine as r; print('check_letterhead_quote() =', r.check_letterhead_quote() if hasattr(r, 'check_letterhead_quote') else 'absent (code before #230)')" 2>&1 | tail -n1)"
    echo; echo "######## DONE (read only): preflight" ;;
  apt)
    if [ "$(apt_state)" = "$APT_VER" ]; then echo "   $APT_PKG $APT_VER is already installed: nothing to do"; echo; echo "######## DONE: apt (already installed)"; return 0; fi
    out=$(apt_sim install --no-install-recommends --no-upgrade "$APT_PKG=$APT_VER")
    printf '%s\n' "$out" | grep -E '^(Inst|Remv|E:|[0-9]+ upgraded)' | sed 's/^/   /' || true
    want="Inst $APT_PKG ($APT_VER "
    [ "$(printf '%s\n' "$out" | grep -c '^Inst ')" = 1 ] && printf '%s\n' "$out" | grep -qF "$want" \
      && printf '%s\n' "$out" | grep -q '^0 upgraded, 1 newly installed, 0 to remove' \
      || stop APT "the simulation is not exactly '$want…' with 0 upgraded and 0 removed" "nothing was installed. Copy the whole window and paste it back to the CA."
    before=$(dpkg-query -W -f='${db:Status-Abbrev} ${Package} ${Version}\n' 2>/dev/null | sort)
    say "apt-get install -y --no-install-recommends --no-upgrade $APT_PKG=$APT_VER"
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends --no-upgrade "$APT_PKG=$APT_VER" 2>&1 | grep -E '^(Setting up|Unpacking|E:|[0-9]+ upgraded)' | sed 's/^/   /'
    rc=${PIPESTATUS[0]}
    after=$(dpkg-query -W -f='${db:Status-Abbrev} ${Package} ${Version}\n' 2>/dev/null | sort)
    delta=$(diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep '^[<>]' || true)
    echo "   dpkg list, before -> after: ${delta:-no change}"
    [ "$rc" = 0 ] || stop APT "apt-get install ended with exit $rc" "read the lines above; dpkg's list is printed. Copy the whole window and paste it back to the CA."
    [ "$delta" = "> ii  $APT_PKG $APT_VER" ] || stop APT "the dpkg list changed by more (or less) than '$APT_PKG $APT_VER'" "Copy the whole window and paste it back to the CA."
    echo; echo "######## DONE: apt — $APT_PKG $APT_VER installed; nothing else changed" ;;
  pip)
    out=$(code_fonts) || stop ORDER "the deployed code is not RT11's ($out)" "nothing was installed: deploy the RT11 code first (a gate reading True on the old code would offer quotes in a fallback face)."
    echo "   $out"
    [ "$(apt_state)" = "$APT_VER" ] || stop ORDER "$APT_PKG $APT_VER is not installed" "nothing was installed: run the apt step first."
    before=$(venv_list "$vown")
    if [ -z "$(comm -23 <(tr 'A-Z_' 'a-z-' < "$LOCK" | grep . | sort) <(printf '%s\n' "$before"))" ]; then
      echo "   every package of the lock is already installed at its version: nothing to do"
      echo; echo "######## DONE: pip (already installed). Next: restart icb-backend, then verify"; return 0
    fi
    out=$(pip_as "$vown" -m pip install --dry-run --no-deps -r "$LOCK" 2>&1); rc=$?
    printf '%s\n' "$out" | grep -E '^(Would install|ERROR)' | sed 's/^/   /' || true
    [ "$rc" = 0 ] || stop PIP "pip --dry-run failed (exit $rc): $(printf '%s\n' "$out" | tail -n1)" "nothing was installed. Copy the whole window and paste it back to the CA."
    new=$(printf '%s\n' "$out" | sed -n 's/^Would install //p' | tr ' ' '\n' | sed 's/-[^-]*$//' | tr 'A-Z_' 'a-z-' | grep . | sort)
    [ "$new" = "$(lock_names)" ] || stop PIP "the dry-run would install [$(echo $new)], not exactly the lock [$(echo $(lock_names))]" "nothing was installed. Copy the whole window and paste it back to the CA."
    say "pip install --no-deps -r the lock, as $vown"
    pip_as "$vown" -m pip install --no-deps -r "$LOCK" 2>&1 | grep -E '^(Successfully installed|ERROR)' | sed 's/^/   /'
    rc=${PIPESTATUS[0]}
    after=$(venv_list "$vown")
    delta=$(diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") | sed -n 's/^> //p' | tr 'A-Z_' 'a-z-' | sort)
    echo "   the venv's packages, new: $(echo $delta)"
    [ "$rc" = 0 ] || stop PIP "pip install ended with exit $rc" "the step is half done: run 'rollback', then tell the CA."
    [ "$(diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep -c '^<')" = 0 ] || stop PIP "an installed package changed" "run 'rollback', then tell the CA."
    [ "$delta" = "$(tr 'A-Z_' 'a-z-' < "$LOCK" | grep . | sort)" ] || stop PIP "the venv gained [$(echo $delta)], not exactly the lock" "run 'rollback', then tell the CA."
    got=$(pip_as "$vown" -I -B -c 'import weasyprint; print(weasyprint.__version__)' 2>&1 | tail -n1)
    [ "$got" = 70.0 ] || stop PIP "weasyprint imports as '$got', not 70.0" "run 'rollback', then tell the CA."
    echo "   weasyprint imports: $got"
    echo; echo "######## DONE: pip — the lock's 10 packages installed as $vown; nothing else changed. Next: restart icb-backend, then verify" ;;
  verify)
    out=$(code_fonts) || stop VERIFY "the deployed code is not RT11's ($out)" "nothing was changed."
    say "the five quote templates at REV 0 and REV 1, rendered with the deployed code as $vown"
    pip_as "$vown" -I -B "$BASE/rt11_verify.py" "$REPO/backend" 2>&1 | grep -E '^(   |VERIFY:|Traceback|[A-Za-z]*Error)' ; rc=${PIPESTATUS[0]}
    [ "$rc" = 0 ] || stop VERIFY "the renders or the gate are not right (exit $rc): read the lines above" "nothing was changed. Copy the whole window and paste it back to the CA."
    local wp started
    wp=$(stat -c %Y "$(dirname "$(pip_as "$vown" -I -B -c 'import weasyprint; print(weasyprint.__file__)' 2>/dev/null | tail -n1)")" 2>/dev/null || echo 0)
    started=$(date -d "$(systemctl show icb-backend -p ActiveEnterTimestamp --value 2>/dev/null)" +%s 2>/dev/null || echo 0)
    if [ "$started" -gt "$wp" ]; then echo "   icb-backend started $(date -d "@$started" '+%H:%M:%S'), after WeasyPrint was installed: its workers read the gate True"
    else echo "   !! icb-backend started BEFORE WeasyPrint was installed: restart it, then verify again (the workers read the gate at start-up)"; fi
    echo; echo "######## DONE (read only): verify — 10/10 renders correct, faces Liberation, the gate True" ;;
  rollback)
    before=$(venv_list "$vown")
    present=$(lock_names | while read -r n; do printf '%s\n' "$before" | grep -q "^$n==" && echo "$n"; done)
    if [ -n "$present" ]; then
      say "pip uninstall -y $(echo $present), as $vown"
      pip_as "$vown" -m pip uninstall -y $present 2>&1 | grep -E '^(  Successfully uninstalled|ERROR|WARNING)' | sed 's/^/   /' || true
    else echo "   none of the lock's packages is installed"; fi
    after=$(venv_list "$vown")
    [ -z "$(lock_names | while read -r n; do printf '%s\n' "$after" | grep -q "^$n==" && echo "$n"; done)" ] || stop ROLLBACK "a lock package is still in the venv" "Copy the whole window and paste it back to the CA."
    if [ -n "$(apt_state)" ]; then
      out=$(apt_sim remove "$APT_PKG")
      printf '%s\n' "$out" | grep -E '^(Remv|Inst|E:)' | sed 's/^/   /' || true
      [ "$(printf '%s\n' "$out" | grep -c '^Remv ')" = 1 ] && [ "$(printf '%s\n' "$out" | grep -c '^Inst ')" = 0 ] \
        || stop ROLLBACK "removing $APT_PKG would remove more than it (or install something)" "pip is rolled back; the apt package stays. Tell the CA."
      DEBIAN_FRONTEND=noninteractive apt-get remove -y "$APT_PKG" 2>&1 | grep -E '^(Removing|E:)' | sed 's/^/   /' || true
      [ -z "$(apt_state)" ] || stop ROLLBACK "$APT_PKG is still installed" "pip is rolled back. Tell the CA."
    else echo "   $APT_PKG is not installed"; fi
    echo; echo "######## DONE: rollback — the lock's packages and $APT_PKG are gone. Restart icb-backend: the gate reads False, the SAP line returns" ;;
  esac
}

[ -L "$REPORT" ] && { echo "######## STOP [KIT]: $REPORT is a symbolic link: refusing to write through it"; exit 1; }
rm -f -- "$REPORT"
( set -C; : > "$REPORT" ) 2>/dev/null || { echo "######## STOP [KIT]: cannot create $REPORT"; exit 1; }
chmod 600 "$REPORT"
main 2>&1 | tee -a "$REPORT"
rc=${PIPESTATUS[0]}
rm -rf --one-file-system -- "$BASE" "$BASE.tar"
if [ -e "$BASE" ] || [ -e "$BASE.tar" ]; then kit="STILL THERE"; else kit="removed"; fi
# the LAST write to the report comes BEFORE it is handed over (fs.protected_regular=2: RT11_RULING_0A)
echo "== the kit on prod (/tmp/icb-rt11-install and its .tar): $kit; the report waits at $REPORT for the laptop" | tee -a "$REPORT"
owner=${SUDO_USER:-}
if [ -n "$owner" ] && [ "$owner" != root ]; then chown "$owner" "$REPORT" 2>/dev/null || true; fi
chmod 644 "$REPORT"
exit "$rc"
