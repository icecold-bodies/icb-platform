#!/bin/bash
# RT11 §3.0 prod check — the WSL scenarios: the STAGED kit (mkstage_check.sh's output, byte for byte) on a fake prod
# (fakeprod.sh) inside the Ubuntu 24.04 clone of prod. As root in that distro:
#
#     bash ops/prod-rt11/sim/run_sim.sh /mnt/c/Users/micge/Documents/icb-rt11-stage/check
#
# Every scenario starts from an empty fake /tmp, copies the stage's tar + helper there, and runs the line's four
# remote commands as prod would (where; unpack; sudo the check; readback). The happy path must end DONE with a SUMMARY
# whose apt and pip parts are the clone's REAL answers, the venv and /opt untouched, the kit gone and /tmp empty after
# the readback; every negative control must STOP for its own reason (or, pip offline, report it and still end DONE),
# remove the kit, and leave /tmp empty after the readback. The sim folder is removed at the end (the WSL disk lesson).
set -u
STAGE=${1:?usage: run_sim.sh <stage dir, as /mnt/c/...>}
HERE=$(cd "$(dirname "$0")" && pwd)
[ -f "$STAGE/icb-rt11-check.tar" ] && [ -f "$STAGE/rt11_vm.sh" ] || { echo "SIM: no staged kit in $STAGE"; exit 2; }
SIM=/root/rt11sim-$(date +%s)
mkdir -p "$SIM" || exit 2
trap 'rm -rf "$SIM"' EXIT
# shellcheck disable=SC1091
. "$HERE/fakeprod.sh"
fp_prod || exit 2
echo "== fake prod: head $(cut -c1-7 "$SIMSTATE/head"), $(wc -c < "$STAGE/icb-rt11-check.tar") byte kit from $STAGE"
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); echo "  ok    $*"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL  $*"; }

reset() {
  find "$SIM/tmp" -mindepth 1 -delete
  rm -f "$SIMSTATE/not_read_only"; fp_pip_offline off
  echo icb-mes-prod > "$SIMSTATE/hostname"; echo 0053 > "$SIMSTATE/alembic"
  cp "$STAGE/icb-rt11-check.tar" "$STAGE/rt11_vm.sh" "$SIM/tmp/" && mv "$SIM/tmp/rt11_vm.sh" "$SIM/tmp/icb-rt11-vm.sh"
}
# the line's four remote commands; $1 = a hook run between unpack and the check (the scenario's change)
line() {
  local hook=${1:-}
  W=$(fp_run "bash /tmp/icb-rt11-vm.sh where" 2>&1)
  U=$(fp_run "bash /tmp/icb-rt11-vm.sh unpack" 2>&1); URC=$?
  [ -n "$hook" ] && eval "$hook"
  C=$(fp_run "sudo bash /tmp/icb-rt11-check/rt11_check.sh" 2>&1); CRC=$?
  REP=$(cat "$SIM/tmp/icb-rt11-check-report.txt" 2>/dev/null)
  KITLEFT=$(ls -A "$SIM/tmp" | grep -E '^icb-rt11-check(\.tar)?$' | tr '\n' ' ')
  R=$(fp_run "bash /tmp/icb-rt11-vm.sh readback" 2>&1); RRC=$?
  LEFT=$(ls -A "$SIM/tmp" | tr '\n' ' ')
}
expect_stop() { # $1 label, $2 the STOP tag, $3 a phrase the STOP line must carry
  if [ "$CRC" = 1 ] && grep -q "######## STOP \[$2\]: .*$3" <<< "$C" && [ -z "$KITLEFT" ] && [ "$RRC" = 0 ] && [ -z "$LEFT" ] \
     && grep -q "######## STOP \[$2\]" <<< "$REP"; then
    ok "$1: STOP [$2] ($3), exit 1; the kit removed itself; the report carries the STOP; /tmp empty after the readback"
  else
    bad "$1: exit $CRC, kit left '$KITLEFT', readback $RRC, /tmp '$LEFT'"; echo "$C" | tail -n 8 | sed 's/^/        | /'
  fi
}
venv_sum() { ( cd "$SIM/opt/icb-platform/.venv" && find . -type f -not -name pip.conf -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16 ); }

echo "== 1. the happy path"
reset; V0=$(venv_sum); line
[ "$(head -n1 <<< "$W")" = icb-mes-prod ] && [ "$(sed -n 2p <<< "$W")" = "$(cat "$SIMSTATE/head")" ] && ok "where: machine, HEAD, boot ($(sed -n 3p <<< "$W"))" || bad "where: $W"
[ "$URC" = 0 ] && grep -q "unpacked, verified (SHA256SUMS) and stamped" <<< "$U" && ok "unpack: verified and stamped" || bad "unpack: $U"
[ "$CRC" = 0 ] && grep -q '^######## DONE (read only)$' <<< "$C" && ok "the check: exit 0, ends DONE (read only)" || { bad "the check: exit $CRC"; echo "$C" | tail -n 20 | sed 's/^/        | /'; }
head -n1 <<< "$C" | grep -q '^######## RT11 prod check (read only) · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head ' \
  && ok "its first line names the machine, the database and the head" || bad "first line: $(head -n1 <<< "$C")"
