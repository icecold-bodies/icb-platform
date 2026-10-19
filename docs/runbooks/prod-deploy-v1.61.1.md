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

(appended after the window)
