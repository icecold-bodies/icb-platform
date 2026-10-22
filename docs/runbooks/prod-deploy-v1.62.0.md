# Prod deploy: v1.62.0 (RT9): a re-opened quote is the saved quote (RT8)

Committed BEFORE the run (D3). The OUTCOME is appended after the window. Dispatch `RT9_DISPATCH_release_v1.62.0`
(21 Oct 2026); rulings `RT9_RULING_<n>`. Built by RT8 (#221 `90d6ce9`, #224, #225, #226; base tip `bb5d44e`);
released by RT9, a fresh release CA (D1).

## What ships (prod `5511355` = v1.61.1 → the v1.62.0 squash commit)

- **The app code (RT8):** `routers/calculator.py`; `services/frozen_quote.py` (new), `free_hand.py`, `rule_guard.py`;
  `static/js/calculator.js` and `templates/calculator.html` — **`calculator.js?v=189 → ?v=191`** (the template and
  the file, both served from disk).
- **One new route:** `POST /api/calculations/{record_id}/reprice-preview` (View changes / Update to today's prices;
  writes nothing). Like every route it needs a session: **401 without one**, on the three doors. On v1.61.1 it does
  not exist (404): the kit accepts 404 for exactly this one probe, and only before the deploy.
- **No migration** (alembic stays **0053**), **no dependency**, **no SPA (`frontend/`) change** — no rebuild. Python
  changes, so the service **restarts** (a few seconds without the app).
- **Also in the range** (not app code): RT7's #222 (`tools/costing_audit/mes_snapshot.py`: CI's snapshot loader
  allows exactly body 51's seven dangling FKs — prod never loads a snapshot) and #223 (RT7's OUTCOME), RT8's tests,
  journeys, discovery evidence and prod-check kit, and this release PR: `backend/VERSION` → `v1.62.0`, the CHANGELOG
  entry, this runbook, `ops/prod-release-v1.62.0/`.
