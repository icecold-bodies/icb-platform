# Prod deploy: v1.63.0 (RT12): revisions visible, accept by record (RT10)

Committed BEFORE the run (D3). The OUTCOME is appended after the window. Dispatch `RT12_DISPATCH_release_v1.63.0`
(24 Oct 2026); rulings `RT12_RULING_<n>` (`RULING_0A`: #231 in; `RULING_1`: #232 in, the base moved). Built by RT10
(#229 `dcba297`, #230 `51231d5`, close #231 `242e57a`) and RT11 (#232 `4e4d251` = the base tip); released by RT12, a
fresh release CA (D1).

## What ships (prod `a29db35` = v1.62.0 → the v1.63.0 squash commit)

- **The app code (RT10):** `routers/calculator.py`, `routers/exports.py`, `routers/plan.py`, `routers/prejob_cards.py`,
  `routers/validated_references.py`, `services/revisions.py` (new), `services/prejob_cards.py`, `schemas/prejob.py`,
  `report_engine.py`, `main.py`; the templates `calculator.html`, `calculator2.html`, `dashboard.html`,
  `results.html`; the two calculators' scripts — **`calculator.js?v=191 → ?v=192`** and
  **`calculator2.js?v=128 → ?v=129`** (each template and file, both served from disk).
- **The MES app (SPA, `frontend/`) changes** (the costings list, the costing view, Accept, the plan and planning
  screens, the pre-job pages): the deploy **rebuilds it** (`npm run build`, as v1.61.0's did). The new bundle has a new
  name and carries RT10's text; the kit checks both.
- **RT11's letterhead quote code (#232), inert on prod:** `report_engine.py` (WeasyPrint renders the letterhead
  quote; the gate `letterhead_quote_available` reads **False** where WeasyPrint is missing), `routers/exports.py`
  (the route answers a plain **503** instead of a raw 500 — a changed response, **no new route**), and two
  WeasyPrint-only static files: `static/css/report.css` and `static/fonts/*` (the Liberation faces). They are read
  from disk by `report_engine` and **named by no template**, so no browser loads them and **no `?v=` moves** (B2).
  **`backend/requirements.txt` gains the one line `weasyprint==70.0`** — a manifest change only: **nothing is
  installed by this release** (the deploy tool warns *"dependency manifests changed (1)"* exactly once, by design; the
  kit asserts that line, never runs pip, and checks before and after that prod's venv does **not** hold weasyprint).
  RT11's own install kit adds the package later (apt + pip + restart, no code move).
- **No migration** (alembic stays **0053**), **no new route** (the probe list is v1.62.0's, 47 lines; `mkstage.sh`
  refuses a range that declares a route without a line). Python changes, so the service **restarts** (a few seconds
  without the app).
- **Also in the range** (not app code): RT9's close #228 (the read-only quotes check, its sims and evidence), RT10's
  tests, journeys, prod-check kit and evidence (#229, #231), RT11's tests, prod-check and install kits (#232), a CI
  step (WeasyPrint's libraries on the Linux runner), and this release PR: `backend/VERSION` → `v1.63.0`, the CHANGELOG
  entry, this runbook, `ops/prod-release-v1.63.0/`.
- **Target SHA:** the squash commit of this release PR, on `backport/v1.39-base` at `4e4d251` (#232 in). **RT13 must
  not be in the range** (the stager's expected values would not match; the BA has asked Michael not to merge it before
  v1.63.0 is out). Every expected value is derived from that commit by the stager; the OUTCOME names it.

## Behaviour a user can notice (for the BA's note to the sales team, after the window)

- **REV everywhere staff see a costing** (REV 0 = the first save, Michael's rule): the costings list reads
  `N10022/10/2026 · REV 1` with **Latest** on a quote's newest live revision and **· earlier** on the older ones, the
  revisions of one quote together; the costing view has its **Revisions** card and the re-priced line; the calculator's
  edit banner says **"REV n is the latest"** when an older revision is open.
- **Every row and every action goes by the record** (not the quote number): Accept, Decline, Replace, the pre-job card
  and the plan act on the revision clicked. This closes the defect where Accept on a newer revision accepted the
  oldest and built its job. **N10021/10/2026 has two live Pending revisions today:** until this ships, Accept on its
  REV 1 row would accept REV 0.
- **Save as Rev.** takes its number from the server (max over the whole chain + 1, under a row lock): no two revisions
  share a number. **Replace** is a soft delete and names what it replaces. **Accept on an older revision asks first**
  ("This is REV 0. REV 2 is the latest. Accept REV 0 anyway?").
- **The exports and the letterhead `ref_no` carry `REV n` from REV 1** (a first save stays unmarked).
- **"Generate Quote" is offered only where the letterhead PDF can render.** WeasyPrint is not on prod, so a body
  costing's results page says **"Official quotes are issued from SAP."** where the button was (it 500'd before); a
  direct call of the route answers a plain 503. RT11's install (a later window) turns it on; nothing changes on screen
  for staff until then.
- **Everyone reloads after the update** (Ctrl+F5): the MES app and both calculator scripts changed. A tab opened before
  it still runs the old scripts (the BA tells the sales team).
- How a NEW costing prices does not change: the costing audit reads the same before and after.

## Expected numbers

- **All BEFORE and All AFTER: the same** — v1.63.0 changes how revisions are shown and accepted, not how costings
  price; the accepted list, the CI snapshot and the golden do not move in the range (`mkstage.sh` refuses otherwise).
  Both read RT7's after-state of 20 Oct (= RT9's 22 Oct), cell for cell (2 936 / 2 936), and PAGE = CLI:

| pack | FLAG | ACCEPTED | PASS | SKIP | UNVERIFIABLE |
|---|---|---|---|---|---|
| chillers | 0 | 0 | 590 | 126 | — |
| freezers | 0 | 72 | 501 | 117 | — |
| icecream | 0 | 40 | 416 | 116 | 40 |
| explosive | 0 | 3 | 528 | 117 | 36 |
| **All (2 702)** | **0** | **115** | 2 035 | 476 | 76 |
| smoke (234) | 0 | 33 | 156 | 45 | — |

  If prod's prices moved since 22 Oct, All BEFORE shows it and the window STOPs there: nothing has changed yet.
- **The no-session probes: 47 per door**, before and after. **No route is new in this range**, so no 404 is allowed at
  any time (v1.62.0's kit allowed one, for RT8's new route, before the deploy only).
- **Tracebacks are counted from this deploy's own restart** (RT7's lesson, ratified default 2). Earlier ones are
  listed with their time and exception class only (never the message: G4) and never counted. **A chained traceback
  lists every class** (RT9's queued finding: the `anyio.WouldBlock` / `anyio.EndOfStream` halves of prod's
  `ClientDisconnect` chains read "(exception line not found)" on 22 Oct; fixed in this kit, with RT9's function as the
  negative control).
- **The dependency manifest:** the deploy tool's dry run and deploy each print *"dependency manifests changed (1) -
  check whether pip/npm install is needed BEFORE continuing"* **once** — expected (the `weasyprint==70.0` pin). The kit
  STOPs if the line is missing, doubled, or if any pip install is mentioned. **prod's venv must not hold weasyprint**
  before (preflight, and the deploy's step 4) or after (every post-deploy assert: `WEASYPRINT_IN_VENV = absent`);
  gaining it in this window is a STOP. **The gate reads False** at the new service's start (`LETTERHEAD_GATE`, from the
  journal since the restart), and the view-only acceptance sees "Official quotes are issued from SAP." on a results page.
- **verify, if run before the deploy, fails on exactly 21** (the simulation's list; the window does not run it):
  `HEAD`, `TAG_LOCAL`, `DESCRIBE`; `LETTERHEAD_GATE` (v1.62.0 logs no gate line); `V_calculator.js`,
  `DISK_calculator.js`, `V_calculator2.js`, `DISK_calculator2.js`; `SPA_MARK_DISK`; and per door `VERSION_x`,
  `calculator.js_x`, `calculator2.js_x` ("not probed": the new bytes are not on disk, so no door is asked for `?v=192`
  or `?v=129`) and `SPA_MARK_x` (the served SPA has no RT10 text yet).
- **The saved costings do not move during the window:** the deploy records their count + md5 (whole rows) **and every
  row's own md5 by id**; step 8 must read the same after the view-only acceptance. If it does not, the kit **names the
  rows itself** — added, changed, removed since the deploy, each as `id | quote (first word) | created | version |
  status | deleted Y/N`, nothing else (G4) — so a mismatch never needs a second kit (RT9's lesson).
- **The three doors, in order (D4):** `/health/version` = `{"version":"v1.63.0","environment":"prod"}`; `calculator.js?v=192`
  and `calculator2.js?v=129` served = the release's bytes; the SPA bundle served = the one the deploy built, carrying
  RT10's text. No new `?v=` is probed through Cloudflare before the bytes are on disk.

## The kits (committed, staged byte-exact from the merge commit by ONE script)

`bash ops/prod-release-v1.63.0/mkstage_window.sh C:/Users/micge/Documents/icb-rt12-stage/window <merge-sha>` (the CA,
after the tag is on origin) stages three kits, each with `lib/`, the place it must run (`icb-mes-prod`,
`icb_platform @ 127.0.0.1:5432`, the HEADs it may see) and the reboot guard:

| kit | runs | over |
|---|---|---|
| `icb-release-v1.63.0` | `release.sh preflight / deploy / verify` | v1.62.0 (and v1.63.0 after the deploy) |
| `icb-rt2-all` | `rt2_all.sh pre / post` (its first line still says RT7: the shared kit is unchanged) | either |
| `icb-rt2-doors` | `rt2_doors.sh` | either |

Beside the tars, **Michael's lines** (ASCII, filled in by the stager, each run by its full path from PowerShell):
`run_window_copy.ps1` (step 1), `run_window_step.ps1` (steps 2–6 and 8: ssh to the VM, then the staged kit BY PATH
under sudo), `run_window_fetch.ps1` (step 9) and `run_window_cleanup.ps1` (step 10, the close), with
`window_common.ps1` and `rt12_vm.sh` — the VM side, which every line copies to prod as `/tmp/icb-rt12-vm.sh` and runs by
path. No line ever hands a script to ssh as an argument (RT8's PowerShell 5.1 quoting fault, 21 Oct), and **no scp
runs `-q`** (RT9's 22 Oct finding: it hid ssh's reason for a refused login; the reason now stays on the screen, with
"paste the same line again once"). Each line's FIRST output line names this laptop, prod's machine, prod's HEAD and
boot time, and it refuses a wrong place before anything runs. The `:8000` check line (block B) is the committed
`ops/prod-release-v1.63.0/local/check_8000.ps1`, copied to `C:\Users\micge\Documents\icb-rt12-stage\local\`.

**Prod `/tmp`:** clean of every earlier window since RT9's close (22 Oct); RT10's and RT11's read-only checks removed
themselves. The kits write only under their own folders (prod runs `fs.protected_regular=2`: RT10's `tee` lesson, 23
Oct); the deploy tool's own `/tmp/icb-rollback-<ts>.txt` anchors are left alone.

## How Michael runs each step

One step, one block. Paste the line into the window named, exactly as written. Wait for the `########` line at the
end, then copy the whole window and paste it back to the CA; run the next step only when the CA says "next".

### Before the window (after the merge, the tag and the CA's fast-forward of your clone)

Your clone's MES build already carries RT10 (built on 23 Oct from #229; #230 and this release change no `frontend/`
file), so no `npm run build` is needed: the fast-forward moves the python and `backend/VERSION`, and a restart picks
them up.

**A. Restart :8000.** Close the window where :8000 runs now (or press Ctrl+C in it and close it). Then:

📋 PASTE INTO: Command Prompt (a new window; leave it open afterwards, it is :8000)
```
"C:\Users\micge\Documents\icb-platform\scripts\start.bat"
```
FIRST LINE YOU SHOULD SEE: [start] Applying migrations (alembic upgrade head)...
IT WILL ASK FOR: nothing
WHEN IT ENDS: it does not end: it keeps running once it shows "Application startup complete." → leave it open and go to B
IF YOU SEE "STOP": there is no STOP line here; if you see "Traceback" or "ERROR", paste the window back to me

**B. Check :8000** (read only: what it serves = what your clone holds, and its version).

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\local\check_8000.ps1"
```
FIRST LINE YOU SHOULD SEE: ######## RT12 :8000 check (read only) . http://127.0.0.1:8000 . clone C:\Users\micge\Documents\icb-platform . …
IT WILL ASK FOR: nothing
WHEN IT ENDS: ######## DONE - :8000 serves v1.63.0 (calculator.js and calculator2.js = the clone, SPA … = the clone, with RT10's text). → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed; it says what to do (usually: close the start.bat window and do A again); paste it back to me

### The window (Michael's time, OUTSIDE quoting hours; the BA asks the sales team to pause first; no quote is saved during it)

**1. Copy the kits to prod** (the VPN must be up). The line first reads your C: drive's free space: **under 5 GB it
STOPs before anything reaches prod** (free some space — your Downloads folder holds earlier window tars — then paste it
again). With enough space its second line is the window line, and the kits go over:
`######## RT12 window copy (step 1) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head a29db35 . boot …`

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\window\run_window_copy.ps1"
```
FIRST LINE YOU SHOULD SEE: == C: free: … GB (the window needs 5 GB or more)
IT WILL ASK FOR: nothing (no sudo in this step)
WHEN IT ENDS: ######## DONE - step 1: the kits are in prod /tmp, verified and stamped … → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing ran on prod; paste it back to me (if it says the login was refused, paste the same line again once; if it says DISK, free space first)

**2. Preflight** (read only). On prod it ends `######## PREFLIGHT PASSED`: v1.62.0 on the three doors,
`calculator.js?v=191` and `calculator2.js?v=128` = disk on the three doors, the SPA served = disk (without RT10's text
yet), 47 probes per door (no 404), the 4G factor, weasyprint absent from the venv, npm and node_modules present, the
tag on origin.

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\window\run_window_step.ps1" preflight
```
FIRST LINE YOU SHOULD SEE: ######## RT12 window step 2 preflight (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head a29db35 . boot …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 2 (preflight) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed (read only); paste it back to me

**3. All BEFORE.** First, in the browser: open `https://192.168.0.251/admin/costing-audit` → **All** → Run, and
wait until it finishes (cells: flag 0 · accepted 115 · pass 2035 · unverifiable 76). Then:

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\window\run_window_step.ps1" all-before
```
FIRST LINE YOU SHOULD SEE: ######## RT12 window step 3 All before (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head a29db35 . boot …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 3 (all-before) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed (read only); paste it back to me

On prod it ends `######## DONE (pre): PAGE = CLI`. Any count that differs from the table above is a STOP: the CA
compares the cells before the deploy.

**4. Deploy** (the service restarts once: a few seconds without the app; the SPA build runs first, about a minute).
On prod: the checked backup (size and sha256 read back), no migration, the deploy tool's one expected warning
(*dependency manifests changed (1)*: the weasyprint pin; nothing installed), `npm run build`, the restart, 0 tracebacks
since it, weasyprint still absent from the venv, the gate logged False, `calculator.js?v=192` and
`calculator2.js?v=129` on disk, the SPA rebuilt under a new name with RT10's text, then 127.0.0.1, LAN and Cloudflare
each `{"version":"v1.63.0","environment":"prod"}`, no TEST banner, both scripts = the release's bytes, the SPA bundle =
the one built, 47 probes; it ends `######## DEPLOYED`.

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\window\run_window_step.ps1" deploy
```
FIRST LINE YOU SHOULD SEE: ######## RT12 window step 4 deploy . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head a29db35 . boot …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 4 (deploy) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": run nothing else (not even this line again) until I answer; paste it back to me

**5. All AFTER.** First, in the browser: `https://192.168.0.251/admin/costing-audit` → **All** → Run again; wait
until it finishes (the same counts as step 3). Then:

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\window\run_window_step.ps1" all-after
```
FIRST LINE YOU SHOULD SEE: ######## RT12 window step 5 All after (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 5 (all-after) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed (read only); paste it back to me

On prod it ends `######## DONE (post): PAGE = CLI`; the counts must equal step 3's, cell for cell.

**6. Doors** (RT2's rear-door report, read only). On prod: `SUMMARY: 14 OK`.

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\window\run_window_step.ps1" doors
```
FIRST LINE YOU SHOULD SEE: ######## RT12 window step 6 doors (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 6 (doors) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed (read only); paste it back to me

**7. The view-only acceptance — in the browser, nothing to paste, NOTHING SAVED** (ratified default 5; RT9's
lesson). Close every MES and calculator tab opened before the deploy. Then open
`https://mes.icecoldgrp.online/mes-app/costings` and press Ctrl+F5 once it loads. Check three things:
- **The costings list:** **N10021/10/2026 · REV 1 · Latest** sits above **· REV 0 · earlier**, the two together. Press
  F5: still one row per revision, no ghost rows.
- **Open N10021 REV 0** (click its row): the header says **"REV 1 is the latest →"**.
- **A results page:** on the **N10021 REV 1** row click **View** (`/mes-app/costings/results/<id>`): where "Generate
  Quote" was, the line **"Official quotes are issued from SAP."**

**Do not click Accept, Update or Save.**

Then tell the CA what you saw (a screenshot of each is fine). Nothing is saved; step 8 proves it.

**8. Verify** (read only), after the acceptance: everything as at the deploy, plus
`PASS QUOTES_UNCHANGED_SINCE_DEPLOY` (no quote was saved; if one was, the rows are named by id) and 0 tracebacks
since the restart (the list, the costing view and the results page included). On prod it ends
`######## VERIFY: 0 check(s) failed`.

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\window\run_window_step.ps1" verify
```
FIRST LINE YOU SHOULD SEE: ######## RT12 window step 8 verify (read only) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 8 (verify) ended with exit 0. → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed (read only); paste it back to me

**9. Fetch** the window's records to your Downloads folder (one tar).

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\window\run_window_fetch.ps1"
```
FIRST LINE YOU SHOULD SEE: ######## RT12 window fetch (step 9) . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head …
IT WILL ASK FOR: nothing (no sudo in this step)
WHEN IT ENDS: ######## DONE - step 9: … (the tar's full path in your Downloads folder) → copy the whole window and paste it back to me
IF YOU SEE "STOP": nothing was changed; paste it back to me

### The close (only on the CA's word, after the fetch)

**10. Remove the window's kits from prod `/tmp`** by exact name (the list is in `rt12_vm.sh`: the three kits, their
tars, the window start mark), then read every name back. Not touched: `/tmp/icb-rollback-<ts>.txt`, which the repo's
own `icb-deploy.sh` writes on every deploy (its rollback anchor; RT9's deploy left one too).

📋 PASTE INTO: PowerShell (your laptop)
```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt12-stage\window\run_window_cleanup.ps1"
```
FIRST LINE YOU SHOULD SEE: ######## RT12 window close (step 10): prod /tmp cleanup . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head …
IT WILL ASK FOR: the VM password (sudo); nothing shows while you type
WHEN IT ENDS: ######## DONE - step 10: prod /tmp: every RT12 window name removed and read back absent … → copy the whole window and paste it back to me
IF YOU SEE "STOP": some names may already be gone; paste it back to me

## If a step STOPs

- **Steps 1–3:** nothing has changed on prod. The CA reads the STOP line and answers; the window can move.
- **Step 4 (deploy) STOPs before `8. deploy`:** nothing has moved (the backup may exist: it stays). After `8. deploy`
  started, the code may have moved: run the same step-4 line again **only on the CA's word** — it says `RESUME` and
  re-runs the deploy script's idempotent steps (the SPA build among them), then every check.
- **`STOP [SPA_REBUILT]`** (the bundle name did not change after `DEPLOYED`): the build did not run; the code has
  moved. The same step-4 line again, on the CA's word: the RESUME path rebuilds it.
- **A STOP on a Cloudflare check after the checks passed on 127.0.0.1 and LAN** (`VERSION_CF`, `calculator.js_CF`,
  `calculator2.js_CF`): the edge still serves the old answer. A `calculator*.js_CF` STOP would mean someone fetched
  the new `?v=` through Cloudflare before the deploy: Michael purges the Cloudflare cache, then step 8 (verify)
  re-checks. (`SPA_CF` cannot go stale: the rebuilt bundle has a new name.)
- **Steps 5–9:** read only; the CA decides. A `QUOTES_UNCHANGED_SINCE_DEPLOY` FAIL in step 8 comes with the rows named
  by id: the CA reports them to the BA; nothing is deleted in the window.

## Rollback (decided before the run)

- **The code:** back to `a29db35`: `sudo -u icb git -C /opt/icb-platform reset --hard a29db35`, then the SPA (this
  range changed `frontend/`): `sudo -u icb bash -lc 'cd /opt/icb-platform/frontend && npm run build'`, then
  `sudo systemctl restart icb-backend`; then `/health/version` = v1.62.0 on the three doors. No migration, no data
  moved, nothing installed (the requirements pin goes back with the code; the venv was never touched): nothing else to
  undo. A browser that loaded `?v=192` / `?v=129` gets `?v=191` / `?v=128` again from the old
  templates, and the old SPA bundle name from the rebuilt `dist/index.html`.
- **The full restore** (only if the above fails): `icb_platform_pre-v1.63.0_<ts>.dump` (pg_dump -Fc, written and
  checked by step 4).

## Simulation

| sim | how | result |
|---|---|---|
| the release kit, 23 scenarios (two of them: prod's venv gains weasyprint, before or after the deploy → STOP) | WSL: `ops/prod-release-v1.63.0/sim/run_all.sh` (the real `mkstage_window.sh` + `mkstage.sh`, the real `deploy/prod/icb-deploy.sh`, stub doors that answer for the RUNNING code, a Cloudflare edge that keeps the first bytes per URL, a sticky `/tmp` under `fs.protected_regular=2` with the kit owned by the ssh user, a journal with prod's chained tracebacks) | `sim/RESULTS.md` |
| every paste block above | Windows PowerShell 5.1: `ops/prod-release-v1.63.0/sim/ps51/run_blocks.ps1` — reads THIS runbook's blocks and pastes each into a new PowerShell 5.1 window against a fake prod in WSL (native ssh/scp stand-ins, so the quoting is PowerShell 5.1's own; the `:8000` check runs for real against Michael's dev server) | `sim/RESULTS.md` |

## OUTCOME

**18 Nov 2026, 16:42–20:22 SAST: prod = v1.63.0 `443a7b7`, alembic 0053. Every release check passed on the three
doors in order. The costing audit is identical before and after the deploy, 2 936 / 2 936 cells, PAGE = CLI
(RT12_RULING_3's gate: All after = All before, cell for cell). No quote was saved during the window (102 saved
costings, unchanged). The window stopped once, at step 3, because All before did not read the ratified table: prod's
data had moved in UAT. It was held 17:09–19:46 for RT12_RULING_3, then resumed at a fresh step 3.** Evidence:
`docs/audit/rt12_2026-11/prod/window_20261118/` (the kits' out folders, without the HTML and JSON reports, plus the
preflight's and verify's `run.log`). The window tar is `Downloads\rt12-window-back-20261118-201933.tar`, sha256
`82bab53a2736fde4…`, 25 118 720 B.

**Before the window:**
- **The merge, in the reverse order (RT12_RULING_2A):** RULING_2 set #233 first and then #234 rebased onto it. On
  18 Nov #234 (RT11 close) merged first as `83f5e9c` (12:32:34 UTC), then #233 as **`443a7b7`** (12:33:49 UTC, parent
  `83f5e9c`). I stopped before the tag. Checks on the result:
  - `83f5e9c..443a7b7` = #233's 26 files (the same patch-id as `4e4d251..a171831`);
  - `4e4d251..83f5e9c` = #234's 4 (the CI runner pin `ubuntu-24.04`, its test, RT11's evidence and runbook), with no
    app code, dependency, static, `frontend/`, `deploy/` or migration;
  - the range `a29db35..443a7b7` = 229 files (C-sorted sha `ff836298…`); the app tree is identical to `a171831`'s.
- **C3 on the squash itself:** `ci.yml` runs build & test only on pull requests and on pushes to `main`. So proof
  **PR #235** ("DO NOT MERGE") put two refs on GitHub and pushed no commit: head `rt12/ci-head-443a7b7` = `443a7b7`,
  base `rt12/ci-base-83f5e9c` = its parent. Its checks attached to `443a7b7`: **7 / 7 green** (build & test
  ubuntu-24.04 13:01 UTC and windows 13:06 UTC, the costing audit × 5). #235 was then closed unmerged and both
  branches deleted (read back absent). The BA accepted the approach.
- **Tag:** `v1.63.0` = tag object `d99b165`, local = origin, peeling to `443a7b7`.
- **:8000:** Michael's clone was fast-forwarded `4e4d251 → 443a7b7` (no overlap with his local edits; 186 local
  entries byte-identical before and after, `389f7a4a`). Blocks A and B at 16:40: `DONE v1.63.0`; both calculator
  scripts and the SPA bundle (`index-I5Myzg-I.js`, with RT10's text) = his checkout.
- **Kits:** staged from `443a7b7` by `mkstage_window.sh` (release `f08a4d8f`, all `f7ad9234`, doors `94683cb7`, vm
  `14365780`).

| # | step (time) | result |
|---|---|---|
| 1 | copy (16:45:05) | 3 kits verified and stamped (window mark 16:45:07); C: 19.2 GB free. Prod boot `2026-11-17 06:46:19` (see the reboots below). At 16:42 the LAN door did not answer from the laptop until the VPN was connected |
| 2 | preflight (17:04:34) | **PASSED**: 0053, `a29db35`, no tracked modifications, autologin empty, `ICB_ENVIRONMENT=prod`, the factor exactly `1.3170731707317074`; `calculator.js?v=191` `fb14d2aa…` and `calculator2.js?v=128` `a5432091…` = disk on the three doors; the SPA `index-BBI2d9Oo.js` `cd39cb56…` = disk × 3, without RT10's text; v1.62.0 × 3; 47 / 47 × 3; weasyprint absent; npm and node_modules present; the tag on origin; 0 tracebacks since the service started (17 Nov 06:46:31); **102 saved costings** (`5fe3353b…`) |
| 3 | All before (17:09:18) | **STOP**: page **#52** (17:08:46) = CLI 2 702 / 2 702, but the counts did not read the ratified table. Freezers FLAG 16 / ACCEPTED 64 / PASS 493 (table 0 / 72 / 501); smoke 3 / 27 / 159 (table 0 / 33 / 156); the other packs = the table. Step 4 was not sent; `RT12_RETURN_1c` → **`RT12_RULING_3` (a)**: the gate becomes All after = All before, cell for cell, on today's data |
| 3 | All before, fresh (19:49:59) | Immediately before step 4, as ruled. Page **#53** (19:46:21, "No change since … run #52") = CLI 2 702 / 2 702; every pack, smoke included, = run #52 (table below). Prod boot unchanged; the last data-kit journal still 15 Oct |
| 4 | deploy (19:54:44; on prod 19:54:57–19:56:21) | **DEPLOYED `a29db35 → 443a7b7`**. Backup `icb_platform_pre-v1.63.0_20261118-195457.dump`, 4 200 475 B, sha256 `86be63c1…`, checked and read back. No migration. The deploy tool's one expected warning *"dependency manifests changed (1)"*, once in the dry run and once in the deploy; no pip run; weasyprint absent before and after. `npm run build`: `index-BBI2d9Oo.js → index-I5Myzg-I.js` (`b53fac84…`, RT10's text × 1). Restart 19:55:34 (pid 1084 → 12445), 4 workers, 0 bootstrap failed, **0 tracebacks since** (0 pre-existing in the 14 days before). **The gate logged False.** Disk: `?v=192` `9d2eb371…`, `?v=129` `bb218b79…`. Then **127.0.0.1 → LAN → Cloudflare**: `{"version":"v1.63.0","environment":"prod"}`, no TEST banner, both scripts = the release's bytes, the SPA = the one built, **47 / 47**. The factor, the audit list (7, pair = snapshot), the golden month 2026-09 and the 102 saved costings were unchanged. The fetch printed `! [rejected] v1.47.1` (prod's own tag, left alone). My own LAN read-back at 19:57:31: v1.63.0, both scripts = `443a7b7`'s blobs |
| 5 | All after (20:01:47) | page **#54** (started 20:00:35, after the restart) = CLI **2 702 / 2 702**; every pack, smoke included, = step 3. (19:58:58: a first paste compared the pre-deploy page run #53, because the page's All had not been re-clicked. The kit let it pass; see the findings. The page was re-run and the line pasted again) |
| 6 | doors (20:03:04) | **SUMMARY: 14 OK; no exceptions** |
| 7 | view-only acceptance (browser, ≈20:05–20:15) | On `https://mes.icecoldgrp.online/mes-app/costings` after Ctrl+F5 (a first pass was on the LAN address, then repeated on Cloudflare). **N10021/10/2026 has three revisions on prod, not two:** REV 2 (record 136, saved 24 Oct 08:55 by admin, "Moved to today's prices on 24 Oct 2026, from REV 1") · **Latest** ("3 revisions") above REV 1 · **earlier** (22 Oct 17:09) and REV 0 · **earlier** (record 129, 19 Oct 08:06), the three together, one row each, no ghost rows, all Pending. REV 0's view: **"REV 2 is the latest →"**. REV 2's results page: **"Official quotes are issued from SAP."** where Generate Quote was (its ✓ Accepted / ✗ Declined pair = the pending buttons). Nothing was clicked or saved. The runbook's "REV 1 · Latest" came from RT10's prod check of 23 Oct; REV 2 is a UAT re-price made the day after. The behaviour is the release's, for three revisions |
| 8 | verify (20:17:07) | **0 checks failed** (the window line's exit 0; the closing `######## VERIFY: 0 check(s) failed` line is in the fetched `run.log`, not on the screen; see the findings). v1.63.0 / prod, both scripts, the SPA, 47 / 47 on the three doors; **0 tracebacks since the restart** (the list, both costing views and the results page included); weasyprint absent; the gate False; **`QUOTES_UNCHANGED_SINCE_DEPLOY = 102 5fe3353b…`** |
| 9 | fetch (20:19:33) | the tar above (8 out folders); the prod copy removed |
| 10 | close (20:21:56) | prod `/tmp`, removed by exact name and read back absent on a second connection: `icb-release-v1.63.0{,.tar}`, `icb-rt2-all{,.tar}`, `icb-rt2-doors{,.tar}`, `icb-rt12-window.started`; the helper `icb-rt12-vm.sh` removed itself. Left as ruled: `/tmp/icb-rollback-20261118-195505.txt` (the deploy tool's own anchor) |

**Prod's audit state on 18 Nov 2026 (RT12_RULING_3), read four times, identical every time** (17:09 and 19:50
before the deploy, 19:59 and 20:01 after it):

| pack | FLAG | ACCEPTED | PASS | SKIP | UNVERIFIABLE |
|---|---|---|---|---|---|
| chillers | 0 | 0 | 590 | 126 | — |
| freezers | **16** | **64** | **493** | 117 | — |
| icecream | 0 | 40 | 416 | 116 | 40 |
| explosive | 0 | 3 | 528 | 117 | 36 |
| **All (2 702)** | **16** | **107** | **2 027** | 476 | 76 |
| smoke (234) | **3** | **27** | **159** | 45 | — |

**Before vs after, cell for cell:** each pack's CSV report is byte-identical in all four runs (sha256 smoke
`e201dfa3…`, chillers `62503edc…`, freezers `98ee10da…`, icecream `3a26c481…`, explosive `91e16ca2…`). The JSON
reports agree on every cell's status, base status, accepted entry, and Excel and MES totals to the cent: **2 936 /
2 936**, 0 differ. Negative control: one freezer cell moved by R0.01 in a copy was caught, 1 differ.

**Recorded (RT12_RULING_3):**
- **Why All before differs from the ratified table.** Michael hand-edited the plywood prices on the freezer templates
  on prod after 22 Oct (UAT). The 16 freezer cells moved to FLAG (8 from ACCEPTED, 8 from PASS). In smoke, 3 ACCEPTED
  cells moved to FLAG and 3 to PASS. No kit made the change (the last data-kit journal is 15 Oct), and the release
  changes no pricing (the stager refuses any move of the accepted list, the snapshot or the golden; the golden is
  `ed4d57bc…`).
- **The 16 + 3 cells go to a separate data-check lane with Burt:** which hand edits, then accept, revert or correct.
  It closes by regenerating the CI snapshot (H3). One observation for that lane, not a conclusion: step 6's door report
  shows the three freezer templates' drafts last saved 29 Sep, 29 Sep and 2 Oct. So the plywood edits may sit outside
  the template drafts (in the material prices, for example).
- **Prod rebooted twice since 11 Oct:**
  - ≈ **7 Nov 07:21** (on 13 Nov 20:33 SAST its uptime read 6 days 13 h);
  - **17 Nov 06:46:19** (the service started 12 s later, 06:46:31, with 0 tracebacks since).

  Michael has asked Marnus whether these are Group IT patching; this ties to the queued 06:02 restart item. The kits
  were staged after the 17 Nov boot and stayed valid.
- **Banked (RT12_RULING_3):** while UAT lasts, release runbooks state the audit gate as **before = after, cell for
  cell**, with today's counts recorded, not the ratified table. The ratified table comes back as the gate when UAT
  ends (the go-live checklist).
- **The sales pause:** the sales team had the BA's note before the first step 3. RULING_3 had the BA send it again
  before the fresh step 3, and step 4 ran on that condition. Nothing was saved between the deploy and step 8.

**Queued for the BA (found in this window, not fixed here):**
1. **`rt2_all.sh post` accepts a page run from before the deploy.** Its "not before" is the last data-kit journal
   (15 Oct) and its age limit is 45 minutes, so step 5's first paste passed against page run #53 (19:46, before the
   19:55:34 restart). I caught it while reading the paste, and the page was re-run (#54). Fix for the next kit: the
   after-run's page must have started after this deploy's restart.
2. **The last line of a step can be lost on screen.** `release.sh` writes through `exec > >(tee -a "$OUT/run.log")`,
   and the window line runs `ssh -t`. When bash exits before `tee` has drained, the pty closes and the screen misses
   the end. That happened with step 8's `######## VERIFY` line. The exit code is the script's own (exit 0 only when
   no check failed), and `run.log` holds the line. Fix: close the redirect and wait for `tee` before exiting.
3. **Acceptance text tied to the data goes stale on a UAT prod**, as the audit table did. The runbook named "REV 1 ·
   Latest" from 23 Oct, and prod had a REV 2 from 24 Oct. Next time, state the acceptance as behaviour: the newest
   live revision says Latest, the others say "· earlier", and an older one's header names the newest.
4. **A browser step names the address and how to recognise it.** The first acceptance pass ran on the LAN address,
   though the runbook named Cloudflare's. A line such as "the address bar starts with `mes.icecoldgrp.online`" would
   prevent that.
5. The SPA build printed npm's and Browserslist's upgrade notices. Nothing was run; it is noise for a later tidy-up.

**State at the close:**
- **Prod:** v1.63.0 `443a7b7` (tag `v1.63.0` `d99b165`), alembic 0053, 102 saved costings (`5fe3353b…`). Weasyprint is
  not in the venv, so the letterhead gate reads False and Generate Quote stays off until RT11's install. Prod `/tmp`
  holds no RT12 name.
- **Michael's clone:** at `443a7b7`.
