#!/bin/bash
# RT10 prod check — the WSL scenarios: the STAGED kit (mkstage_check.sh's output, byte for byte) on a fake prod
# (fakeprod.sh). As root in WSL:
#
#     bash ops/prod-rt10/sim/run_sim.sh /mnt/c/Users/micge/Documents/icb-rt10-stage/check
#
# Every scenario starts from an empty fake /tmp, copies the stage's tar + helper there, and runs the line's four
# remote commands as prod would (where; unpack; sudo the check; readback). The happy path must end DONE with the
# fixture's exact SUMMARY, the kit gone and /tmp empty after the readback; every other scenario must STOP for its
# own reason, still remove the kit, and leave /tmp empty after the readback. The sim folder is removed at the end
# (the WSL disk lesson).
set -u
STAGE=${1:?usage: run_sim.sh <stage dir, as /mnt/c/...>}
HERE=$(cd "$(dirname "$0")" && pwd)
[ -f "$STAGE/icb-rt10-check.tar" ] && [ -f "$STAGE/rt10_vm.sh" ] || { echo "SIM: no staged kit in $STAGE"; exit 2; }
SIM=/root/rt10sim-$(date +%s)
mkdir -p "$SIM" || exit 2
trap 'rm -rf "$SIM"' EXIT
# shellcheck disable=SC1091
. "$HERE/fakeprod.sh"
fp_prod || exit 2
echo "== fake prod: head $(cut -c1-7 "$SIMSTATE/head"), $(wc -c < "$STAGE/icb-rt10-check.tar") byte kit from $STAGE"
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); echo "  ok    $*"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL  $*"; }