S=$(grep '^SUMMARY: ' <<< "$C")
echo "        $S"
grep -qE '^SUMMARY: Ubuntu 24\.04\.[0-9]+ LTS · 3\.12\.3 · pango 1\.52\.1[^ ]* harfbuzz 8\.3\.0[^ ]* · harfbuzz-subset (absent|installed) · apt: [0-9]+ new, 0 upgraded · pip: [0-9]+ new, 0 changed · weasyprint absent · quote\.generate: admin\+full\+user \(4 users by role\) · bodies with a template: 5 of 7$' <<< "$S" \
  && ok "the SUMMARY: the clone's real release, python, libraries, apt and pip answers; the fixture's roles and bodies" || bad "the SUMMARY's shape"
grep -q '^   new: weasyprint 70.0$' <<< "$C" && ! grep -q 'CHANGES AN INSTALLED PACKAGE' <<< "$C" \
  && ok "pip --dry-run (real, against PyPI): weasyprint 70.0 is new and no installed package changes" || bad "pip lines: $(grep -E '^   (new|CHANGES)' <<< "$C" | head -n3)"
grep -qE '^   Inst libharfbuzz-subset0 \(' <<< "$C" || grep -q 'harfbuzz-subset installed' <<< "$S" \
  && ok "apt-get -s (real): libharfbuzz-subset0 would be newly installed, or is already there" || bad "apt lines: $(grep -E '^   (Inst|E:)' <<< "$C")"
grep -q '^   role sales: 3 user(s) — does not hold it$' <<< "$C" && grep -q 'per-user overrides (role | allow/deny | count): sales | allow | 2' <<< "$C" \
  && ok "the role lines and the override line are read and labelled" || bad "role lines"
[ "$(venv_sum)" = "$V0" ] && ok "the deployed venv is byte-identical after the check (pip ran --dry-run as nobody)" || bad "the venv changed"
[ -z "$(git -C "$SIM/opt/icb-platform" status --porcelain --ignored -uall | grep -v '^!! .venv/' | head -n1)" ] \
  && ok "/opt/icb-platform: nothing new or changed (no __pycache__)" || bad "/opt changed: $(git -C "$SIM/opt/icb-platform" status --porcelain --ignored -uall | grep -v '^!! .venv/' | head -n3)"
grep -qi "sim-not-real\|postgresql://\|icb_app" <<< "$C$REP" && bad "a password, the URL or the db user reached the output" || ok "no password, URL or db user in the output"
[ -z "$KITLEFT" ] && ok "the kit removed itself when the check ended" || bad "kit left: $KITLEFT"
[ "$RRC" = 0 ] && [ -z "$LEFT" ] && grep -q "absent      /tmp/icb-rt11-vm.sh (removed itself)" <<< "$R" && ok "readback: every name absent, the helper removed itself, /tmp empty" || bad "readback $RRC: $R / left '$LEFT'"
[ "$(head -n1 <<< "$REP")" = "$(head -n1 <<< "$C")" ] && grep -q '^######## DONE' <<< "$REP" && ok "the report file = the window (first line to DONE)" || bad "the report differs from the window"

echo "== 2. pip cannot reach PyPI: reported, and the check still ends DONE"
reset; line 'fp_pip_offline on'
[ "$CRC" = 0 ] && grep -q '!! pip --dry-run FAILED' <<< "$C" && grep -q 'pip: ? new, ? changed' <<< "$C" && [ -z "$KITLEFT" ] && [ -z "$LEFT" ] \
  && ok "pip offline: '!! pip --dry-run FAILED' with its last lines, SUMMARY 'pip: ? new, ? changed', DONE, /tmp empty" || { bad "pip offline: exit $CRC"; echo "$C" | grep -A7 'pip install --dry-run' | sed 's/^/        | /'; }

echo "== 3. the negative controls: each STOPs for its own reason, and still leaves /tmp empty"
reset; echo icb-mes-dev > "$SIMSTATE/hostname"; line; expect_stop "the wrong machine" WHERE "machine is 'icb-mes-dev'"
reset; touch "$SIMSTATE/not_read_only"; line; expect_stop "a session that is not read-only" DB "not read-only"
reset; echo 0054 > "$SIMSTATE/alembic"; line; expect_stop "another schema head" DB "alembic_version is '0054'"
reset; line 'echo "weasyprint==99.0" >> "$SIM/tmp/icb-rt11-check/requirements-rt11.txt"'; expect_stop "a changed requirements file" KIT "do not match its SHA256SUMS"
reset; line 'rm -f "$SIM/tmp/icb-rt11-check/.staged_at"'; expect_stop "an unstamped kit" WHERE "no staging stamp"
reset; line 'echo 1 > "$SIM/tmp/icb-rt11-check/.staged_at"'; expect_stop "a kit staged before the last boot" WHERE "before this machine.s last boot"
reset; ( cd "$SIM/opt/icb-platform" && git -c user.email=sim@x -c user.name=sim commit -q --allow-empty -m other ) \
  && { line; expect_stop "prod at another commit" WHERE "code is at"; } ; git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q --detach "$(cat "$SIMSTATE/head")"

echo "== $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
