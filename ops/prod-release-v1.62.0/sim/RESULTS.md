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

## The close (RT9_RULING_2 Q1) — Windows PowerShell 5.1, every block of the runbook including the close's three (kit 8a38d3a, 22 Oct 2026 14:18)

The close is staged AFTER the fake deploy (its expected.env pins the fake's own backup by path, size and sha256); 3 costings are then saved on the fake prod, and the quotes check must name exactly those. The fake's repair row carries a made-up customer name in its quote number, and every row a customer_name inside result_json: neither reaches the output.

```
== PS 5.1.26100.9444 on LAPTOP-DGJ0U6RQ; kit rt9/close; work C:\Users\micge\AppData\Local\Temp\rt9ps51-20261022-141833
  ok    stage copied from the real mkstage_window.sh; the ONE host line pointed at stubuser@127.0.0.9 (nothing else changed)
  ok    ssh and scp resolve to the stubs in a fresh powershell.exe (C:\Users\micge\AppData\Local\Temp\rt9ps51-20261022-141833\stub\ssh.exe, C:\Users\micge\AppData\Local\Temp\rt9ps51-20261022-141833\stub\scp.exe)
  ok    every block's command line is plain printable ASCII with no <placeholder> (13 blocks)
  ok    the runbook has exactly the 11 staged-line blocks (window/copy, window/preflight, window/all-before, window/deploy, window/all-after, window/doors, window/verify, window/fetch, close/quotes, close/fetch, close/cleanup)
  ok    :8000 health line runs in PS 5.1 and prints one JSON line ({"version":"v1.62.0","environment":"unset"})
  ok    :8000 start line names Michael's own start.bat by its full path (it exists; not run here: :8000 is Michael's)
  ok    block 'window/copy': exit 0, 4 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'window/preflight': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'window/all-before': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'window/deploy': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'window/all-after': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'window/doors': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'window/verify': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'window/fetch': exit 0, 5 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'close/quotes': exit 0, 5 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'close/fetch': exit 0, 5 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'close/cleanup': exit 0, 4 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    the window's tar holds its out folders (6) and none of RT7's 20 Oct ones
  ok    the close's tar holds the quotes check's out folder with the window's (7)
  ok    after the cleanup block the fake prod's /tmp holds no kit name; only icb-deploy.sh's own icb-rollback-20261022-142006.txt (every deploy writes one)
  ok    RT8's fault reproduced: exit 0 and the inline double-quoted ssh argument ran nothing (ssh received: "C:\Users\micge\AppData\Local\Temp\rt9ps51-20261022-141833\stub\ssh.exe" -o BatchMode=yes stubuser@127.0.0.9 "bash -c 'set -u; echo "######## NC ran"; echo second'")
  ok    positive control: a plain argument (no inner double quotes) runs
  ok    a wrong step word: STOP [STEP], exit 1, nothing run
  ok    the VPN down: STOP [WHERE] with the VPN hint, exit 1
  ok    a tampered rt9_vm.sh: STOP [KIT] before any ssh, exit 1
  ok    the stub without RT9_STUB_REQ refuses (exit 255)
  ok    Michael's clone: the untracked list is the same before and after the run (121 entries)
== 27 passed, 0 failed (pastes and their output: C:\Users\micge\AppData\Local\Temp\rt9ps51-20261022-141833)
```

The quotes block's output on the fake (the stand-in's 72-row backup; 3 N10022 revisions saved after the deploy):

```
== 1. the deploy's checked backup (2026-10-22 12:35:35 SAST): size and sha256 read back
   ok   /var/backups/postgres/icb_platform_pre-v1.62.0_20261022-142006.dump  4102 bytes  sha256 8a83268caca78de9... = the deploy's
== 2. the saved costings' count + md5 (every whole row): now, beside the deploy's
   at the deploy  72 0f1e2d3c4b5a69788796a5b4c3d2e1f0
   now            75 9cc317a694c80eb95b824d05b45c3f7b
   (created times below are as stored; the database's TimeZone setting is Africa/Johannesburg)
== 3. the backup streamed (pg_restore --data-only, never restored) against the live rows (a read-only COPY), row by row
   == the backup: 72 rows (max id 1172); now: 75 rows (max id 1240)
   == added since the backup: 3
      id | quote | created (as stored) | version | status | deleted | selling (result_json) | net total
      1238 | N10022/10/2026 | 2026-10-22 13:02:10 | 4 | pending | N | 389120.00 | 389120.00
      1239 | N10022/10/2026 | 2026-10-22 13:03:10 | 5 | pending | N | 389120.00 | 389120.00
      1240 | N10022/10/2026 | 2026-10-22 13:04:10 | 6 | pending | N | 389120.00 | 389120.00
   == changed since the backup: 0  (id | quote | the changed columns' names; never their values)
   == removed since the backup: 0
   == rows created on 2026-10-22 (as stored, 2 h of leeway for the zone), newest first: 3
      id | quote | created (as stored) | version | status | deleted | selling (result_json) | net total
      1240 | N10022/10/2026 | 2026-10-22 13:04:10 | 6 | pending | N | 389120.00 | 389120.00   <- added since the backup
      1239 | N10022/10/2026 | 2026-10-22 13:03:10 | 5 | pending | N | 389120.00 | 389120.00   <- added since the backup
      1238 | N10022/10/2026 | 2026-10-22 13:02:10 | 4 | pending | N | 389120.00 | 389120.00   <- added since the backup
   SUMMARY: backup 72 rows; now 75 rows; added 3, changed 0, removed 0; created today 3

######## DONE (read only): the backup compared row by row: now 75 rows; added 3, changed 0, removed 0; created today 3 �?" tell the CA: /tmp/icb-rt9-quotes/out-20261022-142104
```
