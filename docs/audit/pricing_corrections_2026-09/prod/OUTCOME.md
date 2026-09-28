# OUTCOME — v1.58 pricing corrections on PROD (F1–F4, 36 rows)

**Applied 28 Sep 2026 13:16:58 SAST on `icb_platform`** (alembic 0048, prod code `6b77d52`) by Michael, from the
manifest staged at `b88ae9a` (sha256 `f7d0232f…`), GO on all 36 rows (BA ruling 2c). No code, no migration, no deploy.
Saved costings untouched.

## 1. The apply

`sudo bash /tmp/icb-audit-pc/pc_prod.sh apply`; full record `apply_20260928T111656Z_run.txt` (this folder, sha256
`3abeac6e…`, byte-exact from the VM). The lines that matter, verbatim:

```
== prod: db=icb_platform alembic=0048 code=? mode=apply  2026-09-28T13:16:56+02:00
== dry-run (READ ONLY)
36 to apply, 0 already applied.
== pre-apply backup (data only): bill_of_materials + bom_override_history
== apply — one transaction
36 to apply, 0 already applied.
APPLIED 36 changes on 27 lines (9 bom_override_history rows). Journal: /tmp/icb-audit-pc/out-apply-20260928T111656Z/pricing_corrections_journal_prod_20260928T111658Z.json
== second dry-run (must find nothing to apply)
0 to apply, 36 already applied.
nothing to apply.
== journal kept at /var/backups/icb-pricing-corrections-2026-09/pricing_corrections_journal_prod_20260928T111658Z.json
```

- **0 guard mismatches.** The tool aborts the whole apply on any mismatch; it applied 36 of 36.
- **Journal:** `/var/backups/icb-pricing-corrections-2026-09/pricing_corrections_journal_prod_20260928T111658Z.json`,
  sha256 `f550a161b68f9ec0113f81373ec670e3a745e1fae5e3efd337b16453c64f6561`. It records batch
  2026-09-28T11:16:58Z, 36 changes, 27 before-rows and `bom_override_history` ids 240–248. Copy in this folder.
- **Pre-apply backup:** `pre_apply_bom.sql.gz` (data only: `bill_of_materials` + `bom_override_history`), sha256
  `06b566bb…`, beside the journal.
- **Revert** (if ever needed):
  `sudo bash /tmp/icb-audit-pc/pc_prod.sh revert /var/backups/icb-pricing-corrections-2026-09/pricing_corrections_journal_prod_20260928T111658Z.json`.
  Proved on the prod mirror to restore every column byte for byte. It refuses if a line has moved since the apply.
