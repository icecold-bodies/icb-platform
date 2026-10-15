## Costing audit — pack `smoke` — FAIL

- Run: 2026-10-15T10:56:05+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-05T13:50:35+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 18 scenarios
- Cells: FLAG 27, ACCEPTED 12, PASS 150, SKIP 45
- Full report: `prod_smoke.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unaccepted differences (27)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L4.2 W2.5 H2.4 as_sheet | 5,983.99 | 5,690.53 | 4.90 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L5.6 W2.5 H2.4 as_sheet | 5,983.99 | 5,690.53 | 4.90 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L6 W2.5 H2.4 as_sheet | 5,983.99 | 5,690.53 | 4.90 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L4.2 W2.5 H2.4 roof_floor_eps | 5,920.60 | 5,627.14 | 4.96 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L5.6 W2.5 H2.4 roof_floor_eps | 5,920.60 | 5,627.14 | 4.96 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | DRD DOOR FITTINGS | L6 W2.5 H2.4 roof_floor_eps | 5,920.60 | 5,627.14 | 4.96 | FLAG | QTY_DIFF CSLB HINGES (-293.46) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L4.2 W2.5 H2.4 as_sheet | 34,797.93 | 35,494.63 | 2.00 | FLAG | PRICE_DIFF 12MM PF PLYWOOD (+483.73) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L5.6 W2.5 H2.4 as_sheet | 45,781.52 | 46,701.69 | 2.01 | FLAG | PRICE_DIFF 12MM PF PLYWOOD (+643.08) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L6 W2.5 H2.4 as_sheet | 48,919.69 | 49,903.70 | 2.01 | FLAG | PRICE_DIFF 12MM PF PLYWOOD (+688.62) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L4.2 W2.5 H2.4 roof_floor_eps | 33,266.83 | 34,499.34 | 3.71 | FLAG | PRICE_DIFF EPS (+535.80) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L5.6 W2.5 H2.4 roof_floor_eps | 43,746.05 | 45,378.53 | 3.73 | FLAG | PRICE_DIFF EPS (+712.30) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L6 W2.5 H2.4 roof_floor_eps | 46,740.12 | 48,486.87 | 3.74 | FLAG | PRICE_DIFF EPS (+762.73) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L4.2 W2.5 H2.4 roof_floor_eps | 7,530.70 | 8,066.44 | 7.11 | FLAG | PRICE_DIFF EPS (+535.80) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L5.6 W2.5 H2.4 roof_floor_eps | 9,974.10 | 10,686.31 | 7.14 | FLAG | PRICE_DIFF EPS (+712.30) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L6 W2.5 H2.4 roof_floor_eps | 10,672.22 | 11,434.85 | 7.15 | FLAG | PRICE_DIFF EPS (+762.73) |
| UP TO 5.5 CHILLER AND 2.3 WIDE | FLOOR | L4.2 W2.3 H2.3 as_sheet | 12,964.30 | 13,164.19 | 1.54 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+199.88) |
| UP TO 5.5 CHILLER AND 2.3 WIDE | FLOOR | L5.5 W2.3 H2.3 as_sheet | 16,875.32 | 17,131.09 | 1.52 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+255.77) |
| UP TO 5.5 CHILLER AND 2.3 WIDE | FLOOR | L5.8 W2.3 H2.3 as_sheet | 17,777.86 | 18,046.53 | 1.51 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+268.66) |
| UP TO 5.5 CHILLER AND 2.3 WIDE | FLOOR | L4.2 W2.3 H2.3 srd | 12,964.30 | 13,164.19 | 1.54 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+199.88) |
| UP TO 5.5 CHILLER AND 2.3 WIDE | FLOOR | L5.5 W2.3 H2.3 srd | 16,875.32 | 17,131.09 | 1.52 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+255.77) |
| UP TO 5.5 CHILLER AND 2.3 WIDE | FLOOR | L5.8 W2.3 H2.3 srd | 17,777.86 | 18,046.53 | 1.51 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+268.66) |
| icecream up to 4.8 | FLOOR | L3.6 W2.3 H2.26 as_sheet | 14,967.61 | 13,227.59 | 11.62 | FLAG accepted cause(s) explain -1 914.11 of -1 740.02; unexplained +174.09 | MISSING_IN_MES 12MM PF PLYWOOD (-1914.11) |
| icecream up to 4.8 | FLOOR | L4.2 W2.3 H2.26 as_sheet | 17,398.73 | 15,369.86 | 11.66 | FLAG accepted cause(s) explain -2 228.75 of -2 028.87; unexplained +199.88 | MISSING_IN_MES 12MM PF PLYWOOD (-2228.75) |
| icecream up to 4.8 | FLOOR | L4.8 W2.3 H2.26 as_sheet | 19,829.85 | 17,512.13 | 11.69 | FLAG accepted cause(s) explain -2 543.40 of -2 317.72; unexplained +225.68 | MISSING_IN_MES 12MM PF PLYWOOD (-2543.40) |
| icecream up to 4.8 | FLOOR | L3.6 W2.3 H2.26 srd | 14,967.61 | 13,227.59 | 11.62 | FLAG accepted cause(s) explain -1 914.11 of -1 740.02; unexplained +174.09 | MISSING_IN_MES 12MM PF PLYWOOD (-1914.11) |
| icecream up to 4.8 | FLOOR | L4.2 W2.3 H2.26 srd | 17,398.73 | 15,369.86 | 11.66 | FLAG accepted cause(s) explain -2 228.75 of -2 028.87; unexplained +199.88 | MISSING_IN_MES 12MM PF PLYWOOD (-2228.75) |
| icecream up to 4.8 | FLOOR | L4.8 W2.3 H2.26 srd | 19,829.85 | 17,512.13 | 11.69 | FLAG accepted cause(s) explain -2 543.40 of -2 317.72; unexplained +225.68 | MISSING_IN_MES 12MM PF PLYWOOD (-2543.40) |

### Known defects — accepted, tracked, awaiting a work order (12 cells)

- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [DATA] SMALL MOUNTING BRACKET priced differently from Burt's sheet on FREEZER MEDIUM (-R126), prod as dev. — review by 2026-10-31 (6)
- icecream up to 4.8 · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (6)

### Oracle findings and probe notes

- UP TO 5.5 CHILLER AND 2.3 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (6)
