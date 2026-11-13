#!/bin/bash
# RT11 install kit — the WSL scenarios: the STAGED kit (mkstage_install.sh's output, byte for byte) on a fake prod in
# the Ubuntu 24.04 clone of prod (icb-noble-rt11), as root in that distro:
#
#     bash ops/prod-rt11/install/sim/run_sim.sh /mnt/c/Users/micge/Documents/icb-rt11-stage/install <lane commit>
#
# The fake prod (../../sim/fakeprod.sh: prod's /tmp rule, sudo user mickeyger) runs the RT11 code (<lane commit>,
# fetched read-only from Michael's clone's object store), and its venv — a copy of the prod-like base venv — is owned
# by `icb`, as on prod. apt and pip are REAL: libharfbuzz-subset0 is really installed and removed in the clone, the
# lock is really installed into the fake venv from PyPI. Order: preflight → the negative controls that must change
# nothing → apt → pip → verify → rollback, each with its read-backs. The clone is left as found (the package removed).
set -u
STAGE=${1:?usage: run_sim.sh <stage dir, as /mnt/c/...> <lane commit>}
LANE=${2:?lane commit}
HERE=$(cd "$(dirname "$0")" && pwd)
[ -f "$STAGE/icb-rt11-install.tar" ] && [ -f "$STAGE/rt11_install_vm.sh" ] || { echo "SIM: no staged kit in $STAGE"; exit 2; }
SIM=/root/rt11isim-$(date +%s)
mkdir -p "$SIM" || exit 2
APT_PKG=libharfbuzz-subset0
cleanup() { DEBIAN_FRONTEND=noninteractive apt-get remove -y -qq "$APT_PKG" >/dev/null 2>&1; rm -rf "$SIM"; }
trap cleanup EXIT
dpkg -s "$APT_PKG" >/dev/null 2>&1 && { echo "SIM: $APT_PKG is already installed in the clone: remove it first"; exit 2; }
# shellcheck disable=SC1091
. "$HERE/../../sim/fakeprod.sh"
fp_prod || exit 2
( cd "$SIM/opt/icb-platform" && git -c protocol.file.allow=always fetch -q --depth 1 "file://$REPO_WIN" "$LANE" \
    && git -c advice.detachedHead=false checkout -q --detach FETCH_HEAD ) || { echo "SIM: could not fetch $LANE"; exit 2; }
git -C "$SIM/opt/icb-platform" rev-parse HEAD > "$SIMSTATE/head"
grep -q '^icb:' "$SIM/etc/passwd" || { echo 'icb:x:1600:1600:sim venv owner:/nonexistent:/usr/sbin/nologin' >> "$SIM/etc/passwd"; echo 'icb:x:1600:' >> "$SIM/etc/group"; }
chown -R 1600:1600 "$SIM/opt/icb-platform/.venv"
echo "== fake prod: head $(cut -c1-7 "$SIMSTATE/head"), venv owner icb (uid 1600), $APT_PKG absent, $(wc -c < "$STAGE/icb-rt11-install.tar") byte kit"
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); echo "  ok    $*"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL  $*"; }
KITLINE='== the kit on prod (/tmp/icb-rt11-install and its .tar): removed; the report waits at /tmp/icb-rt11-install-report.txt for the laptop'
venv_sum() { ( cd "$SIM/opt/icb-platform/.venv" && find . -type f -not -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16 ); }
dpkg_sum() { dpkg-query -W -f='${db:Status-Abbrev} ${Package} ${Version}\n' | sort | sha256sum | cut -c1-16; }
reset() {
  find "$SIM/tmp" -mindepth 1 -delete
  echo icb-mes-prod > "$SIMSTATE/hostname"
  cp "$STAGE/icb-rt11-install.tar" "$STAGE/rt11_install_vm.sh" "$SIM/tmp/" && mv "$SIM/tmp/rt11_install_vm.sh" "$SIM/tmp/icb-rt11-install-vm.sh"
}
step() { # $1 = the step; $2 = a hook run between unpack and the step
  reset
  fp_run "bash /tmp/icb-rt11-install-vm.sh where" >/dev/null 2>&1
  U=$(fp_run "bash /tmp/icb-rt11-install-vm.sh unpack" 2>&1); URC=$?
  [ -n "${2:-}" ] && eval "$2"
  C=$(fp_run "sudo bash /tmp/icb-rt11-install/rt11_install.sh $1" 2>&1); CRC=$?
  REP=$(cat "$SIM/tmp/icb-rt11-install-report.txt" 2>/dev/null)
  REPOWN=$(stat -c %u "$SIM/tmp/icb-rt11-install-report.txt" 2>/dev/null)
  R=$(fp_run "bash /tmp/icb-rt11-install-vm.sh readback" 2>&1); RRC=$?
  LEFT=$(ls -A "$SIM/tmp" | tr '\n' ' ')
}
clean() { [ "$RRC" = 0 ] && [ -z "$LEFT" ] && [ "$REPOWN" = 1500 ] && [ "$(tail -n1 <<< "$REP")" = "$KITLINE" ] && ! grep -q 'Permission denied' <<< "$C"; }
show() { echo "$C" | tail -n "${1:-12}" | sed 's/^/        | /'; }
V0=$(venv_sum); D0=$(dpkg_sum)