- **Provenance note** beside the journal (Michael's paste; sha256 `43fe0e97…`). The journal itself is untouched:

```
journal      pricing_corrections_journal_prod_20260928T111658Z.json
staged_from  b88ae9aaa0892dd4742219c75c226d477f0f5f67   (by hand: the staged pc_prod.sh predates the provenance line)
prod_code    6b77d52   (the run header printed code=?)
tool         3ee4d8306afd9a9981a0e9d9b34c3f310f9ab33e65f307d98acee7a5437ac119  backend/tools/audit_pricing_corrections.py
manifest     f7d0232fe9aa9d056c73e41e7bce70f425b7c7fa091f2c59a34d0f3cb93032b4  docs/audit/pricing_corrections_2026-09/manifest.yaml
```

## 2. Prod audit re-run (all five packs)

`sudo bash /tmp/icb-audit-rerun/prod_rerun.sh`, 28 Sep 13:33 SAST. The header read `code=6b77d52 staged=9228cef…`, so
the label fix works. The pack files, golden and the pruned prod list were staged from `9228cef`. Reports and checks are
in `rerun_20260928-133335/`.

**All five packs exit 0.** And **the prod re-run equals the mirror's final run cell for cell: 3 473 of 3 473 cells**,
status, both totals and the accepted reason included. The mirror proof therefore stands for prod.

| family | before (28 Sep 07:28 prod reference) | after (28 Sep 13:33) | exit |
|---|---|---|---|
| chillers | ACCEPTED 66, PASS 840, SKIP 168 — 84 scenarios; with the new `srd_pu` scenarios (mirror = prod): **FLAG 11**, PRESENCE 14, ACCEPTED 66, PASS 966, SKIP 196 | ACCEPTED 76, PASS 981, SKIP 196 | 1 → **0** |
| freezers | UNVERIFIABLE 27, ACCEPTED 73, PASS 482, SKIP 108 | UNVERIFIABLE 27, ACCEPTED 73, PASS 482, SKIP 108 (the accepted reasons changed, see below) | 0 → 0 |
| icecream | UNVERIFIABLE 40, ACCEPTED 131, PASS 345, SKIP 96 | UNVERIFIABLE 40, ACCEPTED **75**, PASS **401**, SKIP 96 | 0 → 0 |
| explosive | UNVERIFIABLE 36, ACCEPTED 158, PASS 382, SKIP 108 | UNVERIFIABLE 36, ACCEPTED **155**, PASS **385**, SKIP 108 | 0 → 0 |
| (smoke) | UNVERIFIABLE 9, ACCEPTED 39, PASS 150, SKIP 36 | UNVERIFIABLE 9, ACCEPTED 33, PASS 156, SKIP 36 | 0 → 0 |

**The targeted cells.** Every F1–F4 defect is gone from every targeted cell. What still greys some of them is a
different, pre-existing entry, named here:

| finding | cells | after | what the audit shows |
|---|---:|---|---|
| F1 SRD PU (freezers, ICECREAM 4.9 UP, explosive) | 21 | 3 PASS, 18 ACCEPTED | the PU line = Burt's **to the cent** on every cell: R24 409.76 → **R1 463.01** (Burt R1 463.01). The 18 are held by other entries: tapping blocks (freezers −R60, EXPLOSIVE 4.9 AND UP −R127), the icecream buffer plate, and the EXPLOSIVE UP TO 2.7 0.9 MM ALU PLATE (F5 #15) |
| F1c SRD PU (chillers, new `srd_pu`) | 14 | 3 PASS, 11 ACCEPTED | CHILLER MEDIUM / LARGE PU line R24 409.76 → **R1 102.61** (Burt R1 102.61); held by tapping blocks and the held SRD plywood/glue ruling; CHILLER 2.3 PASS |
| F2 ALU floor default | 30 | 10 PASS, 15 ACCEPTED, 5 UNVERIFIABLE | the ALU floor is gone from every cell. ICECREAM 3,2 FLOOR PASS. ICECREAM 4.8 FLOOR shows only the `12MM PF PLYWOOD` draft flag, which the probe cannot tick (§6) |
| F3 ICECREAM 4.9 UP length | 60 | **56 PASS**, 4 UNVERIFIABLE | — |
| F4 CHILLER MEDIUM door rubber | 15 | **15 PASS** | — |

## 3. The prune: one entry at a time, `reaccept` on the prod reports

The list was rebuilt one change at a time from the pre-lane list (`b10a7cf`), and step 6 equals the committed list,
entry for entry. Each step was re-judged against the **prod after-reports** (they must stay green) and against the
**before-reports** (the mirror's, proved cell-identical to the 28 Sep prod reference run), which shows the entry was
load-bearing. Full log: `rerun_20260928-133335/prune_reaccept_steps.txt`.

| step | change to `accepted_differences.prod.yaml` | prod AFTER | BEFORE: cells that turn red |
|---|---|---|---|
| 0 | none | chillers 1 (FLAG 3 + PRESENCE 14 on the new `srd_pu` cells) | — |
| 1 | held rear-frame ruling: `variant` += `srd_pu` | chillers 1 (FLAG 3) | — (extends a held ruling) |
| 2 | held SRD plywood/glue ruling: `variant` += `srd_pu` | **all 0** | the 11 R24.4k chiller cells stay FLAG: the ruling cannot hide F1 |
| 3 | **removed F4** (CHILLER MEDIUM door rubber ×0) | all 0, unchanged | +15 chillers, +6 smoke |
| 4 | **removed F3** (ICECREAM 4.9 UP length 6.7) | all 0, unchanged | +46 icecream |
| 5 | **removed F1** (single-rear-door PU R24.4k) | all 0, unchanged | +9 freezers, +3 icecream, +9 explosive |
| 6 | **narrowed F2** to ICECREAM 4.8 + `12MM PF PLYWOOD` (`[TOOL]`) | all 0, unchanged | +25 icecream, +6 smoke |

The SRD DOOR FITTINGS entry stays, for the F5 batch.

## 4. Sweep by mechanism (E3): lines still inheriting the shared SRD PU material

The shared material is prod material **292 `PU`**, now R4 100. Its last change was 7 Sep 15:38:25 SAST, and there is
no bulk-update note. `checks/E3_*.csv`. Every line on it with **no own price**:

| body | active | bom | formula | what it prices |
|---|---|---|---|---|
| **MEAT HANGER LARGE** (12) | **yes** | **5851** | `1.22*2.44*2` | **R24 409.76**: the same defect, live |
| **MEAT HANGER SMALL-MEDIUM** (36) | **yes** | **6159** | `1.22*2.44*2` | **R24 409.76**: the same defect, live |
| ICECREAM BODY MEDIUM (17) | yes | 5585 | Burt's shape `…/2.98…` | R1 463.01 at 0.06: right today, but it moves with the next edit of the shared material |
| 12 inactive / deleted bodies (ADV VACUUM, CHESTER, old EXPLOSIVE / SMALL MEAT copies) | no | — | `…*0*2` | R0, not quotable |

**Two hits, as the BA predicted.** Both MEAT HANGERs quote the R24.4k single-door PU. Neither has a pack, so the six
variants never exercised them. No saved MEAT HANGER costing has ever priced that line: the 28 Sep impact query took
every costing with an SRD PU line above zero, and none was a MEAT HANGER. **Recommendation:** fix both in the same
shape (own price R4 100) as the first rows of the F5 batch. The proof is an engine-plus-Burt-row check, since there is
no golden, unless a MEAT HANGER pack is added first. Line 5585 should get its own R4 100 in the same batch so nothing
still rides the shared material.

## 5. What caused the 7 Sep change to that shared material

**A hand edit in the app, not a September manifest row.** The September prod import (4 Sep 08:42 SAST) never touched
material 292. It set line 5585's own price, R516.64 → R491.47. On 7 Sep (`checks/C1_*`, `C2_*`, SAST):

| time | record | change |
|---|---|---|
| 14:14:39 | `bom_override_history` 210 | ICECREAM 4.8 SRD PU line 5585 own price R4 100 → R491.47 |
| 14:28:19 | `bom_override_history` 211 | ICECREAM 4.8 DRD PU line 5612 own price — → R491.47 |
| 15:19:09 | `price_history` 296 | **shared DRD PU material 209: R352.12 → R4 100**, no user recorded |
| 15:19:31 | `bom_override_history` 212 | line 5612's own price cleared (→ inherits R4 100) |
| **15:38:25** | `price_history` **297** | **shared SRD PU material 292: R516.64 → R4 100**, no user recorded |
| 15:38:33 | `bom_override_history` 213 | line 5585's own price cleared (→ inherits R4 100) |

So during the ICECREAM 4.8 rear-door fix, two things happened within 8 seconds each time. The correct 32D rate for
that body (R4 100, right for its Burt-shape formulas) was put on the **shared** material instead of on the lines. Then
the lines' own prices were cleared (a single-line `PUT /api/bom/{id}`, e.g. the calculator section-price dialog's
"↩ Restore to material price"; the data does not say which screen).
This was before that day's 16:42 SAST deploy.

**Who: the data cannot say.** The app's material edit (`PUT /api/materials/{id}`, `materials.py:82-84`) writes
`price_history` without `changed_by`. `bom_override_history` has no user column at all. Every tool stamps
`changed_by` (e.g. `september_2026_price_update (v1.52)`), and here it is empty, which is how we know this was the app.
**Lessons for the price-update tooling / app** (a code lane, not Burt's):
1. Stamp the session user on both history writes.
2. Warn before a shared material's price is edited, listing the bodies that inherit it. The dialog already fetches that
   list (`/api/materials/{id}/trailer-usage`) but only displays it.
3. Prefer a line's own price over the shared material.

**Time zone correction:** these columns are `timestamp without time zone`, and the app's UTC write is stored in the
session zone (Africa/Johannesburg; proved on the mirror, where 10:06:23 UTC was stored as 12:06:23). Every history time
here is **SAST**. The discovery doc's "15:38 UTC" was wrong and is corrected; 15:38 SAST = 13:38 UTC.

**F5 #3 (22 Sep), for the BA's question to Michael:** `bom_override_history` 221–224. Between 13:09:26 and 13:10:53
SAST, the four EXPLOSIVE 4.9 AND UP PU lines (FRONT 3940, DRD 3974, SIDES 3996, ROOF 4005) went R172.02 → R234.15,
one line about every 30 s. That is four single-line edits in the section-price dialog. The same morning (09:28–09:29)
the shared FRONT (207) and SIDES (211) PU materials went R245.74 → R185.20, also by app edit. **No user is recorded
for any of them.**

## 6. F2 draft shape and the ICECREAM 4.8 floor (BA ruling 2c §2)

- **F2 (the §2.3 paste, recorded):** both bodies have a server draft. ALU EXTRUTION FLOOR is a `flag` node with
  `flagValue=0` (tickbox), bound to masters 5835 / 5713 (`checks/F2_*`). That is **the first row of the BA's table:
  users already saw it unticked.** The flip aligns the stored default and removes the audit's phantom, so nothing needs
  telling to anyone.
- **The 4.8 plywood floor: the item closes, it is priced.** Prod's 4.8 draft (updated 25 Sep 12:40) carries three
  **unbound** flags under FLOOR TYPE: `12MM PF PLYWOOD` **flagValue=1**, `9MM BIRCH PLYWOOD` 0, `12MM FINN PLYWOOD` 0
  (`checks/P2_*`). The calculator sends an unbound flag by its label (`flag_overrides`, `calculator.js:5877-5908`), and
  the server adds it to the selected option names (`calculator.py:310-313`). That satisfies line **5653 `12MM PF
  PLYWOOD`**'s gate `{"option": "12MM PF PLYWOOD", "equals": "Y"}`. So a 4.8 quote starts with the 12 mm PF plywood
  floor, and with ALU off it is the floor. It prices **exactly** Burt's row: `((length+{Waste})*(width+{Waste}))/2.98`
  × R665 = Burt's 12MM PF PLYWOOD to the cent at 3.6 / 4.2 / 4.8 m (R1 914.11 / R2 228.75 / R2 543.40). Nothing to
  insert. The audit shows it "missing" only because its probe cannot set an unbound draft flag. That is the narrowed
  `[TOOL]` entry, and it is a Phase 2 probe item (read the draft's unbound-flag defaults), not a pricing defect. (Dev's
  4.8 draft has no such nodes: prod and dev differ here.)

## 7. Next

Snapshot regenerated from prod (the prod-baseline paste) → committed with the pruned prod list → PR #197 ready → CI
green on the exact head → one line to Michael → WAIT for the merge word → squash-merge → announce the base SHA → remove
`/tmp/icb-audit*` and `/tmp/icb-prod-baseline*` on the VM. Then the BA dispatches `fix/v1.58.1-audit-f5-batch`,
with the MEAT HANGER lines (§4) proposed as its first rows.
