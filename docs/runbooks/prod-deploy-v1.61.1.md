# Prod deploy: v1.61.1 (RT7): the audit's truth — pinned acceptances, CI snapshot = prod, the 19 Oct 4G golden, all packs in CI

Committed BEFORE the run (D3). The OUTCOME is appended after the window. Dispatch `RT7_DISPATCH_audit_snapshot_and_accepted_list.md`;
rulings `RT7_RULING_1` (17 Oct) and `RT7_RULING_1A` (19 Oct: prod's 4G factor moved, the golden is refreshed for it).

## What ships

- **No migration** (alembic stays **0053**), **no dependency**, **no SPA rebuild**, **no `?v=` bump**. Python changes
  (the audit tool), so the service **restarts**: prod's **Admin → Costing audit** page reads the accepted list, the
  golden and the snapshot from the deployed code.
- **The accepted list pins its amounts** (`tools/costing_audit/accepted.py`, `compare.py`): every prod entry lists, per
  cell it accepts, the difference MES − Excel it accepted; a covered cell is ACCEPTED only at that amount ±R0.01 —
  otherwise a FLAG whose reason starts **`ACCEPTED_AMOUNT_CHANGED`** and names the pinned and actual amounts. Entries
  gain `mechanism:` (what the difference is) and `refs:` (what clears it); the prod list refuses an entry without
  amounts, mechanism, refs or `review_by` (all **30 Nov 2026**).
- **The prod list = 7 entries** (variant B, RULING_1 Q2): the ICECREAM 4.8 FLOOR probe limit; Burt's tapping formula slip
  (B-01, B-02); the FREEZER MEDIUM bracket (B-08); the EXPLOSIVE UP TO 2.7 alu plate (B-10); FREEZER MEDIUM's three
  hand edits as `mes_updated_ahead_of_burt` (FLOOR plywood E-01 + EPS E-02, ROOF EPS E-02, DRD hinges E-03). Eight old
  entries pruned one at a time with `audit reaccept` after each (H4) — every one covered 0 cells.
- **The CI snapshot = prod** (`mes_snapshot/all.json`, the build paste's read-only 15-body export) and the list's
  `pair:` records its sha256 (LF-normalised): `test_rt7_pins.py` fails if the two are not committed together.
- **The golden, regenerated for exactly the 4G change** (RULING_1A): RT2's corrected set rebuilt byte-for-byte from
  Burt's 21 Sep zip (and proven to reproduce the committed golden: 230 scenarios, 0 differences), then Burt's 19 Oct
  price list (`PRICE 2017 MARCH.xlsx`, sha256 `088f43dc…`) with the GRP's link cache resolved to it — the one cell it
  references that moved is **PU!C19, 4G FOAM R5 581 → R5 400**. Every changed golden line traces to PU!C19
  (`docs/audit/rt7_2026-10/golden/`).
- **CI:** all five packs on every PR (no path filter), on every push to `backport/v1.39-base`, and on demand; no
  `schedule` (it never fired off the default branch).
- **CI's snapshot loader (RULING_1B §1):** the snapshot's rows now win over anything a migration or a seed put in the
  CI database. Until RT7 the loader was ON CONFLICT DO NOTHING, so every CI run since v1.57.3 priced 4G with migration
  0046's seeded factor. A new step, `audit load-snapshot`, checks every row column for column before the packs
  (`docs/audit/rt7_2026-10/ci_loader/`). CI only: prod never loads a snapshot.
- **bom 3216 is a named post-correction edit (RULING_1B §2):** CHILLER MEDIUM / DRD DOOR FITTINGS / 2317 DOOR RUBBER,
  `… * 0`, B-07. The v1.58 test knows it by its exact expression, so any other drift still fails.
- **The reboot guard:** every RT7 kit's first line prints prod's boot time; a kit copied before the last boot, or never
  stamped by the copy line, refuses to run.
- **Tests only:** the flaky repair journey and the 14 other sites sharing its assumption wait for the calculator's init
  to finish (`_common.wait_calculator_ready`).

## Expected numbers (from the build paste, 19 Oct 15:15; proven on the mirror — `docs/audit/rt7_2026-10/mirror/MIRROR_PROOF.md`)

Prod's data as the build paste read it (19 Oct 15:15 SAST: prod `5e37b0a`, alembic 0053, the 4G factor exactly
`1.3170731707317074`). If prod's pricing moves before the window, these move with it: re-derive them first.

**Known since the paste (record in the OUTCOME; no re-derivation needed):** on 19 Oct, after the export, Michael put
MEAT HANGER LARGE's FRONT PU divisor back from **2.99 to 2.98** on prod (RULING_1B §4; 2.99 matched one quote, and
RT8's frozen edit removes that need). No pack covers MEAT, so none of the numbers below move, and there is no re-export.

**Window step 1 — All BEFORE** (the deployed v1.61.0: the old golden, the old list): the paste's own counts.

| pack | FLAG | ACCEPTED | PASS | SKIP | UNVERIFIABLE |
|---|---|---|---|---|---|
| chillers | 0 | 0 | 590 | 126 | — |
| freezers | 71 | 24 | 478 | 117 | — |
| icecream | 37 | 32 | 387 | 116 | 40 |
| explosive | 6 | 3 | 522 | 117 | 36 |
| **All (2 702)** | **114** | **59** | 1 977 | 476 | 76 |
| smoke (234) | 15 | 18 | 156 | 45 | — |

(114 = FREEZER MEDIUM's 48 hand edits − 4 of them that the 4G change now nets under 1 % + the 4G cells: 27 freezers,
37 icecream, 6 explosive — the old golden still prices 4G at R5 581.)

**Window step 4 — All AFTER** (v1.61.1: the refreshed golden, the pinned list): **0 FLAG**, PAGE = CLI.

| pack | FLAG | ACCEPTED | PASS | SKIP | UNVERIFIABLE |
|---|---|---|---|---|---|
| chillers | 0 | 0 | 590 | 126 | — |
| freezers | 0 | **72** | 501 | 117 | — |
| icecream | 0 | **40** | 416 | 116 | 40 |
| explosive | 0 | **3** | 528 | 117 | 36 |
| **All (2 702)** | **0** | **115** | 2 035 | 476 | 76 |
| smoke (234) | 0 | **33** | 156 | 45 | — |

ACCEPTED 115 = 52 before RT6's window − 0 pruned (the eight pruned entries covered no cell) + 15 (ICECREAM MEDIUM FLOOR
back under the probe-limit entry once the lamination returned to Burt's price) + 48 (FREEZER MEDIUM's three hand edits).