echo "== 1. preflight (read only)"
step preflight
[ "$CRC" = 0 ] && grep -q '^######## DONE (read only): preflight$' <<< "$C" && clean \
  && grep -q "Inst $APT_PKG (8.3.0-2build2 " <<< "$C" \
  && grep -q '^   Would install brotli-1.2.1 cssselect2-0.10.1 fonttools-4.67.0 pydyf-0.13.0 pyphen-0.18.1 tinycss2-1.5.1 tinyhtml5-2.1.0 weasyprint-70.0 webencodings-0.6.1 zopfli-0.4.3$' <<< "$C" \
  && grep -q 'the deployed code carries the shipped faces' <<< "$C" && grep -q 'check_letterhead_quote() = False' <<< "$C" \
  && [ "$(venv_sum)" = "$V0" ] && [ "$(dpkg_sum)" = "$D0" ] \
  && ok "preflight: apt -s = the one package, pip --dry-run = exactly the lock, the code carries the faces, the gate False; venv and dpkg unchanged; /tmp rule held" \
  || { bad "preflight: exit $CRC"; show 20; }
head -n1 <<< "$C" | grep -q '^######## RT11 install: preflight · machine icb-mes-prod · db ? @ ? · head ' && ok "its first line names the step, the machine and the head" || bad "first line: $(head -n1 <<< "$C")"

echo "== 2. negative controls that must change nothing"
step pip
[ "$CRC" = 1 ] && grep -q "STOP \[ORDER\]: $APT_PKG 8.3.0-2build2 is not installed" <<< "$C" && clean && [ "$(venv_sum)" = "$V0" ] \
  && ok "pip before apt: STOP [ORDER], nothing installed" || { bad "pip before apt: exit $CRC"; show; }
F=backend/app/static/fonts/LiberationSans-Bold.ttf
step pip "rm -f '$SIM/opt/icb-platform/$F'"
git -C "$SIM/opt/icb-platform" checkout -q -- "$F"
[ "$CRC" = 1 ] && grep -q 'STOP \[ORDER\]: the deployed code is not RT11.s (missing or different: static/fonts/LiberationSans-Bold.ttf)' <<< "$C" && [ "$(venv_sum)" = "$V0" ] \
  && ok "pip on code without the shipped faces: STOP [ORDER], nothing installed" || { bad "pip without fonts: exit $CRC"; show; }
cat > "$SIM/bin/apt-get" <<'EOF'
#!/bin/bash
# NC stand-in: the simulation of the install also upgrades libharfbuzz0b (as a stale prod would)
if [[ " $* " == *" -s "* && " $* " == *" install "* ]]; then
  /usr/bin/apt-get "$@"; echo "Inst libharfbuzz0b [8.3.0-2build1] (8.3.0-2build2 Ubuntu:24.04/noble [amd64])"; exit 0
fi
exec /usr/bin/apt-get "$@"
EOF
chmod +x "$SIM/bin/apt-get"
step apt
rm -f "$SIM/bin/apt-get"
[ "$CRC" = 1 ] && grep -q 'STOP \[APT\]: the simulation is not exactly' <<< "$C" && [ "$(dpkg_sum)" = "$D0" ] \
  && ok "apt whose simulation would also upgrade a package: STOP [APT], nothing installed" || { bad "apt NC: exit $CRC"; show; }
