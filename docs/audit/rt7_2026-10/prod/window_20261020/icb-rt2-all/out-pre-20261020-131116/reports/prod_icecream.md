## Costing audit — pack `icecream` — FAIL

- Run: 2026-10-20T11:11:29+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-01T18:00:46+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 48 scenarios
- Cells: FLAG 37, UNVERIFIABLE 40, ACCEPTED 32, PASS 387, SKIP 116
- Full report: `prod_icecream.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unaccepted differences (37)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| icecream 4.9 up | DRD | L4.9 W2.6 H2.6 foam_4g | 8,095.20 | 7,965.97 | 1.60 | FLAG accepted cause(s) explain +0.00 of -129.23; unexplained -129.23 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 1 MES line(s) (-234.00) |
| icecream 4.9 up | DRD | L6.7 W2.6 H2.6 foam_4g | 8,095.20 | 7,965.97 | 1.60 | FLAG accepted cause(s) explain +0.00 of -129.23; unexplained -129.23 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 1 MES line(s) (-234.00) |
| icecream 4.9 up | DRD | L8 W2.6 H2.6 foam_4g | 8,095.20 | 7,965.97 | 1.60 | FLAG accepted cause(s) explain +0.00 of -129.23; unexplained -129.23 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 1 MES line(s) (-234.00) |
| icecream 4.9 up | FRONT | L4.9 W2.6 H2.6 foam_4g | 7,157.15 | 7,027.92 | 1.81 | FLAG | BOTH PU (-129.17) |
| icecream 4.9 up | FRONT | L6.7 W2.6 H2.6 foam_4g | 7,157.15 | 7,027.92 | 1.81 | FLAG | BOTH PU (-129.17) |
| icecream 4.9 up | FRONT | L8 W2.6 H2.6 foam_4g | 7,157.15 | 7,027.92 | 1.81 | FLAG | BOTH PU (-129.17) |
| icecream 4.9 up | ROOF | L4.9 W2.6 H2.6 foam_4g | 15,361.09 | 15,087.99 | 1.78 | FLAG | BOTH PU (-272.97) |
| icecream 4.9 up | ROOF | L6.7 W2.6 H2.6 foam_4g | 20,909.89 | 20,537.48 | 1.78 | FLAG | BOTH PU (-372.24) |
| icecream 4.9 up | ROOF | L8 W2.6 H2.6 foam_4g | 24,917.36 | 24,473.23 | 1.78 | FLAG | BOTH PU (-443.93) |
| icecream 4.9 up | SIDES | L4.9 W2.6 H2.6 foam_4g | 29,587.84 | 29,063.49 | 1.77 | FLAG | BOTH PU (-524.10) |
| icecream 4.9 up | SIDES | L6.7 W2.6 H2.6 foam_4g | 40,205.87 | 39,490.84 | 1.78 | FLAG | BOTH PU (-714.69) |
| icecream 4.9 up | SIDES | L8 W2.6 H2.6 foam_4g | 47,874.45 | 47,021.71 | 1.78 | FLAG | BOTH PU (-852.33) |
| icecream up to 3,2 | DRD | L2.4 W2.1 H2 foam_4g | 6,329.78 | 5,962.38 | 5.80 | FLAG accepted cause(s) explain -259.72 of -367.40; unexplained -107.68 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 2 MES line(s) (-259.72) |
| icecream up to 3,2 | DRD | L3.2 W2.1 H2 foam_4g | 6,329.78 | 5,962.38 | 5.80 | FLAG accepted cause(s) explain -259.72 of -367.40; unexplained -107.68 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 2 MES line(s) (-259.72) |
| icecream up to 3,2 | FLOOR | L2.4 W2.1 H2 foam_4g | 9,906.05 | 9,797.96 | 1.09 | FLAG | BOTH PU (-108.09) |
| icecream up to 3,2 | FLOOR | L3.2 W2.1 H2 foam_4g | 12,808.64 | 12,665.26 | 1.12 | FLAG | BOTH PU (-143.38) |
| icecream up to 3,2 | FRONT | L2.4 W2.1 H2 foam_4g | 5,193.91 | 5,086.24 | 2.07 | FLAG | BOTH PU (-107.65) |
| icecream up to 3,2 | FRONT | L3.2 W2.1 H2 foam_4g | 5,193.91 | 5,086.24 | 2.07 | FLAG | BOTH PU (-107.65) |
| icecream up to 3,2 | ROOF | L2.4 W2.1 H2 foam_4g | 6,012.46 | 5,904.34 | 1.80 | FLAG | BOTH PU (-108.09) |
| icecream up to 3,2 | ROOF | L3.2 W2.1 H2 foam_4g | 7,948.72 | 7,805.30 | 1.80 | FLAG | BOTH PU (-143.38) |
| icecream up to 3,2 | SIDES | L2.4 W2.1 H2 foam_4g | 11,676.29 | 11,460.06 | 1.85 | FLAG | BOTH PU (-216.17) |
| icecream up to 3,2 | SIDES | L3.2 W2.1 H2 foam_4g | 15,391.05 | 15,104.21 | 1.86 | FLAG | BOTH PU (-286.76) |
| icecream up to 4.8 | FLOOR | L3.6 W2.3 H2.26 foam_4g | 16,878.07 | 14,730.48 | 12.72 | FLAG accepted cause(s) explain -1 914.11 of -2 147.59; unexplained -233.49 | MISSING_IN_MES 12MM PF PLYWOOD (-1914.11) |
| icecream up to 4.8 | FLOOR | L4.2 W2.3 H2.26 foam_4g | 19,623.24 | 17,122.62 | 12.74 | FLAG accepted cause(s) explain -2 228.75 of -2 500.62; unexplained -271.87 | MISSING_IN_MES 12MM PF PLYWOOD (-2228.75) |
| icecream up to 4.8 | FLOOR | L4.8 W2.3 H2.26 foam_4g | 22,368.42 | 19,514.76 | 12.76 | FLAG accepted cause(s) explain -2 543.40 of -2 853.66; unexplained -310.25 | MISSING_IN_MES 12MM PF PLYWOOD (-2543.40) |
| icecream up to 4.8 | FRONT | L3.6 W2.3 H2.26 foam_4g | 6,365.80 | 6,236.58 | 2.03 | FLAG | BOTH PU (-129.17) |
| icecream up to 4.8 | FRONT | L4.2 W2.3 H2.26 foam_4g | 6,365.80 | 6,236.58 | 2.03 | FLAG | BOTH PU (-129.17) |
| icecream up to 4.8 | FRONT | L4.8 W2.3 H2.26 foam_4g | 6,365.80 | 6,236.58 | 2.03 | FLAG | BOTH PU (-129.17) |
| icecream up to 4.8 | ROOF | L3.6 W2.3 H2.26 foam_4g | 11,763.93 | 11,530.36 | 1.99 | FLAG | BOTH PU (-233.49) |
| icecream up to 4.8 | ROOF | L4.2 W2.3 H2.26 foam_4g | 13,682.88 | 13,410.91 | 1.99 | FLAG | BOTH PU (-271.87) |
| icecream up to 4.8 | ROOF | L4.8 W2.3 H2.26 foam_4g | 15,601.82 | 15,291.46 | 1.99 | FLAG | BOTH PU (-310.25) |
| icecream up to 4.8 | SIDES | L3.6 W2.3 H2.26 foam_4g | 20,493.09 | 20,106.47 | 1.89 | FLAG | BOTH PU (-386.46) |
| icecream up to 4.8 | SIDES | L4.2 W2.3 H2.26 foam_4g | 23,807.09 | 23,356.92 | 1.89 | FLAG | BOTH PU (-449.99) |
| icecream up to 4.8 | SIDES | L4.8 W2.3 H2.26 foam_4g | 27,121.10 | 26,607.37 | 1.89 | FLAG | BOTH PU (-513.52) |
| icecream up to 4.8 | SRD | L3.6 W2.3 H2.26 foam_4g | 7,405.53 | 7,016.58 | 5.25 | FLAG accepted cause(s) explain -259.72 of -388.95; unexplained -129.23 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 2 MES line(s) (-259.72) |
| icecream up to 4.8 | SRD | L4.2 W2.3 H2.26 foam_4g | 7,405.53 | 7,016.58 | 5.25 | FLAG accepted cause(s) explain -259.72 of -388.95; unexplained -129.23 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 2 MES line(s) (-259.72) |
| icecream up to 4.8 | SRD | L4.8 W2.3 H2.26 foam_4g | 7,405.53 | 7,016.58 | 5.25 | FLAG accepted cause(s) explain -259.72 of -388.95; unexplained -129.23 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 2 MES line(s) (-259.72) |

### Unverifiable (40 cells)

- icecream 4.9 up · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream 4.9 up · FLOOR · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream 4.9 up · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream 4.9 up · ROOF · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream 4.9 up · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 3,2 · DRD · EXCEL_NO_PRICE:EPS (2 scenarios)
- icecream up to 3,2 · FLOOR · EXCEL_NO_PRICE:EPS (2 scenarios)
- icecream up to 3,2 · FRONT · EXCEL_NO_PRICE:EPS (2 scenarios)
- icecream up to 3,2 · ROOF · EXCEL_NO_PRICE:EPS (2 scenarios)
- icecream up to 3,2 · SIDES · EXCEL_NO_PRICE:EPS (2 scenarios)
- icecream up to 4.8 · FLOOR · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · ROOF · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · SRD · EXCEL_NO_PRICE:EPS (3 scenarios)

### Known defects — accepted, tracked, awaiting a work order (32 cells)

- icecream up to 3,2 · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (6)
- icecream up to 3,2 · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (2)
- icecream up to 4.8 · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (3)
- icecream up to 4.8 · FLOOR · [TOOL] ICECREAM UP TO 4.8's 12MM PF PLYWOOD floor line (bom 5653) prices only when its draft choice '12MM PF PLYWOOD' is ticked (beside 9MM BIRCH 11203 and 12MM FINN 11207); the audit probe cannot tick a draft choice, so the FLOOR reads it missing (-R1.9k to -R2.5k). A probe limit, not a template defect (Michael, 28 Sep) — still to confirm which choice the calculator starts with. The ALU EXTRUTION FLOOR default was turned OFF in v1.58. — review by 2026-10-31 (12)
- icecream up to 4.8 · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (9)

### Oracle findings and probe notes

- icecream 4.9 up: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- icecream 4.9 up: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- icecream 4.9 up: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default ON (18)
- icecream 4.9 up: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (18)
- icecream up to 3,2: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- icecream up to 3,2: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- icecream up to 3,2: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (12)
- icecream up to 3,2: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (12)
- icecream up to 4.8: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- icecream up to 4.8: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- icecream up to 4.8: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (18)
- icecream up to 4.8: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (18)