**Verify BEFORE the deploy fails on exactly 7** (the simulation's list): `HEAD`, `TAG_LOCAL`, `DESCRIBE`, `LIST` (the
v1.61.0 tool has no pinned list), `VERSION_LOCAL / _LAN / _CF` (v1.61.0). Everything else passes — the factor, the
autologin, the environment key, the SPA, the 46 probes × 3.

## The kits (committed, staged byte-exact from the merge commit by ONE script)

`bash ops/prod-rt7/mkstage_window.sh <out> <merge-sha>` (after the tag is on origin) stages three kits, each with
`lib/`, the place it must run (`icb-mes-prod`, `icb_platform @ 127.0.0.1:5432`, the HEADs it may see) and the reboot
guard:

| kit | runs | over |
|---|---|---|
| `icb-release-v1.61.1` | `release.sh preflight / verify / deploy` | v1.61.0 (and v1.61.1 after the deploy) |
| `icb-rt2-all` | `rt2_all.sh pre / post` | either |
| `icb-rt2-doors` | `rt2_doors.sh` | either |

Beside the tars: **`run_window_copy.ps1`** (one line on Windows: checks each tar's sha256, copies, unpacks, verifies
and **stamps** each kit on prod) and **`run_window_fetch.ps1`** (one line: every `out-*` folder back to Downloads).
Both print the identity line first — machine, prod's HEAD **and prod's boot time** — and refuse a wrong place.

## Sequence

**0. Michael picks the window.** About 30 minutes; the restart means a few seconds of outage.

**1. Merge, tag, stage (after RT7_RULING_2).** CI green on the PR's exact head; Michael squash-merges; the CA tags
`v1.61.1` on the squash commit and proves the tag object local = origin (D2); `mkstage_window.sh` →
`C:\Users\micge\Documents\icb-rt7-stage\window\`. **Copy (Michael, one line):**
`powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\micge\Documents\icb-rt7-stage\window\run_window_copy.ps1"`.
⚠ If prod reboots after the copy, every kit refuses (`staged … before this machine's last boot`): copy again.

