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
- **The reboot guard:** every RT7 kit's first line prints prod's boot time; a kit copied before the last boot, or never
  stamped by the copy line, refuses to run.
- **Tests only:** the flaky repair journey and the 14 other sites sharing its assumption wait for the calculator's init
  to finish (`_common.wait_calculator_ready`).

## Expected numbers (re-derived from the build paste; written here BEFORE the window)

__FROM_THE_BUILD_PASTE__ — the All after the deploy: **0 FLAG**, ACCEPTED per pack, page = CLI. Filled in from the
build paste's reference run against the refreshed golden, and proven on the mirror loaded from the new snapshot.

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

__FROM_THE_BUILD__ — `ops/prod-rt7/sim/run_export_sim.sh` (20/20), `ops/prod-rt7/sim/run_discovery_sim.sh` (16/16),
the release sim.

## OUTCOME

(appended after the window)
