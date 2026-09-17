# BA feedback — CA session 4–7 Sep 2026: September price update, icecream insulation, edit-mode recalc fix

**Lanes:** `feat/v1.52-september-prices` (#174), `fix/v1.52.1-pairing-shift` (#175),
`fix/v1.52.2-icecream-insulation` (#179) — all squash-merged to `backport/v1.39-base`.

**Prod deploys by this session:** **4 Sep 08:42 SAST at `cd763c8`** (v1.52, migration `0047`) and
**7 Sep 16:42 SAST at `e9dd6da`** (v1.52.1, no migration). Everything else in this lane was
data-only work run against the prod database. **No release tag cut — BA-coordinator's call.**

> **Scope of this document.** Only the work done in this CA session. v1.53 (#176–#178, #180–#184),
> v1.53.1 (#186), capture-for-user (#187), v1.54 (#188), v1.55 (#189) and v1.56 (#190) were built
> by other sessions — see §7. Prod has since moved on to `6b77d52` (16 Sep) through those lanes;
> the fixes below remain present on base (re-checked 17 Sep).

---

## At a glance

| | |
|---|---|
| **Enhancements** | September 2026 price + description import (22 bodies, 410 prod lines) · "Updated Sept 2026" line badge · 4G foam ratio updated · icecream PU and plywood re-costed to Burt's exact sheet method · reusable, journaled data-correction tools |
| **Bugs fixed** | Import pairing shift (lines received a neighbouring section's values) · edit-mode thickness change never reaching the totals · tooling defects that silently skipped verification |
| **Data corrected on prod** | September prices · variant-named skins renamed to Burt's names · all 15 icecream PU lines · icecream floor plywood · Medium body rear-door, roof and floor insulation thickness |
| **Verified** | All 15 icecream PU lines reproduce Burt's sheet to the cent on prod (engine check, not inspection) |
| **Needs a decision** | 4 questions for Burt (email drafted) · double-apply guard has **lapsed** · insulation-thickness drift mechanism |

---

## 1. Enhancements shipped

### 1.1 September 2026 price + description update (#174, `cd763c8`)

Burt's September reissue of the costing workbook and price list, loaded against the BA's row-level
manifest.

- **Two independent diffs had to agree before anything imported.** A second workbook differ was
  built from scratch and reconciled against the BA manifest: **919 rows, clean** (513 price / 213
  description / 462 highlighted), row-, flag- and value-exact.
- **Scope enforced in code, not by discipline.** The five Manni sheets and `Sheet1` are *refused*
  even if present in the input (Michael's ruling); `AELER PANELS` has no MES body and falls away.
  22 sheets map to MES bodies.
- **Safe to apply and to undo.** Dry-run by default; one transaction; every write journaled;
  a `--revert` proven **byte-exact** on dev (all five written tables hash-identical after
  apply → revert) and a re-apply proven value-identical.
- **Prod:** **410 line actions** applied. The prod plan differed from dev's (410 vs 431 actions,
  22 vs 1 unmatched) because prod holds different line names — analysed row by row before the
  go, not assumed.
- **Impact** (dev, costed through the real calculation engine before/after — no impact report
  was run on prod): most bodies moved **down 1–9 %**. **Chester Spec Meat Body rose 22.5 %** — it
  had been *under-quoting* on stale foam prices, and September corrected it.

### 1.2 "Updated Sept 2026" badge

A green marker on every line the import changed, in both calculators, so sales can see what moved.
It clears itself 30 days after the update and is always visible — it does not depend on the Tips
checkbox. Backed by migration `0047` (`bill_of_materials.price_updated_at`).

### 1.3 4G foam ratio updated in the same apply

September moved both foam sheet prices (32D R4 310 → R4 100; 4G R5 875 → R5 400), so the 4G
multiplier moved with them: **1.36311 → 1.31707**. Applied in the same transaction on dev and prod.

### 1.4 Icecream bodies re-costed to Burt's exact sheet method

Prompted by Michael's own analysis of how Burt's sheet builds its foam totals.

- **PU foam — all 15 lines on Small / Medium / Large.** Burt prices foam as *sheet price ×
  sheet volume ÷ nominal area × sheets needed*. MES lines now carry the raw **R4 100** sheet price
  with formulas that mirror his rows term for term — length-driven for sides, roof and floor; a
  fixed two sheets for front and rear doors. This also removed formulas on the Large body that had
  the length hard-coded and would not have scaled.
- **Floor plywood.** The Materials table now shows the **raw price-list value** (R336 / R665 /
  R798) instead of a pre-divided figure, with Burt's ÷2.98 moved into the line formula. Line costs
  are unchanged by construction — and it completed September pricing on the Medium and Large
  floors, which had been missed.

**Verified on prod through the calculation engine — every line equals Burt's sheet to the cent:**

| Body | Front | Rear door | Sides (×2) | Roof | Floor |
|---|---:|---:|---:|---:|---:|
| Small @ 3,2 m | 2 438,35 | 2 438,35 | 6 495,62 | 3 247,81 | 3 247,81 |
| Medium @ 5,3 m | 2 926,03 | 2 926,03 | 12 831,34 | 7 752,27 | 7 752,27 |
| Large @ 6,7 m | 2 926,03 | 2 926,03 | 16 189,08 | 8 431,81 | 6 745,45 |

### 1.5 Reusable data-correction tools

All dry-run by default, journaled, revertible, and idempotent (a second run finds nothing), in
`backend/tools/`:

| Tool | Purpose |
|---|---|
| `september_price_import.py` | the September import |
| `diff_grp_costings.py` | independent workbook differ used for the reconciliation |
| `september_impact_report.py` | before/after body totals through the real engine |
| `september_fixup_pairing.py` | re-reconciles lines by section after the pairing shift (§2.1) |
| `icecream_pu_4100.py` | PU re-anchor + a `--verify` mode that checks every line against Burt |
| `icecream_floor_ply_raw_price.py` | raw plywood prices with ÷2.98 in the formula |
| `icecream_reardoor_thickness.py` | syncs insulation thickness to the sheet (`--all-pairs` for every panel) |

---

## 2. Bugs found and fixed

### 2.1 Import pairing shift — lines received a neighbouring section's values (#175)

**Found by Michael** on prod: Freezer Large, 2,3 m and Medium front skins had not updated.

- **Cause.** On prod several front skins carry legacy names (*EXT GRP SKIN 2\*300 GLOSS CRYSTEX
  V2*). That left some groups with fewer matching lines than sheet rows, and the matcher then
  paired rows onto lines *in order* — shifting every pairing one section down. Dev has no such
  names, so every dev proof passed.
- **Damage on prod.** 1 real price error (Freezer Medium sides plywood at R86,58 instead of
  R68,79), 3 lines with a neighbour's description, ~21 variant-named lines not updated at all.
  Nothing else was affected.
- **Fix.** At source: the matcher now pairs strictly by section and leaves anything ambiguous
  unmatched (regression test reproduces the Freezer Medium case). On prod: the fixup tool
  corrected prices, then — per Michael's ruling that names must match Burt's sheet exactly —
  renamed the variant lines. Final recheck: **0 outstanding**.

### 2.2 Changing an insulation thickness while editing a saved costing did not update the totals (#175)

**Reported by Michael.** Deployed to prod 7 Sep.

- **Cause.** When a saved costing is opened for editing, the system holds its saved thicknesses so
  the quote reproduces faithfully. Typing a new thickness saved it, and the costing *did*
  recalculate — but using the held value, so the totals never moved. The same fault had been
  fixed for the EPS/PU toggle (v1.42.1) and for Excel paste, but never for typing a value in.
- **Fix.** A typed thickness now replaces the held value before recalculating, including when the
  number typed equals what the template already holds.

### 2.3 Tooling defects

- **Prod verification silently not running.** Two tools crashed in their verify step when run
  from the server's staging folder, *after* their data had applied correctly. One run had been
  reported "all OK" at face value. Fixed, and both verifications re-run on prod.
- **False alarm on the Medium body's rear door.** The PU verifier expected SRD; Burt's 7 Sep
  revision moved that body to DRD, so a correctly-zero line kept reporting a mismatch. Corrected
  in #179 — all 15 lines now pass, so the next mismatch shown is a real one.

---

## 3. Data corrected on prod

| Correction | Result | Journal |
|---|---|---|
| September prices + descriptions | 410 lines | yes |
| Pairing-shift fixup | prices, then names per ruling; 0 outstanding | yes |
| Icecream PU re-anchor | all 15 lines = Burt's sheet | yes |
| Icecream floor plywood (+ Freezer Medium floor, which shares the material) | 4 lines | yes |
| Medium body rear door | DRD set to **0,12 m** per Burt's sheet, SRD → 0 (dev had drifted to 0,06 on both) | yes |
| Medium body roof + floor foam | 0,12 → **0,145 m** (≈17 % under-cost removed) | **no — see below** |

**One audit gap, recorded deliberately.** The Medium body's roof and floor thickness was corrected
by hand in the calculator before the tool ran; the tool then found nothing to change. The result is
correct and engine-verified, but that change has **no journal and no audit trail** — thickness
changes are not logged anywhere in the system (see open item 5.3).

---

## 4. Deploys by this session

| When | SHA | What | Migration | Restart |
|---|---|---|---|---|
| 4 Sep 08:42 | `cd763c8` | v1.52 September prices | `0047` | yes |
| 7 Sep 16:42 | `e9dd6da` | v1.52.1 recalc fix — **plus v1.53 #176–#178**, which rode along as ancestors of the fix and had their first prod exposure | none | yes |

Both runbooks and outcomes are in `docs/runbooks/`. The 7 Sep deploy's final check stopped on a
false alarm (a probe that omitted a required parameter got a 422); the deploy itself was complete
and was confirmed live three independent ways.

---

## 5. Open items

### 5.1 Four questions for Burt — email drafted 7 Sep; send status to confirm

1. **Floor skin naming** — every body's floor skin becomes *Rhinotex 1150 BW* except the 2,3 m
   chiller, which stays *EXT GRP SKIN 2\*300*. Deliberate?
2. **4 mm PF plywood** on the explosive bodies and 4,8 m freezer — same item under a different
   description? (R86,58 / R68,79)
3. **Bakery body** — the *BAKERY BODIES* and *Sheet1* tabs disagree (19 mm plywood R46,28 vs
   R223,15). Which is correct?
4. **Foam thickness** on 7 lines that carry a price but no stated thickness: 4,9 m & up chiller
   (5 panels), up-to-5,5 m chiller (rear doors), small meat body floor. Until confirmed these stay
   at their previous price.

Lines awaiting these answers are still costing at the **previous, higher** price — nothing is
under-quoted. Of the original 22 unmatched prod lines, at least 3 have since been resolved; an
exact current list needs a reporter that matches on September names (not yet built).

### 5.2 ⚠ The import's double-apply guard has lapsed — decision needed

`september_price_import.py` refuses a second `--apply` only while the September stamp is **less
than 7 days old**. That window closed around **11 Sep**, so re-running it against prod would no
longer be refused and would try to re-import already-imported data. *Recommend:* make the guard
permanent, or retire the script now that September is complete. (Confirmed still 7 days on base,
17 Sep.)

### 5.3 Insulation thickness drifts — design decision needed

Toggling door type or EPS/PU in a costing rewrites the **body template's** stored thickness, with
a 60 mm fallback, and leaves no trace. This is how the Medium body drifted twice in one day, and
why §3 has an unjournaled correction. The tools now detect drift instantly, but the mechanism
remains. *Question:* should the template or the individual costing be the authority for
thickness? (Still present on base 17 Sep; #184 changed defaults for *draft* bodies only.)

---

## 6. Lessons from this session (process)

- **A dev proof cannot see prod-only data.** The pairing shift passed every dev check because dev
  has no variant names. A prod dry-run is its own plan — analyse its rows, don't transfer dev's
  numbers.
- **Excel's saved results can be stale.** The workbook's cached totals lagged its own inputs
  (Excel recalculates on open; our reader does not). Always read the input cells.
- **"All OK" is a claim, not evidence.** Verify from the run's own output files — one verification
  had crashed while being reported as passing.
- **A probe must be precise.** A missing required parameter returns 422 before security checks
  run; "not found" (404) is the real sign of stale code.
- **Using the right instrument.** Re-running the September import as a status check after it had
  applied produced meaningless counts (191 "unmatched"); it only works against pre-import data.

---

## 7. Other work in the same period (other sessions — not covered here)

For completeness; see those lanes' own BA feedback and memory notes.

| PR | Date | Change |
|---|---|---|
| #176–#178 | 7 Sep | v1.53 — cross-body snapshot restore, Excel-paste vocabulary, draft-body thickness |
| #180–#184 | 8–10 Sep | v1.53 follow-ups — draft-flag pairs, Manni placeholder migration tooling, server-side default thicknesses |
| #185 / #186 | 14 Sep | v1.53.1 — cache-bust fix; master-bound draft flags never shadow body variables |
| #187 | 15 Sep | admin captures a costing for another user (migration `0048`) |
| #188 | 15 Sep | v1.54 — saved costing BOM lists lines in the calculator's order |
| #189 | 16 Sep | v1.55 — Enter moves to the next body parameter |
| #190 | 16 Sep | v1.56 — the costing shows the parameters the body was priced at |

---

**References:** runbooks `docs/runbooks/prod-deploy-v1.52-september-prices.md`,
`prod-deploy-v1.52.1-recalc-fix.md`, `prod-outcome-v1.52.2-icecream-insulation.md` · audit trail
and prod journals `docs/audit/september_price_update/` (including `prod/`) · discovery
`docs/audit/september_price_update/SECTION_3_0_DISCOVERY.md`.
