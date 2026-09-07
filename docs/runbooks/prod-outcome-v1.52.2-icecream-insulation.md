# OUTCOME — v1.52.2 icecream insulation corrections (7 Sep 2026)

Data-only work on `icb_platform` (prod) and dev, closing out the icecream-body
questions Michael raised while quoting Motus Isuzu Zambezi. **No deploy was
required** — every tool here runs from `/tmp` on the VM against the database.

Merged: **`43718f5`** (#179) on `backport/v1.39-base`, CI green both jobs
(ubuntu 10m24s, windows 10m42s) before merge.

## What was wrong, and why

Three separate problems surfaced from one symptom (a PU line quoting half):

1. **The formula representation.** Burt's PU rows compute
   `H = G x F x I x C` where `G` embeds the raw sheet price, the 1.22x2.44
   sheet area and the insulation thickness. MES lines carried a per-m² rate
   instead. Re-anchored on the raw **R4100** price with formulas mirroring
   Burt's rows term-for-term (v1.52.1 lane, `tools/icecream_pu_4100.py`).
2. **The thickness values had drifted.** `calculator.js` rewrites the template's
   stored thickness on every door / EPS-PU toggle (`PUT /api/bom/{id}`), with
   `DEFAULT_REAR_DOOR_THICKNESS_M = 0.06` as its fallback. That is how the
   Medium body ended up at 0.06 on both rear doors, and later at 0.12 on
   ROOF/FLOOR where the sheet says 0.145.
3. **Edit mode never showed a correction.** `editBodyVariable`'s blur handler
   PUT the new thickness and called `runCalc()` but never mirrored it into
   `editBodyVarOverrides`; that pin rides every recompute and the server
   replays it over the template, so the totals kept the SAVED figures. Fixed
   in v1.52.1 (`e9dd6da`), deployed 7 Sep 16:42.

## Final state — verified by the calculation engine, not by inspection

`tools/icecream_pu_4100.py --verify` on prod: **`verify: ALL OK`** — all 15 PU
lines across the three icecream bodies reproduce Burt's `H` to the cent.

| Body | FRONT | rear door | SIDES (x2) | ROOF | FLOOR |
|---|---|---|---|---|---|
| SMALL @3.2 | 2 438,35 | DRD 2 438,35 | 6 495,62 | 3 247,81 | 3 247,81 |
| MEDIUM @5.3 | 2 926,03 | DRD 2 926,03 | 12 831,34 | 7 752,27 | 7 752,27 |
| LARGE @6.7 | 2 926,03 | DRD 2 926,03 | 16 189,08 | 8 431,81 | 6 745,45 |

Floor plywood additionally now shows the **raw PRICE-list value** on the
material (336 / 665 / 798) with Burt's `/2.98` sheet-area division moved into
the line formula — cost-invariant by identity, and it completed the September
price on the Medium and Large floors, which had been missed as unmatched rows.

## Audit trail — one gap, deliberately recorded

| Change | Journal |
|---|---|
| PU re-anchor (15 lines, 3 bodies) | `icecream-pu/` on the VM + committed |
| Floor plywood raw price (4 lines) | `floor-ply/` on the VM + committed |
| Rear-door thickness (Medium) | `reardoor/reardoor_thickness_journal_20260907T141513Z.json` |
| **ROOF/FLOOR 0.12 → 0.145 (Medium)** | **none — see below** |

The `--all-pairs` run on prod (17:28) reported **0 deltas / "nothing to apply"**
and wrote no journal: the two values were already 0.145 by the time it ran,
having been set by hand in the calculator UI. The end state is correct and
engine-verified, but that particular correction has **no journal and no audit
trail** — `variable_value` changes are not recorded in `price_history`,
`bom_override_history`, or anywhere else. Noted so nobody hunts for a revert
that does not exist. The tool now acts as the guard: it detects this drift
immediately and repairs it journalled.

## Verification discipline applied (and one failure of it)

* The `--all-pairs` sync was proved **both ways** before being trusted: a
  negative control (0 deltas while dev was correct), then dev deliberately set
  to prod's wrong 0.12 values to prove **detection**, repair, and a clean second
  pass. An empty check result proves nothing until the check has caught a known
  hit.
* `icecream_pu_4100.py`'s SPEC listed **SRD** as the Medium body's rear door
  (true on the 4 Sep sheet). Burt's 7 Sep revision moved it to **DRD**, so the
  verifier reported a permanent false MISMATCH on a row that is correctly zero
  under the rear-door invariant — and it was briefly escalated as a "live
  regression" before being traced. Corrected in #179; all 15 lines now pass.
* ⚠ **openpyxl reads Excel's saved cached results, which in this workbook are
  stale against its own input cells.** Row 78 read as inactive while Michael's
  screen (Excel recalculates on open) showed it live at R2 926,03. Read the
  **C/D input cells** for truth, never the cached `G`/`H`/`I`.

## Open items

* **22 unmatched + 8 review rows** from the September import — prod lines whose
  names differ from Burt's sheet, still on pre-September prices. Itemised under
  `docs/audit/september_price_update/prod/`; needs Burt's naming decisions.
* **The drift mechanism itself.** Any toggle still rewrites the template
  thickness with a 60 mm fallback — this is why the Medium body drifted twice
  in one day. Worth a design decision (should the template be authoritative, or
  the costing?) rather than repeated corrections.
