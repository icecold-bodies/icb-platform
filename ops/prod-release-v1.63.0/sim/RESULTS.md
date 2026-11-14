# RT12 — the v1.63.0 kit's simulation results (RT12_RETURN_1b)

Both sims run the COMMITTED kit from the branch (the real `mkstage_window.sh` stages it from a sim origin carrying the
branch and an annotated `v1.63.0` tag). Nothing here reaches prod: the fake prod lives in WSL under `/root` (a sticky
`/tmp` under `fs.protected_regular=2`, the kit owned by the ssh user, uid 1500, as on prod), and the PowerShell 5.1
sim's ssh/scp are native stand-ins that refuse any host but `stubuser@127.0.0.9` and run nothing without their settings
(both proven below). Michael's `:8000` is his: block B is proven against a stand-in that serves his clone's files
(`ps51/fake8000.py`, 127.0.0.1:8013) in both states, and pasted verbatim against the real one only when it answers.
Re-run them with:

- WSL (from PowerShell): `wsl -u root -- bash /mnt/c/Users/micge/Documents/icb-platform-rt12/ops/prod-release-v1.63.0/sim/run_all.sh rt12/release-v1.63.0`
- PowerShell 5.1: `powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\micge\Documents\icb-platform-rt12\ops\prod-release-v1.63.0\sim\ps51\run_blocks.ps1`

**verify, run BEFORE the deploy, fails on exactly 21** (the happy scenario): `HEAD`, `TAG_LOCAL`, `DESCRIBE`,
`LETTERHEAD_GATE` (v1.62.0 logs no gate line), `V_calculator.js`, `DISK_calculator.js`, `V_calculator2.js`,
`DISK_calculator2.js`, `SPA_MARK_DISK`, and per door `VERSION_x`, `calculator.js_x`, `calculator2.js_x` ("not probed":
the new bytes are not on disk, so no door is asked for `?v=192` or `?v=129`) and `SPA_MARK_x` (the served SPA has no
RT10 text yet). Cloudflare was asked for a new `?v=` before the deploy: 0 times. The deploy tool's "dependency manifests
changed (1)" warning appeared exactly once in the dry run and once in the deploy; pip was mentioned nowhere; the venv
read weasyprint absent before and after; the gate logged False at the restart.

