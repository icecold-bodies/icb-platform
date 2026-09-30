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

> **Q-A answered YES (Michael, 30 Sep):** the 29 Sep R4 095 re-pricing was deliberate (Burt's 21 Sep 32D price).
> Per the dispatch, the default B below **stops**. It is kept as the record `manifest_b_default.yaml`, and the data kit
> never stages it. The formula-only variant is proposed to the BA (RT1_RETURN_1a). Only a B the BA rules in is
> committed as `manifest_b.yaml`, the one file the data kit stages.

The five single-rear-door PU lines on prod today, priced through the engine at thickness 0.06
(`verify_b_before.txt`):

| line | body | today | Burt (row 46 / F1, PU!C17) |
|---|---|---:|---:|
| 5851 | MEAT HANGER LARGE | `1.22*2.44*2` × R4 095 = **R24 379.99** | R1 463.01 at R4 100 · R1 461.23 at R4 095 |
| 6159 | MEAT HANGER SMALL-MEDIUM | **R24 379.99** | same |
| 5585 | ICECREAM BODY MEDIUM | F1 × R4 095 = R1 461.23 | same |
| 2415 | FREEZER MEDIUM | F1 × R4 095 = R1 461.23 | same |
| 3576 | FREEZER 2.3 METER | F1 × R4 095 = R1 461.23 | same |

**`manifest_b_default.yaml` (the dispatch default for Q-A = NO — stopped; proved as `manifest_b.yaml`, sha
`28b15def…`), 7 entries on 5 lines:**
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

## 5a. Manifest M — the 11 MEAT HANGER PU lines (RT1 ruling 1 §1, option c+), 30 Sep evening

**The defect** (on the mirror = prod's 1b data): every MEAT HANGER PU line kept a sheet-count formula and no own
price. Since 29 Sep the shared PU materials hold R4 095 per m³, so the lines price sheets at the m³ price
(`verify_m_before.txt`, the known hit: MEAT HANGER LARGE at 6.7 m, PU, DRD **R318 538.58**).

**The fix** (`../manifest_m.yaml`, sha256 `59d37b08…`, 11 `formula_expression` entries, generated by
`../make_manifest_m.py`):
- The new formulas are **Michael's own 29 Sep freezer formulas, character for character** (FREEZER MEDIUM 2406 /
  2441 / 2415 / 2463 / 2473 / 2481). The generator refuses if they are not exactly Burt's shape.
- They are Burt's MEAT BODY / SMALL MEAT BODY UP TO 5,2 rows 32 / 83 / 46 / 116 / 132 / 148 term for term, `/2.98`.
- No own price is set.
- 6229 is out.

- Dry-run 11 to apply, 0 mismatches → apply (0 history rows: formulas only) → a second dry-run finds nothing.
- **The engine against Burt** (`verify_m_after.txt`, `../verify_manifest_m.py`). Cases: both MEAT HANGERs at 3
  lengths (LARGE 5.3 / 6.7 / 8.4, SMALL-MEDIUM 2.7 / 5.2 / 5.8), DRD and SRD, EPS and PU, 32D and 4G. **ALL OK:**
  - every M line = the expected value to the cent;
  - Burt's one 32D line (SRD) = MES at 32D to the cent;
  - every Burt 4G panel = MES at 32D × the stored 4G factor = MES at 4G, to the cent;
  - EPS quotes cost no PU line.
- **Negative control:**
  - after M, the five packs are **3 473 of 3 473 cells identical** to after A (`cmp_afterA_vs_afterM.txt`) — no other
    body's cell moves;
  - row level: exactly 136 rows differ from the snapshot (A's 120 + M's 11 + the 5 known).
- **Revert byte-exact** (back to A's 125), then re-applied.

**MEAT HANGER LARGE, default size (6.7 × 2.6 × 2.6), Body Template thicknesses (FRONT / SIDES / DRD PU 0.062,
ROOF / FLOOR PU 0.1), PU panels, DRD:**

| | FRONT | DRD | SIDES (×2) | ROOF | FLOOR | **total** |
|---|---:|---:|---:|---:|---:|---:|
| before M | 24 379.99 | 24 379.99 | 134 889.30 | 67 444.65 | 67 444.65 | **318 538.58** |
| after M, quote at 32D (default toggle) | 1 509.94 | 1 509.94 | 8 354.16 | 6 737.22 | 6 737.22 | **24 848.48** |
| after M, quote at 4G | 1 988.70 | 1 988.70 | 11 003.03 | 8 873.42 | 8 873.42 | **32 727.27** |
| Burt's MEAT BODY at his latest prices (4G panels) | 2 050.98 | 2 057.86 | 11 385.73 | 9 182.04 | 9 182.04 | **33 858.65** |

**Reported, not changed:**
- **Burt prices the MEAT HANGER panels at 4G** (PU!C19), and a MES quote defaults to 32D. At the 32D toggle a MEAT
  HANGER PU quote is ≈ 26.6 % below Burt's sheet. At 4G it is ≈ 3.3 % below: the stored 4G factor **1.31707**
  (= 5400 / 4100) against Burt's latest **5581 / 4095 = 1.36288**. A price-update job owns the setting.
- **The one structural difference:** with the toggle on 4G, MES also moves the SRD door's PU to 4G (R1 988.70 at
  0.062), while Burt keeps it at 32D (R1 509.94).
- **MEAT BODY!G32 (FRONT PU) divides by 2.99**; every other row and the small sheet use 2.98. The ruling fixes
  `/2.98`, which puts MES +0.34 % over Burt's front row.
- **6229** (SMALL-MEDIUM FLOOR PU, own R446.02, out of M) **matches Burt in no mode.** R446.02 = 2.9768 × 0.076 ×
  5875 / 2.98, the v1.51 4G sheet price at a fixed 76 mm. So a 32D quote prices it at an old 4G rate (at 2.7 m:
  R2 992.79 against Burt's R2 086.04 at 32D / R2 843.03 at 4G). A 4G quote applies 4G twice (R3 941.73). And it
  ignores the thickness.

## 5. State left behind

The mirror is left at **A + M** (the default B was reverted after Q-A = YES; the formula-only B was superseded by M):
prod's state after the window and Manifest M. In that state every single-rear-door PU line prices R1 461.23 at T = 0.06
(Burt's formula at R4 095), the two MEAT HANGERs included. Journals: `journals/` (the apply / revert records of every
step above). Reports: `reports/` (md; the JSON stay local).
