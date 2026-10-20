#!/bin/bash
# RT7 window staging simulation, run as root in WSL:  bash run_window_sim.sh [kit-branch]
# The REAL ops/prod-rt7/mkstage_window.sh (and through it ops/prod-release-v1.61.1/mkstage.sh) over a sim origin that
# carries the branch and an annotated v1.61.1 tag. Proves: the three kits and the two Windows lines are staged (every
# placeholder filled, ASCII, LF); the All and door kits carry REBOOT_GUARD=1; and on a fake prod (hostname
# icb-mes-prod, the real icb_where.sh) the All kit's first line names the boot time and it REFUSES an unstamped kit
# and one staged before the boot, while a stamped kit passes the place check. Cleans its own folder at the end.
set -u
KIT=${1:-rt7/audit-truth}
WIN=/mnt/c/Users/micge/Documents
REPO=$WIN/icb-platform
SIM=/root/rt7simW-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{opt,tmp,stage,state,bin}
trap 'rm -rf "$SIM"' EXIT
PASS=0; FAIL=0
ok() { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1"; }

$G clone -q --bare --single-branch --branch backport/v1.39-base "$REPO" "$SIM/origin.git" || exit 1
$G -C "$SIM/origin.git" fetch -q "$REPO" "+refs/remotes/origin/backport/v1.39-base:refs/heads/backport/v1.39-base" "+refs/tags/v1.61.0:refs/tags/v1.61.0" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$REPO" "$KIT" && git -c user.email=sim@x -c user.name=sim merge -q --no-edit FETCH_HEAD || exit 1
git push -q origin backport/v1.39-base && git fetch -q origin --tags
TARGET=$(git rev-parse HEAD)
git -c user.email=sim@x -c user.name=sim tag -a v1.61.1 -m "sim v1.61.1" "$TARGET" && git push -q origin v1.61.1
bash ops/prod-rt7/mkstage_window.sh "$SIM/stage" "$TARGET" > "$SIM/stage.log" 2>&1 || { cat "$SIM/stage.log"; exit 1; }
grep -m1 '^staged the RT7 window' "$SIM/stage.log"

echo "== the staging"
for t in icb-release-v1.61.1 icb-rt2-all icb-rt2-doors; do [ -s "$SIM/stage/$t.tar" ] && ok "$t.tar" || bad "$t.tar missing"; done
for ps in run_window_copy.ps1 run_window_fetch.ps1; do
  f="$SIM/stage/$ps"
  { [ -s "$f" ] && ! grep -q '__[A-Z_]*__' "$f" && ! LC_ALL=C grep -q $'[\x80-\xff]' "$f"; } && ok "$ps filled, ASCII" || bad "$ps"
  grep -q '/^btime/' "$f" && grep -q 'boot $vmBoot' "$f" && ok "$ps prints prod's boot time" || bad "$ps boot"
done
grep -q 'date +%s > .staged_at' "$SIM/stage/run_window_copy.ps1" && ok "the copy line stamps each kit" || bad "copy line stamp"
for k in icb-rt2-all icb-rt2-doors; do grep -qx 'REBOOT_GUARD=1' "$SIM/stage/$k/expected.env" && ok "$k: REBOOT_GUARD=1" || bad "$k guard"; done
grep -q '^KIT_DIR=\$BASE' "$SIM/stage/icb-release-v1.61.1/release.sh" && ok "the release kit sets KIT_DIR" || bad "release KIT_DIR"
CR=$(find "$SIM/stage" -name '*.sh' -print0 | xargs -0 cat | tr -cd '\r' | wc -c); [ "$CR" = 0 ] && ok "no CR in any staged script" || bad "$CR CR bytes"

echo "== the All kit on a fake prod (the place check only)"
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$(git rev-parse v1.61.0^{commit})"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
printf 'DATABASE_URL=postgresql+psycopg://icb_app:sim-not-real@127.0.0.1:5432/icb_platform\nSESSION_SECRET=x\n' > "$SIM/etc/icb/backend.env"
cat > "$SIM/bin/psql" <<'PS'
#!/bin/bash
case "$*" in *current_database*) echo icb_platform ;; *) echo "psql stub: $*" >&2; exit 3 ;; esac
PS
chmod +x "$SIM/bin/psql"
tar -xf "$SIM/stage/icb-rt2-all.tar" -C "$SIM/tmp" || exit 1
A=$SIM/tmp/icb-rt2-all; BOOT=$(awk '/^btime/{print $2}' /proc/stat)
allrun() {
  unshare -m -u bash -c "hostname icb-mes-prod && mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc &&
     mount --bind '$SIM/tmp' /tmp && export PATH='$SIM/bin':\$PATH && bash /tmp/icb-rt2-all/rt2_all.sh pre" > "$SIM/all.log" 2>&1
}
rm -f "$A/.staged_at"; allrun
head -n1 "$SIM/all.log" | grep -qE '^######## RT7 All pre \(read only\) · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head [0-9a-f]{7} · boot [0-9]{4}-' \
  && ok "first line: RT7, machine, db, head, BOOT TIME" || { bad "first line"; head -n2 "$SIM/all.log"; }
grep -q 'STOP \[WHERE\]: WRONG PLACE — the kit has no staging stamp' "$SIM/all.log" && ok "unstamped kit refused" || { bad "unstamped"; tail -n3 "$SIM/all.log"; }
echo $((BOOT - 60)) > "$A/.staged_at"; allrun
grep -q "STOP \[WHERE\]: WRONG PLACE — the kit was staged .*before this machine's last boot" "$SIM/all.log" && ok "kit staged before the boot refused" || { bad "pre-boot"; tail -n3 "$SIM/all.log"; }
date +%s > "$A/.staged_at"; allrun
grep -q 'STOP \[WHERE\]' "$SIM/all.log" && { bad "a stamped kit was refused"; tail -n3 "$SIM/all.log"; } || ok "a stamped kit passes the place check (it goes on to the next check)"
echo
echo "== $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