reset() {
  find "$SIM/tmp" -mindepth 1 -delete
  rm -f "$SIMSTATE"/{not_read_only,py_fail}
  echo icb-mes-prod > "$SIMSTATE/hostname"; echo 0053 > "$SIMSTATE/alembic"
  cp "$STAGE/icb-rt10-check.tar" "$STAGE/rt10_vm.sh" "$SIM/tmp/" && mv "$SIM/tmp/rt10_vm.sh" "$SIM/tmp/icb-rt10-vm.sh"
}
# the line's four remote commands; $1 = a hook run between unpack and the check (the scenario's change)
line() {
  local hook=${1:-}
  W=$(fp_run "bash /tmp/icb-rt10-vm.sh where" 2>&1)
  U=$(fp_run "bash /tmp/icb-rt10-vm.sh unpack" 2>&1); URC=$?
  [ -n "$hook" ] && eval "$hook"
  C=$(fp_run "sudo bash /tmp/icb-rt10-check/rt10_check.sh" 2>&1); CRC=$?
  REP=$(cat "$SIM/tmp/icb-rt10-check-report.txt" 2>/dev/null)
  KITLEFT=$(ls -A "$SIM/tmp" | grep -E '^icb-rt10-check(\.tar)?$' | tr '\n' ' ')
  R=$(fp_run "bash /tmp/icb-rt10-vm.sh readback" 2>&1); RRC=$?
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

echo "== 1. the happy path (the fixture carries the defect's signature)"
reset; line
WANT="13 costings; 4 quote numbers with 2+ rows; 1 live duplicate versions; 1 accepted while a newer live revision existed; 1 jobs built from an older revision"
[ "$(head -n1 <<< "$W")" = icb-mes-prod ] && [ "$(sed -n 2p <<< "$W")" = "$(cat "$SIMSTATE/head")" ] && ok "where: machine, HEAD, boot ($(sed -n 3p <<< "$W"))" || bad "where: $W"
[ "$URC" = 0 ] && grep -q "unpacked, verified (SHA256SUMS) and stamped" <<< "$U" && ok "unpack: verified and stamped" || bad "unpack: $U"
if [ "$CRC" = 0 ] && grep -q "^######## DONE (read only): $WANT\$" <<< "$C"; then ok "the check: DONE with the fixture's exact SUMMARY"; else bad "the check: exit $CRC"; echo "$C" | tail -n 12 | sed 's/^/        | /'; fi
head -n1 <<< "$C" | grep -q '^######## RT10 prod check (read only) · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head ' \
  && ok "its first line names the machine, the database and the head" || bad "first line: $(head -n1 <<< "$C")"
grep -q "A2/09/2026  id 40 v1 REV 0 accepted 2026-09-03 11:00:00; id 41 v2 REV 1 (created 2026-09-02 08:30:00) was live then" <<< "$C" \
  && grep -q "A2/09/2026  job 900 (created 2026-09-03 11:00:05) from id 40 v1 REV 0; id 41 v2 REV 1" <<< "$C" \
  && ok "the signature is named: A2 REV 0 accepted while REV 1 was live, and its job" || bad "the signature lines are missing"
grep -q "C4/10/2026  version 2 on 2 live rows (ids 61, 62)" <<< "$C" && ok "the live duplicate is named (C4 v2 ×2)" || bad "live duplicate line missing"
! grep -q "B3/09/2026  id 50" <<< "$C" && ! grep -q "N1/10/2026  version 2" <<< "$C" \
  && ok "negative controls: B3 (accepted before REV 1 existed) and N1's deleted v2 rows are not named" || bad "an NC row was named"
grep -qi "customer\|contact\|sim-not-real\|postgresql://" <<< "$C$REP" && bad "a name, a password or the URL reached the output" || ok "no customer, contact, password or URL in the output"
[ -z "$KITLEFT" ] && ok "the kit removed itself when the check ended" || bad "kit left: $KITLEFT"
[ "$RRC" = 0 ] && [ -z "$LEFT" ] && grep -q "absent      /tmp/icb-rt10-vm.sh (removed itself)" <<< "$R" && ok "readback: every name absent, the helper removed itself, /tmp empty" || bad "readback $RRC: $R / left '$LEFT'"
[ "$(head -n1 <<< "$REP")" = "$(head -n1 <<< "$C")" ] && grep -q '^######## DONE' <<< "$REP" && ok "the report file = the window (first line to DONE)" || bad "the report differs from the window"
[ -z "$(find "$SIM/opt/icb-platform" -name __pycache__ | head -n1)" ] && ok "no __pycache__ under /opt/icb-platform" || bad "a __pycache__ appeared under /opt"

echo "== 2. the negative controls: each STOPs for its own reason, and still leaves /tmp empty"
reset; echo icb-mes-dev > "$SIMSTATE/hostname"; line; expect_stop "the wrong machine" WHERE "machine is 'icb-mes-dev'"
reset; touch "$SIMSTATE/not_read_only"; line; expect_stop "a session that is not read-only" DB "not read-only"
reset; echo 0054 > "$SIMSTATE/alembic"; line; expect_stop "another schema head" DB "alembic_version is '0054'"
reset; touch "$SIMSTATE/py_fail"; line; expect_stop "the report fails" REPORT "the report did not run"
reset; line 'echo "# changed" >> "$SIM/tmp/icb-rt10-check/rt10_revisions.py"'; expect_stop "a changed kit file" KIT "do not match its SHA256SUMS"
reset; line 'rm -f "$SIM/tmp/icb-rt10-check/.staged_at"'; expect_stop "an unstamped kit" WHERE "no staging stamp"
reset; line 'echo 1 > "$SIM/tmp/icb-rt10-check/.staged_at"'; expect_stop "a kit staged before the last boot" WHERE "before this machine.s last boot"
reset; ( cd "$SIM/opt/icb-platform" && git -c user.email=sim@x -c user.name=sim commit -q --allow-empty -m other ) \
  && { line; expect_stop "prod at another commit" WHERE "code is at"; } ; git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q --detach "$(cat "$SIMSTATE/head")"

echo "== $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