echo icb-mes-dev > "$SIMSTATE/hostname"
reset; echo icb-mes-dev > "$SIMSTATE/hostname"; fp_run "bash /tmp/icb-rt11-install-vm.sh unpack" >/dev/null 2>&1
C=$(fp_run "sudo bash /tmp/icb-rt11-install/rt11_install.sh apt" 2>&1); CRC=$?
fp_run "bash /tmp/icb-rt11-install-vm.sh readback" >/dev/null 2>&1
[ "$CRC" = 1 ] && grep -q "STOP \[WHERE\]: .*machine is 'icb-mes-dev'" <<< "$C" && [ "$(dpkg_sum)" = "$D0" ] \
  && ok "the wrong machine: STOP [WHERE], nothing installed" || { bad "wrong machine: exit $CRC"; show; }

echo "== 3. apt (real), and again"
step apt
DELTA_OK=$(dpkg-query -W -f='${db:Status-Abbrev} ${Version}\n' "$APT_PKG" 2>/dev/null)
[ "$CRC" = 0 ] && grep -q "^######## DONE: apt — $APT_PKG 8.3.0-2build2 installed; nothing else changed$" <<< "$C" \
  && grep -q "dpkg list, before -> after: > ii  $APT_PKG 8.3.0-2build2" <<< "$C" && [ "$DELTA_OK" = "ii  8.3.0-2build2" ] && clean \
  && ok "apt: the one package installed (8.3.0-2build2); the dpkg list changed by that line only" || { bad "apt: exit $CRC"; show 20; }
D1=$(dpkg_sum)
step apt
[ "$CRC" = 0 ] && grep -q 'already installed: nothing to do' <<< "$C" && [ "$(dpkg_sum)" = "$D1" ] && ok "apt again: already installed, nothing done" || { bad "apt again"; show; }

echo "== 4. pip (real, from PyPI, as icb), and again"
step pip
[ "$CRC" = 0 ] && grep -q '^######## DONE: pip — the lock.s 10 packages installed as icb; nothing else changed' <<< "$C" \
  && grep -q '^   weasyprint imports: 70.0$' <<< "$C" && clean \
  && [ "$(stat -c %u "$SIM/opt/icb-platform/.venv/lib/python3.12/site-packages/weasyprint/__init__.py")" = 1600 ] \
  && ok "pip: exactly the lock installed, owned by icb; weasyprint imports 70.0" || { bad "pip: exit $CRC"; show 20; }
V1=$(venv_sum)
step pip
[ "$CRC" = 0 ] && grep -q 'already installed at its version: nothing to do' <<< "$C" && [ "$(venv_sum)" = "$V1" ] && ok "pip again: already installed, nothing done" || { bad "pip again"; show; }

echo "== 5. verify (read only), with its negative control"
step verify
[ "$CRC" = 0 ] && grep -q '^VERIFY: 10/10 renders correct; gate True$' <<< "$C" && grep -q '^######## DONE (read only): verify' <<< "$C" \
  && [ "$(grep -c '^   ok   ' <<< "$C")" = 10 ] && [ "$(venv_sum)" = "$V1" ] && clean \
  && ok "verify: the five quote templates at REV 0 and REV 1 with the deployed code: 10/10, faces Liberation; the gate True; venv unchanged" \
  || { bad "verify: exit $CRC"; show 16; }
CSS=backend/app/static/css/report.css
# (dropping "Liberation Sans" from the stack is NOT a failure: fontconfig's metric alias maps Arial to the loaded
# Liberation Sans. A face that does not load is: the Regular @font-face points at a file that is not there.)
step verify "sed -i 's#url(\"../fonts/LiberationSans-Regular.ttf\")#url(\"../fonts/missing.ttf\")#' '$SIM/opt/icb-platform/$CSS'"
git -C "$SIM/opt/icb-platform" checkout -q -- "$CSS"
[ "$CRC" = 1 ] && grep -q 'STOP \[VERIFY\]' <<< "$C" && grep -q 'a fallback face' <<< "$C" \
  && ok "verify NC: the Regular face does not load -> a fallback face in the renders -> STOP [VERIFY]" || { bad "verify NC: exit $CRC"; show 14; }

echo "== 6. rollback (real)"
step rollback
[ "$CRC" = 0 ] && grep -q '^######## DONE: rollback' <<< "$C" && [ "$(venv_sum)" = "$V0" ] && [ "$(dpkg_sum)" = "$D0" ] && clean \
  && ok "rollback: the venv is byte-identical to before pip, the dpkg list to before apt" || { bad "rollback: exit $CRC (venv $(venv_sum) vs $V0, dpkg $(dpkg_sum) vs $D0)"; show 16; }

echo "== $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
