# RT1 prod-mirror proof — Manifests A and B (30 Sep 2026)

**The mirror:** the local scratch database `icb_prodmirror` (owner `icb_app`). It was reset to an empty,
CI-shaped database: the three app schemas were dropped, `icb_costings` and `icb_mes` recreated as
`deploy/postgres/init.sql` does, then `alembic upgrade head` (0049) with the **v1.59.2 code**. It was loaded with the
committed CI loader (`load_snapshot`) from the **RT1 1b prod snapshot**
(`../prod/1b_20260930-162834/`: `all.json` sha256 `43937969…`, `meat_hangers.json` `276befca…`; prod
`icb_platform`, alembic 0049, code `de74796`, 30 Sep 16:28 SAST). Then `costings.pu_foam_4g_factor` was set to prod's
1.3171; migration 0046 seeds 1.3631, and the loader never overwrites. Reproduce: `../load_mirror.py`.

## 1. The mirror is prod, and v1.59.2 prices it as v1.59.0 does

| check | result |
|---|---|
| every snapshot row vs the mirror, column by column (`../mirror_vs_snapshot.py`) | **4 537 of 4 542 identical**. The 5 others are the known ones: 4 orphan BOM rows whose FK targets lie outside the snapshot (trailer 51, group 21, subgroup 59, written NULL, exactly as in CI) and `admin_settings` id 10 (the 4G row, present under the migration's own id, value set to prod's) |
| the five packs `--env prod` on the mirror (**v1.59.2 engine**) vs prod's 1b reference run (**v1.59.0 engine**), cell by cell (`../compare_reports.py`: status, both totals to the cent, accepted reason) | **3 473 of 3 473 cells identical** (`cmp_prod_vs_mirror_before.txt`) |

So the code release changes nothing an audit can see. This is the offline form of window step 2c ("No change since").

## 2. Manifest A (120 REAR FRAME & FLOOR PLATE rules, 14 bodies)

- **Dry-run:** 120 to apply, 0 already applied, **0 guard mismatches**.
- **Apply:** 120 changes on 120 lines, one transaction; a second dry-run finds nothing (manifest sha `2952a935…`,
  the committed LF blob prod will stage).
- **Known hit for the mirror check:** after A it reports 125 rows not identical (the 120 rules + the 5 known).
- **Revert byte-exact:** after the revert it is back to the same 4 537 / 5.

**The audit after A** (`cmp_before_vs_afterA.txt`):

| cells | result |
|---|---|
| the SRD REAR FRAME & FLOOR PLATE cells (`srd` / `srd_pu`) | **57 of 57: ACCEPTED (entry #5, EXTRA_IN_MES, R2 447–R10 502) → SKIP** — smoke 3, chillers 28, freezers 9, icecream 8, explosive 9 |
| every other cell | **3 416 of 3 416 identical to the cent** |

**SKIP, not PASS** (a correction to the dispatch's expectation). With every line excluded, the section drops out of MES's
section totals, and Burt carries R0 on a single rear door. The audit's rule for "both sides zero" is SKIP ("the rear
door that is not fitted", `compare.py:8`). So the difference entry #5 accepted is gone; nothing is left to compare.

**The engine, all 14 bodies incl. both MEAT HANGERs** (`verify_rule_on_mirror.txt`, `../../srd_rear_frame_2026-09/verify_rule_on_db.py`):
**28 of 28 OK**. Each body is quoted twice:
- **DRD:** REAR FRAME priced, 0 lines excluded.
- **SRD:** REAR FRAME R0, every line excluded **by condition** (`excluded_by=condition`, so the v1.59.1+ calculator
  shows NOT SELECTED). The reason reads `SRD PU = N`; on CHILLER LARGE it reads `SRD = N` (7233).

## 3. Manifest B (built from the 1b snapshot: guards = prod as it is now)

The five single-rear-door PU lines on prod today, priced through the engine at thickness 0.06
(`verify_b_before.txt`):

| line | body | today | Burt (row 46 / F1, PU!C17) |
|---|---|---:|---:|
| 5851 | MEAT HANGER LARGE | `1.22*2.44*2` × R4 095 = **R24 379.99** | R1 463.01 at R4 100 · R1 461.23 at R4 095 |
| 6159 | MEAT HANGER SMALL-MEDIUM | **R24 379.99** | same |
| 5585 | ICECREAM BODY MEDIUM | F1 × R4 095 = R1 461.23 | same |
| 2415 | FREEZER MEDIUM | F1 × R4 095 = R1 461.23 | same |
| 3576 | FREEZER 2.3 METER | F1 × R4 095 = R1 461.23 | same |

**`manifest_b.yaml` (the dispatch default, Q-A = NO), 7 entries on 5 lines:**
- **The fix:** 5851 / 6159 get the F1 formula and all five get an own R4 100.
- **Apply:** dry-run 7 to apply, 0 mismatches → apply (5 `bom_override_history` rows) → a second dry-run finds nothing.
- **Engine = Burt to the cent** on every line: R1 463.01 at 0.06, R1 950.68 at 0.08. A double-door quote never
  costs the line (`verify_b_after.txt`).
- **Audit** (`cmp_afterA_vs_afterB.txt`): **12 cells move, +R1.78 each**, status unchanged — the SRD cells that price
  2415 / 3576 / 5585 (FREEZER 2.3 ×2, FREEZER MEDIUM ×4, ICECREAM MEDIUM ×3 + smoke ×3). Every other cell, 3 452,
  identical to the cent. The MEAT HANGERs are in no pack; the engine proof covers them.

**`manifest_b_formula_only.yaml` (the Q-A = YES variant, for the BA), 2 entries:**
- **The fix:** only the two MEAT HANGER formulas; no price is set anywhere.
- **Apply:** dry-run 2 to apply → apply (0 history rows) → a second dry-run finds nothing.
- **Engine:** every line = Burt's formula at the material's R4 095 (Burt's 21 Sep list): R1 461.23 at 0.06,
  R1 948.30 at 0.08 (`verify_b_formula_only.txt`). The MEAT HANGERs drop from R24 379.99 to R1 461.23, the same as
  every other F1 PU line on prod.
- **Audit:** 3 473 of 3 473 cells identical to after A (`cmp_afterA_vs_afterBformula.txt`).

**Rollback, in the kit's order:**
- Revert B (5 lines, 5 history rows deleted), then revert A (120 lines).
- The mirror is back at the loaded snapshot: 4 537 of 4 542, the same 5 known, `bom_override_history` empty.
  **Byte-exact**, `price_updated_at` included.

## 4. The prune of entry #5, rehearsed (H4; `accepted_differences.prod.pruned5.yaml` = the prod list minus #5)

`audit reaccept --accepted <pruned list>` on the saved mirror reports:
- **After A + B: all five packs exit 0.** Entry #5 is no longer needed.
- **Before A: exactly the 57 SRD REAR FRAME cells turn red** (PRESENCE: chillers 28, explosive 9, freezers 9, icecream
  8, smoke 3; exit 1). The entry was load-bearing before A — the known hit a prune needs.

## 5. State left behind

The mirror is left at **A + B (default)** applied — prod's state after the window under the dispatch default. Journals:
`journals/` (the apply/revert records of every step above). Reports: `reports/` (md; the JSON stay local).
