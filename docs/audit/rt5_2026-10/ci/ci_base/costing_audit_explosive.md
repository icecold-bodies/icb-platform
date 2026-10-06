## Costing audit — pack `explosive` — FAIL

- Run: 2026-10-05T13:55:20+00:00 · tolerance 1.0 % · MES: in-process localhost/icb_test
- Golden: 2026-10-01T18:02:46+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 54 scenarios
- Cells: FLAG 15, UNVERIFIABLE 36, ACCEPTED 104, PASS 412, SKIP 117
- Full report: `costing_audit_explosive.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unaccepted differences (15)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| EXPLOSIVE 4.9 AND UP | ROOF | L4.9 W2.6 H2.1 all_pu | 12,077.41 | 12,200.09 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+118.88) |
| EXPLOSIVE 4.9 AND UP | ROOF | L8 W2.6 H2.1 all_pu | 19,581.26 | 19,780.76 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+193.33) |
| EXPLOSIVE 4.9 AND UP | ROOF | L14.7 W2.6 H2.1 all_pu | 35,799.24 | 36,164.79 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+354.24) |
| EXPLOSIVE 4.9 AND UP | ROOF | L4.9 W2.6 H2.1 as_sheet | 12,077.41 | 12,200.09 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+118.88) |
| EXPLOSIVE 4.9 AND UP | ROOF | L8 W2.6 H2.1 as_sheet | 19,581.26 | 19,780.76 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+193.33) |
| EXPLOSIVE 4.9 AND UP | ROOF | L14.7 W2.6 H2.1 as_sheet | 35,799.24 | 36,164.79 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+354.24) |
| EXPLOSIVE 4.9 AND UP | ROOF | L4.9 W2.6 H2.1 drd | 12,077.41 | 12,200.09 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+118.88) |
| EXPLOSIVE 4.9 AND UP | ROOF | L8 W2.6 H2.1 drd | 19,581.26 | 19,780.76 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+193.33) |
| EXPLOSIVE 4.9 AND UP | ROOF | L14.7 W2.6 H2.1 drd | 35,799.24 | 36,164.79 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+354.24) |
| EXPLOSIVE 4.9 AND UP | ROOF | L4.9 W2.6 H2.1 foam_4g | 12,077.41 | 12,200.09 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+118.88) |
| EXPLOSIVE 4.9 AND UP | ROOF | L8 W2.6 H2.1 foam_4g | 19,581.26 | 19,780.76 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+193.33) |
| EXPLOSIVE 4.9 AND UP | ROOF | L14.7 W2.6 H2.1 foam_4g | 35,799.24 | 36,164.79 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+354.24) |
| EXPLOSIVE 4.9 AND UP | ROOF | L4.9 W2.6 H2.1 srd | 12,077.41 | 12,200.09 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+118.88) |
| EXPLOSIVE 4.9 AND UP | ROOF | L8 W2.6 H2.1 srd | 19,581.26 | 19,780.76 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+193.33) |
| EXPLOSIVE 4.9 AND UP | ROOF | L14.7 W2.6 H2.1 srd | 35,799.24 | 36,164.79 | 1.02 | FLAG | GROUP_DIFF 4MM PF PLYWOOD ~ 6MM PF PLYWOOD (+354.24) |

### Unverifiable (36 cells)

- EXPLOSIVE 2.7 TO 4.8 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 2.7 TO 4.8 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 2.7 TO 4.8 · ROOF · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 2.7 TO 4.8 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 4.9 AND UP · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 4.9 AND UP · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 4.9 AND UP · ROOF · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 4.9 AND UP · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE UP TO 2.7 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE UP TO 2.7 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE UP TO 2.7 · ROOF · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE UP TO 2.7 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)

### Known defects — accepted, tracked, awaiting a work order (104 cells)

- EXPLOSIVE 2.7 TO 4.8 · ROOF · [DATA] A PRICE, not only a label: PROD EXPLOSIVE 2.7 TO 4.8 prices its ROOF/SIDES plywood as 6MM PF PLYWOOD at R95.64/m2 where Burt has 4MM PF PLYWOOD at R86.58/m2 (+R58.51 to +R193.93 per cell, all of it the plywood line). On Michael's hand-fix list. (RT2 close: the entry's EXPLOSIVE 4.9 AND UP PU half went with Manifest P + the 4G body default.) — review by 2026-10-31 (15)
- EXPLOSIVE 2.7 TO 4.8 · SIDES · [DATA] A PRICE, not only a label: PROD EXPLOSIVE 2.7 TO 4.8 prices its ROOF/SIDES plywood as 6MM PF PLYWOOD at R95.64/m2 where Burt has 4MM PF PLYWOOD at R86.58/m2 (+R58.51 to +R193.93 per cell, all of it the plywood line). On Michael's hand-fix list. (RT2 close: the entry's EXPLOSIVE 4.9 AND UP PU half went with Manifest P + the 4G body default.) — review by 2026-10-31 (14)
- EXPLOSIVE 2.7 TO 4.8 · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE (FREEZER MEDIUM, explosive bodies) / MOUNTING CLEATS (EXPLOSIVE 2.7 TO 4.8) lines have no MES line on prod. — review by 2026-10-31 (18)
- EXPLOSIVE 4.9 AND UP · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (12)
- EXPLOSIVE 4.9 AND UP · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (3)
- EXPLOSIVE 4.9 AND UP · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE (FREEZER MEDIUM, explosive bodies) / MOUNTING CLEATS (EXPLOSIVE 2.7 TO 4.8) lines have no MES line on prod. — review by 2026-10-31 (18)
- EXPLOSIVE UP TO 2.7 · SRD · [DATA] 0.9 MM ALU PLATE on the EXPLOSIVE UP TO 2.7 single rear door priced/quantified differently from Burt's sheet (-R325), prod as dev. — review by 2026-10-31 (3)
- EXPLOSIVE UP TO 2.7 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (3)
- EXPLOSIVE UP TO 2.7 · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE (FREEZER MEDIUM, explosive bodies) / MOUNTING CLEATS (EXPLOSIVE 2.7 TO 4.8) lines have no MES line on prod. — review by 2026-10-31 (18)

### Oracle findings and probe notes

- EXPLOSIVE 4.9 AND UP: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE 4.9 AND UP: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE 4.9 AND UP: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE 4.9 AND UP: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default ON (18)
- EXPLOSIVE 4.9 AND UP: mixed PU references on the sheet as saved: 1x 32D (C17) + 4x 4G (C19); normalised to 4G for this scenario (18)
- EXPLOSIVE UP TO 2.7: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE UP TO 2.7: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE UP TO 2.7: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE UP TO 2.7: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default ON (18)