**What the sims found and fixed:** (1) the happy scenario's first run (24 Oct, kit 4af14a2) STOPped the deploy at the
served-bytes baseline: `each_static` set `local IFS='|'`, bash scopes are dynamic, so the functions it called lost their
word splitting (`LOCAL LAN CF: invalid variable name`) — fixed (no IFS change at all); (2) the PowerShell 5.1 sim's
refused-login control showed that PS 5.1 wraps a native command's stderr in an error record ("scp.exe : <reason>",
"At …", "+ …"): `window_common.ps1` now keeps the reason only, so the STOP line reads what ssh said; (3) the sims' own
"Permission denied" count matched #231's commit subject (which quotes the words) as the deploy tool printed it: the
count is anchored to an error line. RT12_RULING_1 (#232 in the range) added the dependency-warning, venv, gate and
disk-space checks and the two `weasyprint` scenarios; their first batch run failed only on the pattern's line order
(the kit's venv check precedes its quotes check), re-run green below.

## WSL — the release kit, 23 scenarios (sim/run_all.sh, kit 064771d; the `weasyprint` scenario re-run on 66d3f0f, where only the sim's expected-line order changed)

```
== kit rt12/release-v1.63.0 = 064771d (every scenario stages from this commit)
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
PASS  deleted
PASS  factor
PASS  autologin
PASS  noenv
PASS  notag
PASS  nonpm
PASS  nobuild
FAIL  weasyprint
PASS  weasyprintpre
== 22 passed, 1 failed
```

```
== kit rt12/release-v1.63.0 = 66d3f0f (every scenario stages from this commit)
PASS  weasyprint
== 1 passed, 0 failed
```

The happy scenario's telling lines (preflight, verify before, deploy, verify after, the second deploy; the sim's own tallies):

```
== the sim origin, the stage (the real mkstage_window.sh), the fake prod at v1.62.0
== prod: db=icb_platform alembic=0053 code=a29db35 mode=preflight target=064771d (v1.63.0) 2026-11-13T17:07:37-06:00
== anchors
== autologin: MES_DEMO_AUTOLOGIN_USER must be EMPTY on prod (only 'empty: yes/no' is ever printed)
== the 4G factor (RT7_RULING_1A: exactly 5400/4100, set by Michael on 19 Oct; v1.63.0 does not touch it)
== served bytes today: calculator.js ?v=191 and calculator2.js ?v=128 (the pages on disk) = disk = v1.62.0's blobs, on the three doors in order; the SPA served = disk, without RT10's text yet
   PASS calculator.js_CF = fb14d2aa92a5b2a5d5388e65c52c366f3e8e48285eff2ee004b0b57ae9ae8453
   PASS calculator2.js_CF = a54320915bbe749a1c73f30f6abda8d42fcc536365fcdf227f90ba9e99ea269b
== today, on the three doors in order: v1.62.0 answers, and RT4's no-session gate holds (no route is new in this release: no 404 is allowed)
   PASS NOAUTH_CF = all 47 as expected
== tracebacks (read only: the old code runs, nothing is counted)
   pre-existing  Nov 13 17:07:35  starlette.requests.ClientDisconnect
== PyYAML (installed by v1.59.0; this release installs nothing)
== weasyprint is NOT in prod's venv today (this release adds only the pin to backend/requirements.txt; RT11's install kit adds the package later)
   PASS WEASYPRINT_IN_VENV = absent
== the SPA build tooling (icb-deploy.sh runs npm run build as icb)
== the tag is on origin BEFORE the window
== backup location
== deploy tooling on prod
== prod: db=icb_platform alembic=0053 code=a29db35 mode=verify target=064771d (v1.63.0) 2026-11-13T17:07:42-06:00
== code + tag; the schema and the data do not move (no migration; the 4G factor is data)
== the deployed audit: the prod list loads strictly (every entry pinned) and is paired with the deployed snapshot
== the environment key and autologin
== service (the Python is new only if the service started after the code moved)
== tracebacks: counted from this deploy's restart only
   pre-existing  Nov 13 17:07:35  starlette.requests.ClientDisconnect
== RT11's code is inert: weasyprint is NOT in the venv (this release installs nothing), and the service logged the gate False at its start
   PASS WEASYPRINT_IN_VENV = absent
   FAIL LETTERHEAD_GATE = '' (want False)
== the two statics on disk: each page loads its new ?v= (192 / 129) and the file is the target's blob (before any door is asked for it)
== the SPA on disk: rebuilt by this deploy (a new bundle), carrying RT10's text
== door LOCAL (https://127.0.0.1): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
== door LAN (https://192.168.0.251): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
== door CF (https://mes.icecoldgrp.online): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
   PASS NOAUTH_CF = all 47 as expected
== no quote saved since the deploy (the saved costings: count + md5 of the whole rows; a difference is named row by row: id, quote, created, version, status, deleted)
######## VERIFY: 21 check(s) failed — tell the CA: /tmp/icb-release-v1.63.0/out-verify-20261113-170742
== Cloudflare asked for calculator.js?v=192 or calculator2.js?v=129 before the deploy (want 0): 0
== prod: db=icb_platform alembic=0053 code=a29db35 mode=deploy target=064771d (v1.63.0) 2026-11-13T17:07:46-06:00
== 1. anchors
== 2. autologin, the environment key, the 4G factor, the saved costings (before anything moves)
   ok   saved costings: 72 0f1e2d3c4b5a69788796a5b4c3d2e1f0; 72 rows recorded by id and md5 (verify after the acceptance must read the same, and names any row that moved)
== 3. served-bytes baseline (the doors in order; the old ?v= only — a new one is never asked for before it is on disk)
   ok   SPA assets/index-BBI2d9Oo.js ed0fadaa0af611d3 = disk on the three doors, without RT10's text (the deploy rebuilds it)
== 4. PyYAML 6.0.2 present (nothing is installed by this release); weasyprint absent; npm and node_modules for the SPA rebuild
   ok   weasyprint absent from the venv (backend/requirements.txt gains the pin 'weasyprint==70.0'; pip is never run here)
== 5. backup — checked (ops/lib/icb_backup.sh, pg_dump -Fc: size and sha256 printed); no migration, the backup comes first
== 6. fetch (with tags) + tag and range guards
   ok   228 files (C-sorted sha256 abd455def7ef0cfc): no migration, one manifest (backend/requirements.txt +weasyprint==70.0, nothing installed), 18 frontend file(s) (the SPA rebuild), static = the two calculators + #232's WeasyPrint-only files, deploy/ untouched
== 7. the repo's deploy script — dry run
   ok   plan: no migration, SPA rebuild, restart; the one expected warning: dependency manifests changed (1) = backend/requirements.txt (the weasyprint pin; nothing is installed)
== 8. deploy (fast-forward, its own backup, npm run build, restart, health, completion record)
   ok   SPA bundle assets/index-BBI2d9Oo.js -> assets/index-RT121794611268.js
== 9. post-deploy asserts: the disk first, then the three doors in order (waiting 20 s for all workers to log startup)
== code + tag; the schema and the data do not move (no migration; the 4G factor is data)
== the deployed audit: the prod list loads strictly (every entry pinned) and is paired with the deployed snapshot
== the environment key and autologin
== service (the Python is new only if the service started after the code moved)
== tracebacks: counted from this deploy's restart only
   pre-existing  Nov 10 17:07:32  anyio.WouldBlock
   pre-existing  Nov 10 17:07:32  anyio.EndOfStream
   pre-existing  Nov 10 17:07:32  starlette.requests.ClientDisconnect
   pre-existing  Nov 13 17:07:35  starlette.requests.ClientDisconnect
   pre-existing tracebacks in the 14 days before this deploy's restart (listed, not counted): 4
== RT11's code is inert: weasyprint is NOT in the venv (this release installs nothing), and the service logged the gate False at its start
   PASS WEASYPRINT_IN_VENV = absent
   PASS LETTERHEAD_GATE = False
== the two statics on disk: each page loads its new ?v= (192 / 129) and the file is the target's blob (before any door is asked for it)
== the SPA on disk: rebuilt by this deploy (a new bundle, not assets/index-BBI2d9Oo.js ed0fadaa0af611d32f5e45b1674b8e3c947536f9895f13dd28c833be41589cb1), carrying RT10's text
   PASS SPA_REBUILT = yes
   PASS SPA_MARK_DISK = 1
== door LOCAL (https://127.0.0.1): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
== door LAN (https://192.168.0.251): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
== door CF (https://mes.icecoldgrp.online): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
   PASS calculator.js_CF = 9d2eb371677c7764288aa3177e4b1b98f42b6c29d74207baa84f17f475917a0c
   PASS calculator2.js_CF = bb218b79d7e194803c198d9a176700449cc62d3cc71950a3aabc460612284720
   PASS NOAUTH_CF = all 47 as expected
== no quote saved since the deploy (the saved costings: count + md5 of the whole rows; a difference is named row by row: id, quote, created, version, status, deleted)
######## DEPLOYED — tell the CA: /tmp/icb-release-v1.63.0/out-deploy-20261113-170746  (next: All after, on the page and the CLI)
== prod: db=icb_platform alembic=0053 code=064771d mode=verify target=064771d (v1.63.0) 2026-11-13T17:08:23-06:00
== code + tag; the schema and the data do not move (no migration; the 4G factor is data)
== the deployed audit: the prod list loads strictly (every entry pinned) and is paired with the deployed snapshot
== the environment key and autologin
== service (the Python is new only if the service started after the code moved)
== tracebacks: counted from this deploy's restart only
   pre-existing  Nov 10 17:07:32  anyio.WouldBlock
   pre-existing  Nov 10 17:07:32  anyio.EndOfStream
   pre-existing  Nov 10 17:07:32  starlette.requests.ClientDisconnect
   pre-existing  Nov 13 17:07:35  starlette.requests.ClientDisconnect
   pre-existing tracebacks in the 14 days before this deploy's restart (listed, not counted): 4
== RT11's code is inert: weasyprint is NOT in the venv (this release installs nothing), and the service logged the gate False at its start
   PASS WEASYPRINT_IN_VENV = absent
   PASS LETTERHEAD_GATE = False
== the two statics on disk: each page loads its new ?v= (192 / 129) and the file is the target's blob (before any door is asked for it)
== the SPA on disk: rebuilt by this deploy (a new bundle), carrying RT10's text
   PASS SPA_MARK_DISK = 1
== door LOCAL (https://127.0.0.1): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
== door LAN (https://192.168.0.251): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
== door CF (https://mes.icecoldgrp.online): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
   PASS calculator.js_CF = 9d2eb371677c7764288aa3177e4b1b98f42b6c29d74207baa84f17f475917a0c
   PASS calculator2.js_CF = bb218b79d7e194803c198d9a176700449cc62d3cc71950a3aabc460612284720
   PASS NOAUTH_CF = all 47 as expected
== no quote saved since the deploy (the saved costings: count + md5 of the whole rows; a difference is named row by row: id, quote, created, version, status, deleted)
   PASS QUOTES_UNCHANGED_SINCE_DEPLOY = 72 0f1e2d3c4b5a69788796a5b4c3d2e1f0
######## VERIFY: 0 check(s) failed — tell the CA: /tmp/icb-release-v1.63.0/out-verify-20261113-170823
== prod: db=icb_platform alembic=0053 code=064771d mode=deploy target=064771d (v1.63.0) 2026-11-13T17:08:28-06:00
== 1. anchors
== code + tag; the schema and the data do not move (no migration; the 4G factor is data)
== the deployed audit: the prod list loads strictly (every entry pinned) and is paired with the deployed snapshot
== the environment key and autologin
== service (the Python is new only if the service started after the code moved)
== tracebacks: counted from this deploy's restart only
   pre-existing  Nov 10 17:07:32  anyio.WouldBlock
   pre-existing  Nov 10 17:07:32  anyio.EndOfStream
   pre-existing  Nov 10 17:07:32  starlette.requests.ClientDisconnect
   pre-existing  Nov 13 17:07:35  starlette.requests.ClientDisconnect
   pre-existing tracebacks in the 14 days before this deploy's restart (listed, not counted): 4
== RT11's code is inert: weasyprint is NOT in the venv (this release installs nothing), and the service logged the gate False at its start
   PASS WEASYPRINT_IN_VENV = absent
   PASS LETTERHEAD_GATE = False
== the two statics on disk: each page loads its new ?v= (192 / 129) and the file is the target's blob (before any door is asked for it)
== the SPA on disk: rebuilt by this deploy (a new bundle), carrying RT10's text
   PASS SPA_MARK_DISK = 1
== door LOCAL (https://127.0.0.1): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
== door LAN (https://192.168.0.251): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
== door CF (https://mes.icecoldgrp.online): /health/version, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 = the target, the SPA bundle served = the one built, the 47 no-session probes
   PASS calculator.js_CF = 9d2eb371677c7764288aa3177e4b1b98f42b6c29d74207baa84f17f475917a0c
   PASS calculator2.js_CF = bb218b79d7e194803c198d9a176700449cc62d3cc71950a3aabc460612284720
   PASS NOAUTH_CF = all 47 as expected
== no quote saved since the deploy (the saved costings: count + md5 of the whole rows; a difference is named row by row: id, quote, created, version, status, deleted)
######## ALREADY DEPLOYED, all asserts PASS — tell the CA: /tmp/icb-release-v1.63.0/out-deploy-20261113-170828
== sim state: prod HEAD 064771d, describe v1.63.0, alembic 0053, record 'completed 064771d217bf65e6e1103035ff708969b90aa84c', spa index-RT121794611268
== backups: icb_platform_20261023-0230.dump.gz icb_platform_pre-v1.63.0_20261113-170746.dump   (the kit's pg_dump ran at alembic 0053); npm builds: 1
== the doors, in the order the kit asked (first request per door for /health/version): 127.0.0.1 192.168.0.251 mes.icecoldgrp.online 
== root-owned __pycache__ the kit left in the repo (want 0): 0
== 'Permission denied' anywhere in the kit's out folders (sticky /tmp, protected_regular=2; want 0): 0
== files the kit wrote directly in /tmp (want none): 
== 'exception line not found' in the kit's out folders (want 0): 0
== pip mentioned anywhere in the kit's out folders (want 0): 0
== 'dependency manifests changed (1)' in the deploy's captured outputs (want 2: the dry run and the deploy): 2
```

## Windows PowerShell 5.1 — every runbook block (sim/ps51/run_blocks.ps1, kit 064771d)

```
== the runbook has 11 paste blocks
  ok    every block's command line is plain printable ASCII with no <placeholder> (11 blocks)
  ok    the runbook has exactly the 9 staged-line blocks (copy, preflight, all-before, deploy, all-after, doors, verify, fetch, cleanup)
  ok    block B (stand-in says v1.62.0 (before the merge)): 4 byte checks 'same: yes' (calculator.js, calculator2.js, SPA bundle, SPA text); exit 1; it ended '######## STOP [VERSION]: :8000 says {"version":"v1.62.0","environment":"unset"}, not v1.63.0 - the python that runs started before the clone moved: close the start.bat window, start it again, then paste this line again'
  ok    block B (stand-in says v1.63.0 (after the merge)): 4 byte checks 'same: yes' (calculator.js, calculator2.js, SPA bundle, SPA text); exit 0; it ended '######## DONE - :8000 serves v1.63.0 (calculator.js and calculator2.js = the clone, SPA index-I5Myzg-I.js = the clone, with RT10's text). Copy the whole window and paste it back to the CA.'
  info  Michael's real :8000 does not answer now; block B was proven against the stand-in only
  ok    :8000 start line names Michael's own start.bat by its full path (it exists; not run here: :8000 is Michael's)
== the window, in order (the page's All and the view-only acceptance are browser steps: nothing to paste), then the close
  ok    block 'copy': exit 0, 4 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'preflight': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'all-before': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'deploy': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'all-after': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'doors': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'verify': exit 0, 3 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'fetch': exit 0, 5 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    block 'cleanup': exit 0, 4 ssh/scp call(s); first line = the runbook; end = the runbook
  ok    the deploy block: SPA rebuilt to a new bundle, 72 rows recorded by id, no 'Permission denied' (sticky /tmp, kit owned by uid 1500)
  ok    the window's tar holds exactly its 6 out folders
== the fake prod's /tmp after the cleanup block, and negative controls
  ok    after the cleanup block the fake prod's /tmp holds no kit name; only icb-deploy.sh's own anchors (icb-rollback-20261022-123540.txt 0, icb-rollback-20261113-170824.txt 0)
  ok    no 'Permission denied' in any kit's out folder on the sticky fake /tmp (fs.protected_regular as prod)
  ok    RT8's fault reproduced: exit 0 and the inline double-quoted ssh argument ran nothing (ssh received: "C:\Users\micge\AppData\Local\Temp\rt12ps51-20261113-170515\stub\ssh.exe" -o BatchMode=yes stubuser@127.0.0.9 "bash -c 'set -u; echo "######## NC ran"; echo second'")
  ok    positive control: a plain argument (no inner double quotes) runs
  ok    a wrong step word: STOP [STEP], exit 1, nothing run
  ok    the VPN down: STOP [WHERE] with the VPN hint, exit 1
  ok    a refused login: STOP [WHERE] carries ssh's own words ('Connection closed by ...') and the retry hint
  ok    C: under 5 GB free: STOP [DISK] with the plain message, exit 1, no ssh/scp call
  ok    a tampered rt12_vm.sh: STOP [KIT] before any ssh, exit 1
  ok    the stub without RT12_STUB_REQ refuses (exit 255)
  ok    Michael's clone: the untracked list is the same before and after the run (121 entries)
   == fake prod /tmp at the end (name owner):
      icb-rollback-20261022-123540.txt 0
      icb-rollback-20261113-170824.txt 0
   == fake prod HEAD 064771d, describe v1.63.0, spa index-RT121794611304
   == 'Permission denied' in the kits' out folders (want 0): 0
   == the remote commands the stubs ran:
      bash /tmp/icb-rt12-vm.sh where
      bash /tmp/icb-rt12-vm.sh unpack icb-release-v1.63.0 icb-rt2-all icb-rt2-doors
      bash /tmp/icb-rt12-vm.sh where
      sudo bash /tmp/icb-release-v1.63.0/release.sh preflight
      bash /tmp/icb-rt12-vm.sh where
      sudo bash /tmp/icb-rt2-all/rt2_all.sh pre
      bash /tmp/icb-rt12-vm.sh where
      sudo bash /tmp/icb-release-v1.63.0/release.sh deploy
      bash /tmp/icb-rt12-vm.sh where
      sudo bash /tmp/icb-rt2-all/rt2_all.sh post
      bash /tmp/icb-rt12-vm.sh where
      sudo bash /tmp/icb-rt2-doors/rt2_doors.sh
      bash /tmp/icb-rt12-vm.sh where
      sudo bash /tmp/icb-release-v1.63.0/release.sh verify
      bash /tmp/icb-rt12-vm.sh where
      bash /tmp/icb-rt12-vm.sh fetch rt12-window-back-20261113-170924
      bash /tmp/icb-rt12-vm.sh rmfetch rt12-window-back-20261113-170924
      bash /tmp/icb-rt12-vm.sh where
      sudo bash /tmp/icb-rt12-vm.sh cleanup
      bash /tmp/icb-rt12-vm.sh readback
   == removed /root/rt12ps51-1794611122 and the cache
== 29 passed, 0 failed (pastes and their output: C:\Users\micge\AppData\Local\Temp\rt12ps51-20261113-170515)
```
