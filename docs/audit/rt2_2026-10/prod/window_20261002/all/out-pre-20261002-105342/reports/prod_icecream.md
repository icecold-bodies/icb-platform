## Costing audit — pack `icecream` — FAIL

- Run: 2026-10-02T08:53:55+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-09-25T14:16:10+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 48 scenarios
- Cells: FLAG 34, UNVERIFIABLE 40, ACCEPTED 50, PASS 384, SKIP 104
- Full report: `prod_icecream.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unaccepted differences (34)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| icecream 4.9 up | DRD | L4.9 W2.6 H2.6 foam_4g | 7,966.03 | 8,354.86 | 4.88 | FLAG accepted cause(s) explain +259.72 of +388.83; unexplained +129.11 | EXTRA_IN_MES 3MM ALU BUFFER PLATE (+493.72) |
| icecream 4.9 up | DRD | L6.7 W2.6 H2.6 foam_4g | 7,966.03 | 8,354.86 | 4.88 | FLAG accepted cause(s) explain +259.72 of +388.83; unexplained +129.11 | EXTRA_IN_MES 3MM ALU BUFFER PLATE (+493.72) |
| icecream 4.9 up | DRD | L8 W2.6 H2.6 foam_4g | 7,966.03 | 8,354.86 | 4.88 | FLAG accepted cause(s) explain +259.72 of +388.83; unexplained +129.11 | EXTRA_IN_MES 3MM ALU BUFFER PLATE (+493.72) |
| icecream 4.9 up | FRONT | L4.9 W2.6 H2.6 foam_4g | 7,027.98 | 7,157.09 | 1.84 | FLAG | BOTH PU (+129.17) |
| icecream 4.9 up | FRONT | L6.7 W2.6 H2.6 foam_4g | 7,027.98 | 7,157.09 | 1.84 | FLAG | BOTH PU (+129.17) |
| icecream 4.9 up | FRONT | L8 W2.6 H2.6 foam_4g | 7,027.98 | 7,157.09 | 1.84 | FLAG | BOTH PU (+129.17) |
| icecream 4.9 up | ROOF | L4.9 W2.6 H2.6 foam_4g | 15,088.12 | 15,360.96 | 1.81 | FLAG | BOTH PU (+272.97) |
| icecream 4.9 up | ROOF | L6.7 W2.6 H2.6 foam_4g | 20,537.66 | 20,909.72 | 1.81 | FLAG | BOTH PU (+372.24) |
| icecream 4.9 up | ROOF | L8 W2.6 H2.6 foam_4g | 24,473.44 | 24,917.15 | 1.81 | FLAG | BOTH PU (+443.93) |
| icecream 4.9 up | SIDES | L4.9 W2.6 H2.6 foam_4g | 29,063.74 | 29,587.59 | 1.80 | FLAG | BOTH PU (+524.10) |
| icecream 4.9 up | SIDES | L6.7 W2.6 H2.6 foam_4g | 39,491.18 | 40,205.53 | 1.81 | FLAG | BOTH PU (+714.69) |
| icecream 4.9 up | SIDES | L8 W2.6 H2.6 foam_4g | 47,022.11 | 47,874.04 | 1.81 | FLAG | BOTH PU (+852.33) |
| icecream up to 3,2 | DRD | L2.4 W2.1 H2 foam_4g | 6,222.13 | 6,563.75 | 5.49 | FLAG accepted cause(s) explain +234.00 of +341.62; unexplained +107.62 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 1 MES line(s) (-805.72) |
| icecream up to 3,2 | DRD | L3.2 W2.1 H2 foam_4g | 6,222.13 | 6,563.75 | 5.49 | FLAG accepted cause(s) explain +234.00 of +341.62; unexplained +107.62 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 1 MES line(s) (-805.72) |
| icecream up to 3,2 | FLOOR | L2.4 W2.1 H2 foam_4g | 9,797.97 | 9,906.05 | 1.10 | FLAG | BOTH PU (+108.09) |
| icecream up to 3,2 | FLOOR | L3.2 W2.1 H2 foam_4g | 12,665.26 | 12,808.64 | 1.13 | FLAG | BOTH PU (+143.38) |
| icecream up to 3,2 | FRONT | L2.4 W2.1 H2 foam_4g | 5,086.26 | 5,193.88 | 2.12 | FLAG | BOTH PU (+107.65) |
| icecream up to 3,2 | FRONT | L3.2 W2.1 H2 foam_4g | 5,086.26 | 5,193.88 | 2.12 | FLAG | BOTH PU (+107.65) |
| icecream up to 3,2 | ROOF | L2.4 W2.1 H2 foam_4g | 5,904.37 | 6,012.42 | 1.83 | FLAG | BOTH PU (+108.09) |
| icecream up to 3,2 | ROOF | L3.2 W2.1 H2 foam_4g | 7,805.34 | 7,948.68 | 1.84 | FLAG | BOTH PU (+143.38) |
| icecream up to 3,2 | SIDES | L2.4 W2.1 H2 foam_4g | 11,460.12 | 11,676.23 | 1.89 | FLAG | BOTH PU (+216.17) |
| icecream up to 3,2 | SIDES | L3.2 W2.1 H2 foam_4g | 15,104.29 | 15,390.96 | 1.90 | FLAG | BOTH PU (+286.76) |
| icecream up to 4.8 | FLOOR | L3.6 W2.3 H2.26 foam_4g | 16,644.59 | 14,963.97 | 10.10 | FLAG accepted cause(s) explain -1 914.11 of -1 680.62; unexplained +233.49 | MISSING_IN_MES 12MM PF PLYWOOD (-1914.11) |
| icecream up to 4.8 | FLOOR | L4.2 W2.3 H2.26 foam_4g | 19,351.38 | 17,394.49 | 10.11 | FLAG accepted cause(s) explain -2 228.75 of -1 956.89; unexplained +271.87 | MISSING_IN_MES 12MM PF PLYWOOD (-2228.75) |
| icecream up to 4.8 | FLOOR | L4.8 W2.3 H2.26 foam_4g | 22,058.17 | 19,825.01 | 10.12 | FLAG accepted cause(s) explain -2 543.40 of -2 233.16; unexplained +310.25 | MISSING_IN_MES 12MM PF PLYWOOD (-2543.40) |
| icecream up to 4.8 | FRONT | L3.6 W2.3 H2.26 foam_4g | 6,236.63 | 6,365.76 | 2.07 | FLAG | BOTH PU (+129.17) |
| icecream up to 4.8 | FRONT | L4.2 W2.3 H2.26 foam_4g | 6,236.63 | 6,365.76 | 2.07 | FLAG | BOTH PU (+129.17) |
| icecream up to 4.8 | FRONT | L4.8 W2.3 H2.26 foam_4g | 6,236.63 | 6,365.76 | 2.07 | FLAG | BOTH PU (+129.17) |
| icecream up to 4.8 | ROOF | L3.6 W2.3 H2.26 foam_4g | 11,530.44 | 11,763.85 | 2.02 | FLAG | BOTH PU (+233.49) |
| icecream up to 4.8 | ROOF | L4.2 W2.3 H2.26 foam_4g | 13,411.01 | 13,682.78 | 2.03 | FLAG | BOTH PU (+271.87) |
| icecream up to 4.8 | ROOF | L4.8 W2.3 H2.26 foam_4g | 15,291.57 | 15,601.71 | 2.03 | FLAG | BOTH PU (+310.25) |
| icecream up to 4.8 | SIDES | L3.6 W2.3 H2.26 foam_4g | 20,106.63 | 20,492.94 | 1.92 | FLAG | BOTH PU (+386.46) |
| icecream up to 4.8 | SIDES | L4.2 W2.3 H2.26 foam_4g | 23,357.10 | 23,806.91 | 1.93 | FLAG | BOTH PU (+449.99) |
| icecream up to 4.8 | SIDES | L4.8 W2.3 H2.26 foam_4g | 26,607.58 | 27,120.89 | 1.93 | FLAG | BOTH PU (+513.52) |

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
- icecream up to 4.8 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · FLOOR · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · ROOF · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)

### Known defects — accepted, tracked, awaiting a work order (50 cells)

- icecream 4.9 up · DRD · [DATA] PROD icecream bodies carry a 3MM ALU BUFFER PLATE line in the rear-door section that Burt's sheets do not (+R494 on a double door, +R235 on icecream 3,2's single door). — review by 2026-10-31 (9)
- icecream 4.9 up · SRD · [DATA] PROD icecream bodies carry a 3MM ALU BUFFER PLATE line in the rear-door section that Burt's sheets do not (+R494 on a double door, +R235 on icecream 3,2's single door). — review by 2026-10-31 (3)
- icecream up to 3,2 · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (6)
- icecream up to 3,2 · SRD · [DATA] PROD icecream bodies carry a 3MM ALU BUFFER PLATE line in the rear-door section that Burt's sheets do not (+R494 on a double door, +R235 on icecream 3,2's single door). — review by 2026-10-31 (2)
- icecream up to 4.8 · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (3)
- icecream up to 4.8 · DRD DOOR FITTINGS · [DATA] PROD icecream 4.8 double door: PU line quantity (+R1.8k) and CSLB HINGES priced differently from Burt's sheet. — review by 2026-10-31 (15)
- icecream up to 4.8 · FLOOR · [TOOL] ICECREAM UP TO 4.8's 12MM PF PLYWOOD floor line (bom 5653) prices only when its draft choice '12MM PF PLYWOOD' is ticked (beside 9MM BIRCH 11203 and 12MM FINN 11207); the audit probe cannot tick a draft choice, so the FLOOR reads it missing (-R1.9k to -R2.5k). A probe limit, not a template defect (Michael, 28 Sep) — still to confirm which choice the calculator starts with. The ALU EXTRUTION FLOOR default was turned OFF in v1.58. — review by 2026-10-31 (12)

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
