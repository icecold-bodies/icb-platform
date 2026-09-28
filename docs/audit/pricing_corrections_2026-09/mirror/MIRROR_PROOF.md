# §3.2 Prod-mirror proof — v1.58 audit pricing corrections

**28 Sep 2026.** Local database `icb_prodmirror` (created by Michael as the postgres superuser, owner `icb_app`),
`alembic upgrade head` (0049 — CI's head; prod is 0048, and 0049 only adds the audit-runs table), then the committed
prod pricing snapshot (`backend/tests/costing_audit/mes_snapshot/all.json`, sha256 `7e07c4c2…14b7`, exported from
`icb_platform` 28 Sep 07:29 SAST) loaded with the CI loader (`load_snapshot`, committed, not rolled back).

## 1. The mirror is prod

| check | result |
|---|---|
| every snapshot row vs the mirror, column by column | **3 905 of 3 910 identical**. The 5 others: 4 orphan BOM rows whose FK targets are outside the snapshot (trailer 51 — written NULL, exactly as in CI) and `admin_settings` id 10 (below) |
| `costings.pu_foam_4g_factor` | migration 0046 seeds **1.3631** on every fresh database; the loader's `ON CONFLICT DO NOTHING` then skips prod's row (**1.3171**) on the unique `key`. Set on the mirror to prod's value; the calculator then reads 1.3171. **CI's `icb_test` has the same gap** — raised as its own task (loader code, not this lane) |
| the five packs `--env prod` on the mirror vs the committed 28 Sep prod reference reports | **3 294 cells, 0 different, 0 missing** (status, Excel total and MES total per cell). The 179 other cells are the 14 new chiller `srd_pu` scenarios |

## 2. Known hits before the apply (`mirror_before_*`)

| finding | targeted cells (SKIP excluded) | before |
|---|---|---|
| F1 SRD PU — freezers, ICECREAM 4.9 UP, explosive | 21 | 21 ACCEPTED known_defect (+R22 946.75 PU line each) |
| F1c SRD PU — chillers (`srd_pu`, new) | 14 | **11 FLAG** (+R23 307.15: CHILLER MEDIUM ×3, LARGE ×8); 3 PASS (CHILLER 2.3, hand-fixed 26 Sep) |
| F2 ALU floor — ICECREAM 3,2 + 4.8 FLOOR | 30 | 25 ACCEPTED known_defect, 5 UNVERIFIABLE |
| F3 ICECREAM 4.9 UP ≠ 6.7 m | 60 | 46 ACCEPTED known_defect, 10 PASS (within tolerance near 6.7), 4 UNVERIFIABLE |
| F4 CHILLER MEDIUM DRD DOOR FITTINGS | 15 | 15 ACCEPTED known_defect |

## 3. Apply

Dry-run: 36 to apply, 0 guard mismatches. `--apply`: **36 changes on 27 lines, 9 `bom_override_history` rows**, one
transaction, journal `pricing_corrections_journal_mirror_20260928T100623Z.json` (this folder). A second apply:
*0 to apply, 36 already applied*. **Revert** (proved on the real data, then re-applied): 27 lines restored,
9 history rows deleted, and the mirror compared back to the snapshot at exactly the post-load state (3 905 identical,
the same 5 known differences) — every column of every touched line, `price_updated_at` included.

## 4. After (`mirror_final_*`, live run with the final pruned prod list)

| pack | exit | cells |
|---|---|---|
| smoke | 0 | UNVERIFIABLE 9, ACCEPTED 33, PASS 156, SKIP 36 |
| chillers | 0 | ACCEPTED 76, PASS 981, SKIP 196 |
| freezers | 0 | UNVERIFIABLE 27, ACCEPTED 73, PASS 482, SKIP 108 |
| icecream | 0 | UNVERIFIABLE 40, ACCEPTED 75, PASS 401, SKIP 96 |
| explosive | 0 | UNVERIFIABLE 36, ACCEPTED 155, PASS 385, SKIP 108 |

The single-rear-door PU line, MES vs Burt, on every targeted cell that itemises it:

| body | before | after | Burt |
|---|---:|---:|---:|
| CHILLER MEDIUM (×3), LARGE (×8) | R24 409.76 | **R1 102.61** | R1 102.61 |
| FREEZER 2.3 / MEDIUM / LARGE | R24 409.76 | **R1 463.01** | R1 463.01 |
| ICECREAM 4.9 UP | R24 409.76 | **R1 463.01** | R1 463.01 |
| EXPLOSIVE UP TO 2.7 / 4.9 AND UP | R24 409.76 | **R1 463.01** | R1 463.01 |
| EXPLOSIVE 2.7 TO 4.8, CHILLER 2.3 | — | SRD cell **PASS** (0.27 % / 0.001 %) | |

What still greys some of those SRD cells is **other, pre-existing** entries only: tapping blocks (freezers −R60,
EXPLOSIVE 4.9 AND UP −R127, CHILLER LARGE +R60), the icecream buffer plate, the EXPLOSIVE UP TO 2.7 0.9 MM ALU
PLATE, and the held SRD plywood/glue ruling (CHILLER MEDIUM). F3 and F4: every targeted cell PASS. F2: ICECREAM 3,2
FLOOR PASS; ICECREAM 4.8 FLOOR carries only the 12MM PF PLYWOOD draft choice the probe cannot tick (−R1.9k to −R2.5k).

## 5. The prune — one entry at a time (`reaccept` on the saved reports)

Each step re-judged the AFTER reports (must stay green) and the BEFORE reports (the entry must have been
load-bearing — the known-hit rule for a prune).

| step | change to `accepted_differences.prod.yaml` | AFTER (worst exit) | BEFORE — cells that turn red |
|---|---|---|---|
| 0 | none | 1 (= the live run) | — |
| 1 | held rear-frame ruling: `variant: srd` → `[srd, srd_pu]` | 1 → chillers PRESENCE 14 → ACCEPTED | — (an extension of a held ruling) |
| 2 | held SRD plywood/glue ruling: → `[srd, srd_pu]` | **0** | chillers still FLAG 11 — the R24.4k is NOT explained by it |
| 3 | **remove F4** (CHILLER MEDIUM door rubber ×0) | 0, unchanged | +15 chillers, +6 smoke |
| 4 | **remove F3** (ICECREAM 4.9 UP length 6.7) | 0, unchanged | +46 icecream |
| 5 | **remove F1** (single-rear-door PU R24.4k) | 0, unchanged | +9 freezers, +3 icecream, +9 explosive |
| 6 | **narrow F2** to ICECREAM 4.8 + `12MM PF PLYWOOD` (a probe limit) | 0, unchanged | +25 icecream, +6 smoke |

The dev list (`accepted_differences.yaml`) gets only the two held-ruling extensions (steps 1–2): the chillers pack
now has `srd_pu` scenarios on dev too. Nothing is pruned from it — dev is Michael's workbench.

## 6. Reproduce

```
DATABASE_URL=postgresql+psycopg://icb_app:…@localhost:5432/icb_prodmirror
python -m alembic upgrade head
python -c "from pathlib import Path; from tools.costing_audit.mes_snapshot import load_snapshot; load_snapshot(Path('tests/costing_audit/mes_snapshot/all.json'), allow_non_test_db=True)"
# then set admin_settings 'costings.pu_foam_4g_factor' to the snapshot's value (§1)
python -m tools.costing_audit run --pack <p> --env prod --out <dir>          # before
python tools/audit_pricing_corrections.py --target mirror [--apply]          # dry-run / apply
python -m tools.costing_audit run --pack <p> --env prod --out <dir>          # after
python -m tools.costing_audit reaccept --report <json> --env prod            # the prune, entry by entry
```
