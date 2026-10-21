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

Then click **Cancel edit**. Do **not** save, re-price or overwrite it. Tell the CA what you saw (a screenshot is fine).

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

**10. Remove the window's kits from prod `/tmp`** by exact name (the list is in `rt9_vm.sh`: the three RT9 kits and
their tars — RT7's old out folders inside the reused All and door folders go with them — RT7's v1.61.1 release kit
and tar, and the window start mark), then read every name back.

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt9-stage\window\run_window_cleanup.ps1"
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
| the release kit, 18 scenarios | WSL: `ops/prod-release-v1.62.0/sim/run_all.sh` (the real `mkstage_window.sh` + `mkstage.sh`, the real `deploy/prod/icb-deploy.sh`, stub doors that answer for the RUNNING code, a Cloudflare edge that keeps the first bytes per URL) | see `RT9_RETURN_1` |
| every paste block above | Windows PowerShell 5.1: `ops/prod-release-v1.62.0/sim/ps51/run_blocks.ps1` — reads THIS runbook's blocks and pastes each into a new PowerShell 5.1 window against a fake prod in WSL (native ssh/scp stand-ins, so the quoting is PowerShell 5.1's own) | see `RT9_RETURN_1` |

## OUTCOME

(appended after the window)