**2. Preflight (read only, any time before the window).** `sudo bash /tmp/icb-release-v1.61.1/release.sh preflight` →
**`PREFLIGHT PASSED`**: alembic 0053, HEAD `5e37b0a`, no tracked modifications, autologin empty, `ICB_ENVIRONMENT=prod`,
the 4G factor exactly `1.3170731707317074`, SPA served = disk, `/health/version` = v1.61.0 on the three doors, all
46 probes as listed (v1.61.1 adds no route), PyYAML, the tag on origin, the backup directory, the deploy tooling.

**3. The window** (dispatch order; every line is one paste on the VM unless it says browser; each first line names
machine, database, HEAD and boot time).

| # | step | pass condition |
|---|---|---|
| 1 | Admin → Costing audit → **All**; when it finishes: `sudo bash /tmp/icb-rt2-all/rt2_all.sh pre` | PAGE = CLI. "Before" (the deployed v1.61.0 list + golden: the FREEZER MEDIUM cells and the 4G cells FLAG, as the build paste showed) |
| 2–3 | `sudo bash /tmp/icb-release-v1.61.1/release.sh deploy` | **`######## DEPLOYED`**: the checked backup (step 2 of the dispatch: `pg_restore -l` lists `alembic_version`, `admin_settings`, `trailer_types`, `bill_of_materials`, `materials`, `calculations`); no migration; restart; 4 workers, 0 tracebacks; the factor unchanged; **the deployed list loads strictly, `pair = snapshot`**; **`/health/version` = `{"version":"v1.61.1","environment":"prod"}` on 127.0.0.1, then LAN, then Cloudflare** (D4); no TEST banner; 46 probes × 3; the SPA byte-identical |
| 4 | **All** → `sudo bash /tmp/icb-rt2-all/rt2_all.sh post` | **0 FLAG**, the expected ACCEPTED counts above, **PAGE = CLI** |
| 5 | `sudo bash /tmp/icb-rt2-doors/rt2_doors.sh` | **SUMMARY: 14 OK** |
| 6 | Windows, one line: `run_window_fetch.ps1` | `######## DONE - tell the CA: …\Downloads\rt7-window-back-<ts>.tar` |

## Behaviour a user can notice

None for sales: no screen, price, quote or document changes. **Admins:** the Costing audit page reads the new list —
ACCEPTED cells carry their pinned amount; a moved amount shows as a red FLAG `ACCEPTED_AMOUNT_CHANGED`.

## Rollback (decided before the run)

- **The code:** back to `5e37b0a`: `sudo -u icb git -C /opt/icb-platform reset --hard 5e37b0a`, then
  `sudo systemctl restart icb-backend`; then `/health/version` = v1.61.0 on the three doors. No migration, no SPA, no
  data moved: nothing else to undo.
- **The full restore** (only if the above fails): `icb_platform_pre-v1.61.1_<ts>.dump`.

## Before the window, after the merge: Michael's :8000 (the post-merge procedure)

The CA fast-forwards the main clone (Michael's 235 local entries fingerprinted before and after, never stashed, reset
or overwritten); no SPA rebuild, no migration; the restart. **Click-through:** `http://127.0.0.1:8000/mes-app/` →
Admin → Costing audit → the page loads; **All** runs and shows the expected counts against dev's data (dev differs from
prod — it is Michael's workbench — so the counts are dev's; the point is that the page reads the pinned list).

## Simulation (WSL; the real kits)

Each sim runs the committed kit from the branch in a WSL namespace, with stubs for prod's commands, and removes its own
clones.

