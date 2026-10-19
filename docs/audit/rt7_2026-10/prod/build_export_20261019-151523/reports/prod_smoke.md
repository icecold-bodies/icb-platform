## Costing audit — pack `smoke` — FAIL

- Run: 2026-10-19T13:15:28+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-05T13:50:35+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 18 scenarios
- Cells: FLAG 15, ACCEPTED 18, PASS 156, SKIP 45
- Full report: `prod_smoke.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unaccepted differences (15)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L4.2 W2.5 H2.4 as_sheet | 5,983.99 | 5,690.53 | 4.90 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L5.6 W2.5 H2.4 as_sheet | 5,983.99 | 5,690.53 | 4.90 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L6 W2.5 H2.4 as_sheet | 5,983.99 | 5,690.53 | 4.90 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L4.2 W2.5 H2.4 roof_floor_eps | 5,920.60 | 5,627.14 | 4.96 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L5.6 W2.5 H2.4 roof_floor_eps | 5,920.60 | 5,627.14 | 4.96 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L6 W2.5 H2.4 roof_floor_eps | 5,920.60 | 5,627.14 | 4.96 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L4.2 W2.5 H2.4 as_sheet | 34,797.93 | 35,281.64 | 1.39 | FLAG | PRICE_DIFF 12MM PF PLYWOOD (+483.73) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L5.6 W2.5 H2.4 as_sheet | 45,781.52 | 46,424.57 | 1.41 | FLAG | PRICE_DIFF 12MM PF PLYWOOD (+643.08) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L6 W2.5 H2.4 as_sheet | 48,919.69 | 49,608.26 | 1.41 | FLAG | PRICE_DIFF 12MM PF PLYWOOD (+688.62) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L4.2 W2.5 H2.4 roof_floor_eps | 33,266.83 | 34,286.34 | 3.06 | FLAG | PRICE_DIFF EPS (+535.80) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L5.6 W2.5 H2.4 roof_floor_eps | 43,746.05 | 45,101.41 | 3.10 | FLAG | PRICE_DIFF EPS (+712.30) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L6 W2.5 H2.4 roof_floor_eps | 46,740.12 | 48,191.43 | 3.10 | FLAG | PRICE_DIFF EPS (+762.73) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L4.2 W2.5 H2.4 roof_floor_eps | 7,530.70 | 8,066.44 | 7.11 | FLAG | PRICE_DIFF EPS (+535.80) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L5.6 W2.5 H2.4 roof_floor_eps | 9,974.10 | 10,686.31 | 7.14 | FLAG | PRICE_DIFF EPS (+712.30) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L6 W2.5 H2.4 roof_floor_eps | 10,672.22 | 11,434.85 | 7.15 | FLAG | PRICE_DIFF EPS (+762.73) |

### Known defects — accepted, tracked, awaiting a work order (18 cells)

- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [DATA] SMALL MOUNTING BRACKET priced differently from Burt's sheet on FREEZER MEDIUM (-R126), prod as dev. — review by 2026-10-31 (6)
- icecream up to 4.8 · FLOOR · [TOOL] ICECREAM UP TO 4.8's 12MM PF PLYWOOD floor line (bom 5653) prices only when its draft choice '12MM PF PLYWOOD' is ticked (beside 9MM BIRCH 11203 and 12MM FINN 11207); the audit probe cannot tick a draft choice, so the FLOOR reads it missing (-R1.9k to -R2.5k). A probe limit, not a template defect (Michael, 28 Sep) — still to confirm which choice the calculator starts with. The ALU EXTRUTION FLOOR default was turned OFF in v1.58. — review by 2026-10-31 (6)
- icecream up to 4.8 · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (6)

### Oracle findings and probe notes

- UP TO 5.5 CHILLER AND 2.3 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (6)
