# RT9 — the v1.62.0 kit's simulation results (RT9_RETURN_1)

Both sims run the COMMITTED kit from the branch (the real `mkstage_window.sh` stages it from a sim origin carrying the
branch and an annotated `v1.62.0` tag). Nothing here reaches prod: the fake prod lives in WSL under `/root`, and the
PowerShell 5.1 sim's ssh/scp are native stand-ins that refuse any host but `stubuser@127.0.0.9` and run nothing
without their settings (both proven below). Re-run them with:

- WSL (from PowerShell): `wsl -u root -- bash /mnt/c/Users/micge/Documents/icb-platform-rt9/ops/prod-release-v1.62.0/sim/run_all.sh rt9/release-v1.62.0`
- PowerShell 5.1: `powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\micge\Documents\icb-platform-rt9\ops\prod-release-v1.62.0\sim\ps51\run_blocks.ps1`

**verify, run BEFORE the deploy, fails on exactly 11** (the happy scenario): `HEAD`, `TAG_LOCAL`, `DESCRIBE`,
`CALCJS_V`, `CALCJS_DISK`, `VERSION_LOCAL`, `CALCJS_LOCAL`, `VERSION_LAN`, `CALCJS_LAN`, `VERSION_CF`, `CALCJS_CF`
(the three `CALCJS_*` read "not probed": the new bytes are not on disk, so no door is asked for `?v=191`). Cloudflare
was asked for `calculator.js?v=191` before the deploy: 0 times.

**What the PowerShell 5.1 sim found and fixed (21 Oct):** (1) a failed helper copy (VPN down) stopped without the
"connect the VPN" hint — fixed in `window_common.ps1`; (2) `icb-deploy.sh` leaves its own `/tmp/icb-rollback-<ts>.txt`
on every deploy — the cleanup leaves it and the runbook says so; (3) the sim's first run wrote a PowerShell module
cache into the folder it was started from (Michael's clone) — removed, and the sim now runs every paste from its own
folder and checks the clone's untracked list before and after.

## Windows PowerShell 5.1 — every runbook block (sim/ps51/run_blocks.ps1, kit 17e6cd5, 21 Oct 2026 21:06)

```
== PS 5.1.26100.9444 on LAPTOP-DGJ0U6RQ; kit rt9/release-v1.62.0; work C:\Users\micge\AppData\Local\Temp\rt9ps51-20261021-210638
  ok    stage copied from the real mkstage_window.sh; the ONE host line pointed at stubuser@127.0.0.9 (nothing else changed)
  ok    ssh and scp resolve to the stubs in a fresh powershell.exe (C:\Users\micge\AppData\Local\Temp\rt9ps51-20261021-210638\stub\ssh.exe, C:\Users\micge\AppData\Local\Temp\rt9ps51-20261021-210638\stub\scp.exe)
  ok    every block's command line is plain printable ASCII with no <placeholder> (11 blocks)
  ok    the runbook has exactly the 9 window blocks (copy, preflight, all-before, deploy, all-after, doors, verify, fetch, cleanup)
  ok    :8000 health line runs in PS 5.1 and prints one JSON line ({"version":"v1.61.1","environment":"unset"})
  ok    :8000 start line names Michael's own start.bat by its full path (it exists; not run here: :8000 is Michael's)
  ok    block 'copy': exit 0, 4 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'preflight': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'all-before': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'deploy': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'all-after': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'doors': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'verify': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'fetch': exit 0, 5 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'cleanup': exit 0, 4 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    the fetched tar holds this window's out folders (6) and none of RT7's 20 Oct ones
  ok    after the cleanup block the fake prod's /tmp holds no kit name; only icb-deploy.sh's own icb-rollback-20261021-210814.txt (every deploy writes one)
  ok    RT8's fault reproduced: exit 0 and the inline double-quoted ssh argument ran nothing (ssh received: "C:\Users\micge\AppData\Local\Temp\rt9ps51-20261021-210638\stub\ssh.exe" -o BatchMode=yes stubuser@127.0.0.9 "bash -c 'set -u; echo "######## NC ran"; echo second'")
  ok    positive control: a plain argument (no inner double quotes) runs
  ok    a wrong step word: STOP [STEP], exit 1, nothing run
  ok    the VPN down: STOP [WHERE] with the VPN hint, exit 1
  ok    a tampered rt9_vm.sh: STOP [KIT] before any ssh, exit 1
  ok    the stub without RT9_STUB_REQ refuses (exit 255)
  ok    Michael's clone: the untracked list is the same before and after the run (121 entries)
== 24 passed, 0 failed (pastes and their output: C:\Users\micge\AppData\Local\Temp\rt9ps51-20261021-210638)

the remote commands the ssh stand-in received, in order:
      bash /tmp/icb-rt9-vm.sh where
      bash /tmp/icb-rt9-vm.sh unpack icb-release-v1.62.0 icb-rt2-all icb-rt2-doors
      bash /tmp/icb-rt9-vm.sh where
      sudo bash /tmp/icb-release-v1.62.0/release.sh preflight
      bash /tmp/icb-rt9-vm.sh where
      sudo bash /tmp/icb-rt2-all/rt2_all.sh pre
      bash /tmp/icb-rt9-vm.sh where
      sudo bash /tmp/icb-release-v1.62.0/release.sh deploy
      bash /tmp/icb-rt9-vm.sh where
      sudo bash /tmp/icb-rt2-all/rt2_all.sh post
      bash /tmp/icb-rt9-vm.sh where
      sudo bash /tmp/icb-rt2-doors/rt2_doors.sh
      bash /tmp/icb-rt9-vm.sh where
      sudo bash /tmp/icb-release-v1.62.0/release.sh verify
      bash /tmp/icb-rt9-vm.sh where
      bash /tmp/icb-rt9-vm.sh fetch rt9-window-back-20261021-210905
      bash /tmp/icb-rt9-vm.sh rmfetch rt9-window-back-20261021-210905
      bash /tmp/icb-rt9-vm.sh where
      sudo bash /tmp/icb-rt9-vm.sh cleanup
      bash /tmp/icb-rt9-vm.sh readback
```

## WSL — the release kit, 18 scenarios (sim/run_all.sh, kit 106673f = 17e6cd5 but for run_blocks.ps1, 21 Oct 2026 21:05)

```
PASS  happy
PASS  moved
PASS  wrongplace
PASS  wrongdb
PASS  staleboot
PASS  unstamped
PASS  nobackup
PASS  pgdumpfail
PASS  traceback
PASS  routeopen
PASS  cfstale
PASS  cfcached
PASS  resume
PASS  saved
PASS  factor
PASS  autologin
PASS  noenv
PASS  notag
== 18 passed, 0 failed
```