| sim | result | its refusals |
|---|---|---|
| `ops/prod-release-v1.61.1/sim/run_all.sh` (the release kit, `795f441`; the kits are unchanged since) | **14 / 14** | the factor not exact; no tag on origin; prod moved; a traceback after the restart; a backup with no data; pg_dump failing; Cloudflare still serving v1.61.0; autologin set; no environment key; the wrong machine; a kit staged before the last boot; an unstamped kit. Plus a failed deploy that a second run RESUMEs (SPA rebuilt by the resume; verify 0) |
| `ops/prod-rt7/sim/run_window_sim.sh` (the window stager + the copy and fetch lines) | **16 / 16** | an unstamped kit; a kit staged before the boot |
| `ops/prod-rt7/sim/run_export_sim.sh` (the 19 Oct build-export kit) | **20 / 20** | the factor not exact; the wrong machine, database or HEAD; a kit staged before the boot; an unstamped kit; not root; the wrong alembic; a tampered stage; an env file without SESSION_SECRET; an email in the export (the no-people gate; the refused export removed) |
| `ops/prod-rt7/sim/run_discovery_sim.sh` (the 16 Oct discovery kit) | **16 / 16** | the wrong machine, database or HEAD; a kit staged before the boot; an unstamped kit; not root; the wrong alembic; a tampered stage; an env file without SESSION_SECRET (the first prod paste's STOP); an email in the export |

The happy path reads: preflight PASSED → verify-before fails on exactly 7 → DEPLOYED → verify 0 → a second deploy says
ALREADY DEPLOYED and verifies; the kit's pg_dump runs at alembic 0053; no npm build on a fresh deploy.

## OUTCOME

**20 Oct 2026, 13:03–13:25 SAST: prod = v1.61.1 `5511355`, alembic 0053. 0 FLAG / 115 ACCEPTED, smoke 0 / 33,
PAGE = CLI. Nothing priced moved.** Evidence: `docs/audit/rt7_2026-10/prod/window_20261020/` (the kits' out folders,
`window_pastes.txt`, `cells_window.txt`). The window tar is `Downloads\rt7-window-back-20261020-132023.tar`, sha256
`92e4b07c…`, 12 564 480 B.

**Before the window:**
- **Merge:** #220 squash `5511355` (09:00 UTC), parent `9017c0b`, tree = the tested `cce0fb0`, 7 / 7 checks green on
  it.
- **Tag:** `v1.61.1` = tag object `771b032`, local = origin, peeling to `5511355`.
- **:8000:** the main clone was fast-forwarded `9017c0b → 5511355`. Michael's 235 local entries are byte-identical
  before and after (digest d64dc329). `/health/version` reads `{"version":"v1.61.1","environment":"unset"}`.
  Admin → Costing audit run #12 (dev list, dev data): pass 1584 · flag 54 · accepted 512 · unverifiable 76.
  - These are dev's own numbers. :8000 audits the database `icb` with the dev list, so RULING_2 G2's "0 / 115" and the
    mechanism / pinned line could not appear there.
  - They appeared on prod in step 5a.
- **Kits:** staged from `5511355` (release `d48801dd`, all `8f2e629c`, doors `2960d270`).

| # | step | result |
|---|---|---|
| 0 | copy (13:03:43) | 3 kits verified and stamped; prod boot 2026-10-11 08:02:53 (no reboot since RT6) |
| 1 | preflight (13:05:57) | **PASSED**: the factor exactly `1.3170731707317074`, v1.61.0 on the three doors, 46 probes × 3, the tag on origin |
| 2 | verify, before | **8 failed, not 7.** The expected 7 (`HEAD`, `TAG_LOCAL`, `DESCRIBE`, `LIST`, `VERSION_*` × 3) plus `TRACEBACKS = 12`. A read-only listing (13:08:28) showed all 12 are 4 `starlette.requests.ClientDisconnect` (dropped browser requests, 3 traceback lines each) under v1.61.0 on 19 Oct, 11:14:05 × 2 and 14:13:25 × 2. Cleared as pre-existing: the deploy counts from its own restart |
| 3 | All before (13:10) | page #48 PASS 1977 / **FLAG 114 / ACCEPTED 59** / UNVERIFIABLE 76; the CLI per pack = the table above, smoke 15 / 18; **PAGE = CLI** 2 702 / 2 702; = the 19 Oct build paste **cell for cell, 2 936 / 2 936** |
| 4 | deploy (13:12:34–13:13:25) | **DEPLOYED `5e37b0a → 5511355`**. Backup `icb_platform_pre-v1.61.1_20261020-131234.dump`, 3 807 433 B, sha256 `c165f72d…`, checked. No migration; restart 13:12:40 (pid 34561 → 76017), 4 workers, 0 tracebacks. The factor unchanged; `LIST = 7 336dd05e… pair=snapshot`; `{"version":"v1.61.1","environment":"prod"}` on 127.0.0.1, then LAN, then Cloudflare; no TEST bar; 46 probes × 3; the SPA byte-identical. The fetch printed `! [rejected] v1.47.1 (would clobber existing tag)`: prod's own old tag, left alone (standing rule) |
| 5 | All after (13:14) | page #49 PASS 2035 / **FLAG 0 / ACCEPTED 115** / UNVERIFIABLE 76, golden `ed4d57bc`; the CLI per pack = the table above, smoke **0 / 33**; **PAGE = CLI** 2 702 / 2 702; = the mirror's final run **cell for cell, 2 936 / 2 936**. A FREEZER MEDIUM DRD DOOR FITTINGS cell reads `… review by 2026-11-30 · mes_updated_ahead_of_burt · pinned at -293,46 · clears with E-03` |
| 6 | doors (13:19:10) | **SUMMARY: 14 OK**; no exceptions |
| 7 | verify, after (13:19:36) | **0 failed** |
| 8 | fetch (13:20:23) | the tar above |
| close | prod `/tmp` (13:24–13:25) | `icb-rt7-discovery/`, `icb-rt7-discovery.tar`, `icb-rt7-export/` and `icb-rt7-export.tar` (with the out folders and tars inside): **gone, read back**. The three window kits and their tars stay: not named by the ruling, their outputs fetched, and a reboot clears `/tmp` |

**Recorded (RT7_RULING_2, the close):**
- **The 4G factor:** set by hand on prod by Michael on 19 Oct, by SQL, value only:
  - `'1.361219512195122'` (F2, as the 16 Oct export read it) → `'1.3170731707317074'` (5400 / 4100);
  - its `updated_at` still reads `2026-10-01 12:44:36`;
  - no backup was taken before that SQL, and the BA's F3 kit was not run (RT7_RULING_1A).
- **bom 3216** (CHILLER MEDIUM / DRD DOOR FITTINGS / 2317 DOOR RUBBER):
  - its formula ends `* 0`, a hand edit on prod after 2 Oct (seen 16 Oct);
  - intended (Michael, 19 Oct): Burt's sheet types that total as 0. B-07;
  - named by its exact expression in `test_v1_58`'s `LATER_PROD_EDITS`.
- **MEAT HANGER LARGE FRONT PU, bom 5842:**
  - `/2.99` in the 19 Oct export: on purpose, to match a quote (BA);
  - Michael put it back to `/2.98` on prod on 19 Oct, after the export. RT7 did not read that back: no pack covers MEAT,
    and there is no re-export;
  - the CI snapshot keeps `/2.99` until the next export.
- **The three extra bodies, against the 2 Oct snapshot** (no pack covers them):
  - **MEAT HANGER LARGE (12):** SIDES plywood 4MM PF → 6MM BIRCH (same price R171.14); ROOF row 5913 conditioned on
    `6MM PF PLYWOOD`, plus a new 4MM PF PLYWOOD row (11223); FRONT 5842 `/2.99` (above); FRONT 5846's formula rewritten
    (panel deductions).
  - **MEAT HANGER SMALL-MEDIUM (36):** the same ROOF radio (6221 conditioned, plus a new 11224).
  - **RHINORANGE (15):** the 256.50 `unit_price_override` removed on FRONT 1794, DRD 1805 and SIDES 1827; FLOOR
    1854 / 1855 lost a `*2`.
- **CI's snapshot loader (RULING_1B):**
  - every CI run since v1.57.3 had priced 4G with migration 0046's seeded factor;
  - fixed before the merge: the snapshot's rows win, and the fidelity check runs before the packs
    (`docs/audit/rt7_2026-10/ci_loader/`).
- **Q2** (body 51's seven dangling FKs, pinned): its own PR after the window (Michael's choice),
  icecold-bodies/icb-platform#222.
- **The 16 Oct near-miss:** a missing ssh stub in a CA runner test let the real ssh reach prod: a read-only probe plus a
  failed tar, nothing written. Disclosed in RT7_RETURN_1 and accepted. Since then, stub tests point at 127.0.0.9 and
  assert the stubs resolve first.
- **20 Oct, the shared local `icb_test` (disclosure):**
  - while checking Q2, the CA ran `audit load-snapshot` against the shared local `icb_test`. It **commits**: the 15
    snapshot bodies now carry the 19 Oct prod data;
  - the four seeded rows that share a snapshot row's name now sit under the snapshot's ids, with their referrers
    re-pointed: the FREEZER group, `freezer_quote`, Waste and the 4G factor;
  - stale rows under those bodies are gone, and the sequences are forward;
  - RT8's side-port server (:8013) was running on `icb_test` at the time;
  - the state is CI's after-load state and the full suite is built for it, but it cannot be undone exactly: the CLI keeps
    no undo log, and the 19 Oct dump would wipe newer work;
  - the lesson: `load-snapshot` and `run --mes-snapshot` are for CI and scratch databases, never a shared one.
- **Queued (RULING_2):**
  - no side-port server on `icb_test` while a suite runs on it;
  - body 51's clean-up (clears the seven);
  - from earlier rulings: the Manni gap job, the old-stylesheet clean-up, the role review, the Trailer Designer console
    error, the duplicate route; the calculator's init-restore race → RT8.