- **`/openapi.json` does not change.** It has been **admin-only since v1.60.1** (RT4, `01751fa`, on prod since
  5 Oct): no session → **401** (a probe line since v1.60.1; 46 / 46 on the three doors on 20 Oct), a signed-in
  non-admin → 403, an admin → 200. Before and after this deploy: `401 /openapi.json` on the three doors. (RT8's
  return said prod's was world-readable and "gets it with v1.62.0": that note predates RT4.)

## Behaviour a user can notice (for the BA's note to the sales team, after the window)

- Re-opening a saved quote shows it **exactly as saved** (lines, prices, totals from its own saved copy). A quiet line
  under the edit banner says how today's prices differ; **View changes** lists the differences; **Update to today's
  prices** re-prices it, and a re-priced quote saves only as a **new revision**. Options and chassis are locked at
  saved prices. Repairs follow the same rule.
- **A browser tab opened before the update** holds `calculator.js?v=190` or older. An Overwrite from it is refused in
  plain words: "This page is out of date. Reload it (Ctrl+F5) and save again. Your quote has not been changed."
  Everyone reloads after the update (the BA tells the sales team).
- How a NEW costing prices does not change: the costing audit reads the same before and after.

## Expected numbers

- **All BEFORE and All AFTER: the same** — v1.62.0 changes how saved quotes re-open, not how costings price; the
  accepted list, the CI snapshot and the golden do not move in the range (mkstage.sh refuses otherwise). Both read
  RT7's after-state of 20 Oct, cell for cell (2 936 / 2 936), and PAGE = CLI:

| pack | FLAG | ACCEPTED | PASS | SKIP | UNVERIFIABLE |
|---|---|---|---|---|---|
| chillers | 0 | 0 | 590 | 126 | — |
| freezers | 0 | 72 | 501 | 117 | — |
| icecream | 0 | 40 | 416 | 116 | 40 |
| explosive | 0 | 3 | 528 | 117 | 36 |
| **All (2 702)** | **0** | **115** | 2 035 | 476 | 76 |
| smoke (234) | 0 | 33 | 156 | 45 | — |

  If prod's prices moved since 20 Oct, All BEFORE shows it and the window STOPs there: nothing has changed yet.
- **The no-session probes: 47 per door** (RT7's 46 + the new route). Before the deploy the new route answers 404
  (allowed, named in the line); after it, 401.
- **Tracebacks are counted from this deploy's own restart** (RT7's lesson, ratified default 2). Earlier ones are
  listed with their time and exception class only (never the message: G4) and never counted.
- **verify, if run before the deploy, fails on exactly 11** (the simulation's list; the window does not run it):
  `HEAD`, `TAG_LOCAL`, `DESCRIBE`, `CALCJS_V`, `CALCJS_DISK`, and per door `VERSION_LOCAL / _LAN / _CF` and
  `CALCJS_LOCAL / _LAN / _CF` ("not probed": the new bytes are not on disk, so no door is asked for `?v=191`).
- **The saved costings do not move during the window:** the deploy records their count + md5 (whole rows; nothing
  else is printed) and step 8 must read the same after Michael's N10022 check.

## The kits (committed, staged byte-exact from the merge commit by ONE script)

`bash ops/prod-release-v1.62.0/mkstage_window.sh C:/Users/micge/Documents/icb-rt9-stage/window <merge-sha>` (the CA,
after the tag is on origin) stages three kits, each with `lib/`, the place it must run (`icb-mes-prod`,
`icb_platform @ 127.0.0.1:5432`, the HEADs it may see) and the reboot guard:

| kit | runs | over |
|---|---|---|
| `icb-release-v1.62.0` | `release.sh preflight / deploy / verify` | v1.61.1 (and v1.62.0 after the deploy) |
| `icb-rt2-all` | `rt2_all.sh pre / post` (its first line still says RT7: the shared kit is unchanged) | either |
| `icb-rt2-doors` | `rt2_doors.sh` | either |

Beside the tars, **Michael's lines** (ASCII, filled in by the stager, each run by its full path from PowerShell):
`run_window_copy.ps1` (step 1), `run_window_step.ps1` (steps 2–6 and 8: ssh to the VM, then the staged kit BY PATH
under sudo), `run_window_fetch.ps1` (step 9) and `run_window_cleanup.ps1` (the close), with `window_common.ps1` and
`rt9_vm.sh` — the VM side, which every line copies to prod as `/tmp/icb-rt9-vm.sh` and runs by path. No line ever
hands a script to ssh as an argument (RT8's PowerShell 5.1 quoting fault, 21 Oct). Each line's FIRST output line names
this laptop, prod's machine, prod's HEAD and boot time, and it refuses a wrong place before anything runs.

**Note on prod `/tmp`:** RT7 left its three window kits there on 20 Oct. RT9 reuses the All and door kit folders by
name (`/tmp/icb-rt2-all`, `/tmp/icb-rt2-doors`): the copy unpacks over them and re-stamps them, and the fetch takes
only the `out-*` folders written since this window's copy (`/tmp/icb-rt9-window.started`). RT7's old out folders stay
inside until the close.

## How Michael runs each step

One step, one block. Paste the line into the window named, exactly as written. Wait for the `########` line at the
end, then copy the whole window and paste it back to the CA; run the next step only when the CA says "next".

### Before the window (after the merge, the tag and the CA's fast-forward of your clone)

**A. Restart :8000.** Close the window where :8000 runs now (or press Ctrl+C in it and close it). Then:

📋 PASTE INTO: Command Prompt (a new window; leave it open afterwards, it is :8000)
```
"C:\Users\micge\Documents\icb-platform\scripts\start.bat"
```
FIRST LINE YOU SHOULD SEE: [start] Applying migrations (alembic upgrade head)...
IT WILL ASK FOR: nothing
WHEN IT ENDS: it does not end: it keeps running once it shows "Application startup complete." → leave it open and go to B
IF YOU SEE "STOP": there is no STOP line here; if you see "Traceback" or "ERROR", paste the window back to me

**B. Check :8000's version.**

📋 PASTE INTO: PowerShell (your laptop)
```
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health/version).Content
```
FIRST LINE YOU SHOULD SEE: {"version":"v1.62.0","environment":"unset"}
IT WILL ASK FOR: nothing
WHEN IT ENDS: that one line is all → paste it back to me
IF YOU SEE "STOP": there is no STOP line here; if it says v1.61.1, the old :8000 is still running: close its window and do A again

### The window (Michael's time, outside Nadie's and Lezette's quoting hours; no quote is saved during it)

**1. Copy the kits to prod** (the VPN must be up).

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_copy.ps1"
```
FIRST LINE YOU SHOULD SEE: ######## RT9 window copy (step 1) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head 5511355 . boot …
IT WILL ASK FOR: nothing (no sudo in this step)
WHEN IT ENDS: ######## DONE - step 1: the kits are in prod /tmp, verified and stamped … → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing ran on prod; paste it back to me

**2. Preflight** (read only). On prod it ends `######## PREFLIGHT PASSED`: v1.61.1 on the three doors,
`calculator.js?v=189` = disk on the three doors, 47 probes per door (the new route 404, named), the 4G factor, the tag
on origin.

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_step.ps1" preflight
```
FIRST LINE YOU SHOULD SEE: ######## RT9 window step 2 preflight (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head 5511355 . boot …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 2 (preflight) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed (read only); paste it back to me

**3. All BEFORE.** First, in the browser: open `https://192.168.0.251/admin/costing-audit` → **All** → Run, and
wait until it finishes (cells: flag 0 · accepted 115 · pass 2035 · unverifiable 76). Then:

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_step.ps1" all-before
```
FIRST LINE YOU SHOULD SEE: ######## RT9 window step 3 All before (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head 5511355 . boot …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 3 (all-before) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed (read only); paste it back to me

On prod it ends `######## DONE (pre): PAGE = CLI`. Any count that differs from the table above is a STOP: the CA
compares the cells before the deploy.

**4. Deploy** (the service restarts once: a few seconds without the app). On prod: the checked backup (size and
sha256 read back), no migration, the restart, 0 tracebacks since it, `calculator.js?v=191` on disk, then
127.0.0.1, LAN and Cloudflare each `{"version":"v1.62.0","environment":"prod"}`, no TEST banner,
`calculator.js?v=191` = the release's bytes, 47 probes (the new route 401); it ends `######## DEPLOYED`.

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_step.ps1" deploy
```
FIRST LINE YOU SHOULD SEE: ######## RT9 window step 4 deploy . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head 5511355 . boot …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 4 (deploy) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": run nothing else (not even this line again) until I answer; paste it back to me

**5. All AFTER.** First, in the browser: `https://192.168.0.251/admin/costing-audit` → **All** → Run again; wait
until it finishes (the same counts as step 3). Then:

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_step.ps1" all-after
```
FIRST LINE YOU SHOULD SEE: ######## RT9 window step 5 All after (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 5 (all-after) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed (read only); paste it back to me

On prod it ends `######## DONE (post): PAGE = CLI`; the counts must equal step 3's, cell for cell.

**6. Doors** (RT2's rear-door report, read only). On prod: `SUMMARY: 14 OK`.

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_step.ps1" doors
```
FIRST LINE YOU SHOULD SEE: ######## RT9 window step 6 doors (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 6 (doors) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed (read only); paste it back to me

**7. N10022 acceptance — in the browser, nothing to paste, NOTHING SAVED** (ratified default 7). Close every
calculator tab opened before the deploy. Then open `https://mes.icecoldgrp.online/mes-app/costings`, find
**N10022/10/2026** and open it in **Edit**. Check:
- ROOF shows **6MM PF PLYWOOD R1,801.08** and **PU R5,581.00**;
- the total is **R391,853.38**;
- the quiet line under the edit banner shows today's difference;
- the options are locked.

**Cancel edit — do not click Update or Save.**

Then click **Cancel edit**. Do **not** save, re-price or overwrite it. Tell the CA what you saw (a screenshot is fine).
(RT9_RULING_2, lesson 1: the acceptance on prod is view-only. On 22 Oct a revision was saved here instead; the close
identified and removed it.)

**8. Verify** (read only), after the N10022 check: everything as at the deploy, plus
`PASS QUOTES_UNCHANGED_SINCE_DEPLOY` (no quote was saved) and 0 tracebacks since the restart (the N10022 re-open
included). On prod it ends `######## VERIFY: 0 check(s) failed`.

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_step.ps1" verify
```
FIRST LINE YOU SHOULD SEE: ######## RT9 window step 8 verify (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 8 (verify) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed (read only); paste it back to me

**9. Fetch** the window's records to your Downloads folder (one tar).

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_fetch.ps1"
```
FIRST LINE YOU SHOULD SEE: ######## RT9 window fetch (step 9) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head …
IT WILL ASK FOR: nothing (no sudo in this step)
WHEN IT ENDS: ######## DONE - step 9: … (the tar's full path in your Downloads folder) → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed; paste it back to me

### The close (only on the CA's word, after the fetch)

The close's lines live in a second stage folder, `C:\Users\micge\Documents\icb-rt9-stage\close` (staged by
`mkstage_close.sh` from a later commit than the release: its VM helper knows one more kit). The window's folder stays
as it was.

**Q. The quotes check** (read only; `RT9_RULING_2` Q1 — step 8 read 95 saved costings against 92 at the deploy).
On prod it (1) reads the deploy's checked backup back by size and sha256; (2) prints the saved costings' count + md5
now beside the deploy's; (3) streams the backup's costings (`pg_restore --data-only`, never restored: nothing is
extracted to disk) against the live rows (a read-only COPY, the same pipe) and compares them **row by row**: added,
changed (the changed columns' **names** only, never their values), removed, and every row created today. It prints only
id, the quote number's first word (a repair's number carries the customer's name), created as stored, version, status,
soft-deleted Y/N and the totals: an allow-list in the filter refuses any other field (G4). It ends
`######## DONE (read only): the backup compared row by row: added …, changed …, removed …`; a STOP means the backup
is not the deploy's, or the comparison could not run. Run it again after Michael's deletes (Q2): the deleted rows then
read as changed (`deleted_at, deleted_by`) and soft-deleted Y, and nothing else.

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\close\run_quotes_check.ps1"
```
FIRST LINE YOU SHOULD SEE: ######## RT9 window quotes check (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head a29db35 . boot …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - the quotes check ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": it is read only: nothing was changed; paste it back to me

**9b. Fetch again** — the close's records (the quotes check's out folder, with the window's) to your Downloads folder,
in a new tar. This line lives in the close folder: its helper knows the quotes kit.

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\close\run_window_fetch.ps1"
```
FIRST LINE YOU SHOULD SEE: ######## RT9 window fetch (step 9) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head …
IT WILL ASK FOR: nothing (no sudo in this step)
WHEN IT ENDS: ######## DONE - step 9: … (the tar's full path in your Downloads folder) → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed; paste it back to me

**10. Remove the window's kits from prod `/tmp`** by exact name (the list is in `rt9_vm.sh`: the three RT9 window
kits and their tars — RT7's old out folders inside the reused All and door folders go with them — the quotes check's
kit and tar, RT7's v1.61.1 release kit and tar, and the window start mark), then read every name back. Not touched:
`/tmp/icb-rollback-<ts>.txt`, which the repo's own `icb-deploy.sh` writes on every deploy (its rollback anchor;
earlier deploys left theirs too). This line lives in the close folder too (re-staged with the longer list).

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\close\run_window_cleanup.ps1"
```
FIRST LINE YOU SHOULD SEE: ######## RT9 window close: prod /tmp cleanup . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - prod /tmp: every RT9 window name removed and read back absent … → copy the whole window and paste it back to me
IF YOU SEE "STOP": some names may already be gone; paste it back to me

## If a step STOPs

- **Steps 1–3:** nothing has changed on prod. The CA reads the STOP line and answers; the window can move.
- **Step 4 (deploy) STOPs before `8. deploy`:** nothing has moved (the backup may exist: it stays). After `8. deploy`
  started, the code may have moved: run the same step-4 line again **only on the CA's word** — it says `RESUME` and
  re-runs the deploy script's idempotent steps, then every check.
- **A STOP on a Cloudflare check after `DEPLOYED`-level checks passed on 127.0.0.1 and LAN** (`VERSION_CF`,
  `CALCJS_CF`): the edge still serves the old answer. `CALCJS_CF` would mean someone fetched `?v=191` through
  Cloudflare before the deploy: Michael purges the Cloudflare cache, then step 8 (verify) re-checks.
- **Steps 5–9:** read only; the CA decides.

## Rollback (decided before the run)

- **The code:** back to `5511355`: `sudo -u icb git -C /opt/icb-platform reset --hard 5511355`, then
  `sudo systemctl restart icb-backend`; then `/health/version` = v1.61.1 on the three doors. No migration, no SPA, no
  data moved: nothing else to undo. A browser that loaded `?v=191` gets `?v=189` again from the old template.
- **The full restore** (only if the above fails): `icb_platform_pre-v1.62.0_<ts>.dump` (pg_dump -Fc, written and
  checked by step 4).

## Simulation

| sim | how | result |
|---|---|---|
| the release kit, 20 scenarios (18, plus the close's quotes check and its negative control) | WSL: `ops/prod-release-v1.62.0/sim/run_all.sh` (the real `mkstage_window.sh` + `mkstage.sh`, the real `deploy/prod/icb-deploy.sh`, stub doors that answer for the RUNNING code, a Cloudflare edge that keeps the first bytes per URL) | see `RT9_RETURN_1` |
| every paste block above | Windows PowerShell 5.1: `ops/prod-release-v1.62.0/sim/ps51/run_blocks.ps1` — reads THIS runbook's blocks and pastes each into a new PowerShell 5.1 window against a fake prod in WSL (native ssh/scp stand-ins, so the quoting is PowerShell 5.1's own) | see `RT9_RETURN_1` |

## OUTCOME

**22 Oct 2026, 12:22–13:23 SAST: prod = v1.62.0 `a29db35`, alembic 0053. Every release check passed on the three
doors in order; the costing audit identical before and after, 2 936 / 2 936, PAGE = CLI. The window STOPped at
step 8 on `QUOTES_UNCHANGED_SINCE_DEPLOY` (92 → 95): costings were saved during it — the check doing its job, not a
release fault (RT9_RULING_2). The close identified and removed the test saves (below).** Evidence:
`docs/audit/rt9_2026-10/prod/window_20261022/` (the kits' out folders, without the HTML reports); the window tar is
`Downloads\rt9-window-back-20261022-132322.tar`, sha256 `bf722a68…`, 24 924 160 B.

**Before the window:**
- **Merge:** #227 squash `a29db35` (10:03 UTC), parent `bb5d44e`, tree = the tested `a8a7778`, 7 / 7 green on it
  (the ubuntu build & test on its re-run: one journey flake, `test_preview_formats_journey::test_banner_length_live`,
  queued).
- **Tag:** `v1.62.0` = tag object `61edbaa`, local = origin, peeling to `a29db35`.
- **:8000:** Michael's clone fast-forwarded `bb5d44e → a29db35` at 12:09 once the old :8000 had stopped (it ran in an
  Explorer-launched `MES start.bat` window; the first window closed was another). 235 local entries byte-identical
  before and after (`d64dc329`). His restart at 12:11: `{"version":"v1.62.0","environment":"unset"}`, the new route
  401 with no session, served `calculator.js?v=191` = the checkout = the release (C2).
- **Kits:** staged from `a29db35` (release `29162f6b`, all `b147dc93`, doors `3847d639`, vm `1b39e8e0`).

| # | step (time) | result |
|---|---|---|
| 1 | copy (12:22:32) | 3 kits verified and stamped; prod boot 2026-10-11 08:02:53 (no reboot). **A first try at 12:12 stopped before anything ran:** the helper copy's ssh login was refused ("Connection closed", exit 255) with the VPN up and port 22 open; the same line worked at 12:22. Cause unknown (one-off); the kit's `scp -q` hid ssh's reason (queued) |
| 2 | preflight (12:28:49) | **PASSED**: 0053, `5511355`, no tracked modifications, autologin empty, `ICB_ENVIRONMENT=prod`, the factor exactly `1.3170731707317074`, `calculator.js?v=189` = disk on the three doors, v1.61.1 × 3, 47 probes × 3 (the new route 404, allowed), the tag on origin, 92 saved costings (`92163e05…`) |
| 3 | All before (12:31:53) | page **#50** PASS 2035 / **FLAG 0 / ACCEPTED 115** / UNVERIFIABLE 76; the CLI per pack = the table, smoke 0 / 33; **PAGE = CLI** 2 702 / 2 702. (12:30: a first paste stopped by design — the page's All had not been clicked) |
| 4 | deploy (12:35:35–12:36:27) | **DEPLOYED `5511355 → a29db35`**. Backup `icb_platform_pre-v1.62.0_20261022-123535.dump`, 3 928 655 B, sha256 `2f8534f8…`, checked and read back. No migration, no SPA rebuild; restart 12:35:41 (pid 95897 → 99877), 4 workers, 0 bootstrap failed, **0 tracebacks since**; 18 pre-existing listed (19 Oct × 12, 21 Oct 07:38 × 6, all `ClientDisconnect`), not counted. Disk: `?v=191` = `fb14d2aa…`; then **127.0.0.1 → LAN → Cloudflare**: `{"version":"v1.62.0","environment":"prod"}`, no TEST banner, `calculator.js?v=191` = the release's bytes, **47 / 47** (the new route 401). Factor, audit list (7, pair = snapshot), SPA unchanged; 92 saved costings unchanged at that moment. The fetch printed `! [rejected] v1.47.1` (prod's own tag, left alone) |
| 5 | All after (12:40:13) | page **#51** (started 12:39:47, after the restart) PASS 2035 / **FLAG 0 / ACCEPTED 115** / UNVERIFIABLE 76; **PAGE = CLI** 2 702 / 2 702. **Before vs after, cell for cell: 2 936 / 2 936 identical** (status, base status, Excel and MES totals; four packs + smoke). (12:38: a first paste compared the pre-deploy page run #50 — the page's All was re-run) |
| 6 | doors (12:41:38) | **SUMMARY: 14 OK; no exceptions** |
| 7 | N10022 (browser) | **Not as ruled.** Michael did View changes → Update to today's prices → Approve & Save Costing → **Save as Rev.** instead of Cancel edit. A "Save as Rev." inserts a new row and only reads the original (its quote number): **the original N10022 (19 Oct, R391,853.38) stayed untouched and PENDING.** His list afterwards showed five N10022 rows dated 22 Oct (R389k, today's prices) and Lezette's repair R-2003 saved that morning |
| 8 | verify (13:11:16) | everything PASS — v1.62.0 / prod and 47 / 47 on the three doors, **0 tracebacks since the restart** (the re-open, View changes, the re-price and the saves included) — **except `QUOTES_UNCHANGED_SINCE_DEPLOY = 95 9cc317a6…` (want 92 92163e05…): STOP.** Only 3 rows were added after 12:35:35, so at least two of the day's N10022 rows were saved that morning on v1.61.1 |
| 9 | fetch (13:23:22) | the tar above (8 out folders) |

**Recorded (RT9_RULING_2):**
- **The STOP and its resolution:** the close's read-only quotes check (block Q) named the rows against the deploy's
  checked backup; Michael's test saves were soft-deleted through the MES Delete, sales work kept; the same check as the
  read-back. The rows by id and time: see **The close** below.
- **Prod's `icb-backend` restarted at 06:02:17 that morning** without a reboot (boot 2026-10-11 08:02:53): most likely
  Ubuntu's unattended upgrades; code unchanged, 0 tracebacks under it. For the Marnus list (automatic restarts).
- **Queued ops findings (not fixed here):** `scp -q` hiding ssh's reason on the first connection; the sim re-tagging
  v1.62.0 after the merge (fixed in the sim with the close: a post-release mode); the traceback list's "(exception
  line not found)" for the first half of a chained traceback.
- **Queued (Michael, 22 Oct):** the costings list and the costing view should show the revision number ("Rev. n"),
  so the newest version is visible — beside RT8's queued "re-priced line on the costing page".
- **Lessons (RULING_2):** the acceptance on prod is view-only, and the runbook says so on its own line (done above);
  the window runs outside quoting hours, or the BA asks the sales team to pause first (this one ran 12:22–13:23 and
  sales work landed inside it); the kit's quotes check names the rows itself (queued for the next kit).

### The close (RT9_RULING_2, 22 Oct 15:03–15:3x SAST)

**Block Q, 15:03:38** (`icb-rt9-quotes/out-20261022-150338`): the deploy's backup read back as the deploy's
(3 928 655 B, `2f8534f8…`); saved costings 92 at the deploy → **96** now; the backup's 92 rows streamed against the live
96, row by row: **added 4, changed 0, removed 0; created today 4** — so the original N10022 and every row that existed
at the deploy were byte-identical, and nothing had been saved that morning on v1.61.1 (RT9_RETURN_1b's inference from
the costings list was wrong: the list showed five N10022 rows for 22 Oct where the database held three — an open
observation about the list's display, queued with Michael's revision-number request).

| id | quote (first word) | created (as stored, SAST) | version | net total | classification (Michael) |
|---|---|---|---|---|---|
| 131 | N10022/10/2026 | 12:44:59 | 2 | 388 749.85 | his step-7 "Save as Rev." → **deleted** |
| 132 | N10022/10/2026 | 13:00:43 | 2 | 388 749.85 | his "Save as Rev." → **deleted** |
| 133 | N10022/10/2026 | 13:01:08 | 2 | 388 749.85 | his "Save as Rev." → **deleted** |
| 134 | L10023/10/2026 | 13:15:07 | 1 | 23 320.00 | Lezette's repair (R-2003), after step 8 → **kept** |

**The deletes** (Q2): the MES Delete is a soft delete of that one row (`api_delete_calculation`: `deleted_at`,
`deleted_by`, commit; idempotent; refused with blockers). Michael confirmed 131–133 as his, and soft-deleted each on
`https://mes.icecoldgrp.online/mes-app/costings` (right-click → Delete costing… → Delete), identifying the rows by their
View link's id. A first read-back at 15:12 (and two more at 15:17 and 15:18) still read N: the deletes had not reached
prod yet — the read-back doing its job. **15:20:04 (`out-20261022-152004`): 131, 132, 133 deleted Y; 134 N; changed 0,
removed 0**; the digest `f647e643…` → `7f550428…` (the three delete stamps and nothing else).

**Block 9b, 15:23:07:** `Downloads\rt9-window-back-20261022-152307.tar` (24 954 880 B, sha256 `6a556c88…`), 13 out
folders (the window's 8, the quotes check's 5), every `SHA256SUMS.out` checked; the close's records committed here under
`icb-rt9-quotes/`.

**Block 10, 15:25:17:** prod `/tmp` — removed by exact name and read back absent on a second connection:
`icb-release-v1.62.0{,.tar}`, `icb-rt2-all{,.tar}`, `icb-rt2-doors{,.tar}` (with RT7's old out folders inside),
`icb-release-v1.61.1{,.tar}` (RT7's leftover, RULING_2 Q1), `icb-rt9-window.started`, `icb-rt9-quotes{,.tar}`; the
helper `icb-rt9-vm.sh` removed itself. Left as ruled: `icb-rollback-<ts>.txt` (the deploy tool's own anchor).

**State at the close:** prod = v1.62.0 `a29db35`, alembic 0053, 96 saved costings of which 3 soft-deleted today
(131–133); the original N10022/10/2026 PENDING as sent; L10023 live; prod `/tmp` clean of RT9 and RT7.
