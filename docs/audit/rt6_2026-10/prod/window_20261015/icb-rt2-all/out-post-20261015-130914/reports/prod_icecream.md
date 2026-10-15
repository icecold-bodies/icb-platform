## Costing audit — pack `icecream` — FAIL

- Run: 2026-10-15T11:09:26+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-01T18:00:46+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 48 scenarios
- Cells: FLAG 40, UNVERIFIABLE 40, ACCEPTED 25, PASS 391, SKIP 116
- Full report: `prod_icecream.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unaccepted differences (40)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| icecream 4.9 up | FLOOR | L4.9 W2.6 H2.6 all_pu | 20,756.11 | 21,008.71 | 1.22 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+252.60) |
| icecream 4.9 up | FLOOR | L6.7 W2.6 H2.6 all_pu | 27,950.06 | 28,287.63 | 1.21 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+337.58) |
| icecream 4.9 up | FLOOR | L8 W2.6 H2.6 all_pu | 33,145.68 | 33,544.64 | 1.20 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+398.96) |
| icecream 4.9 up | FLOOR | L4.9 W2.6 H2.6 as_sheet | 20,756.11 | 21,008.71 | 1.22 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+252.60) |
| icecream 4.9 up | FLOOR | L6.7 W2.6 H2.6 as_sheet | 27,950.06 | 28,287.63 | 1.21 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+337.58) |
| icecream 4.9 up | FLOOR | L8 W2.6 H2.6 as_sheet | 33,145.68 | 33,544.64 | 1.20 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+398.96) |
| icecream 4.9 up | FLOOR | L4.9 W2.6 H2.6 drd | 20,756.11 | 21,008.71 | 1.22 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+252.60) |
| icecream 4.9 up | FLOOR | L6.7 W2.6 H2.6 drd | 27,950.06 | 28,287.63 | 1.21 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+337.58) |
| icecream 4.9 up | FLOOR | L8 W2.6 H2.6 drd | 33,145.68 | 33,544.64 | 1.20 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+398.96) |
| icecream 4.9 up | FLOOR | L4.9 W2.6 H2.6 foam_4g | 22,542.94 | 22,795.54 | 1.12 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+252.60) |
| icecream 4.9 up | FLOOR | L6.7 W2.6 H2.6 foam_4g | 30,386.64 | 30,724.22 | 1.11 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+337.58) |
| icecream 4.9 up | FLOOR | L8 W2.6 H2.6 foam_4g | 36,051.54 | 36,450.49 | 1.11 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+398.96) |
| icecream 4.9 up | FLOOR | L4.9 W2.6 H2.6 srd | 20,756.11 | 21,008.71 | 1.22 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+252.60) |
| icecream 4.9 up | FLOOR | L6.7 W2.6 H2.6 srd | 27,950.06 | 28,287.63 | 1.21 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+337.58) |
| icecream 4.9 up | FLOOR | L8 W2.6 H2.6 srd | 33,145.68 | 33,544.64 | 1.20 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+398.96) |
| icecream up to 3,2 | FLOOR | L2.4 W2.1 H2 all_pu | 9,021.66 | 9,122.50 | 1.12 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+100.84) |
| icecream up to 3,2 | FLOOR | L3.2 W2.1 H2 all_pu | 11,635.46 | 11,766.18 | 1.12 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+130.72) |
| icecream up to 3,2 | FLOOR | L2.4 W2.1 H2 as_sheet | 9,021.66 | 9,122.50 | 1.12 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+100.84) |
| icecream up to 3,2 | FLOOR | L3.2 W2.1 H2 as_sheet | 11,635.46 | 11,766.18 | 1.12 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+130.72) |
| icecream up to 3,2 | FLOOR | L2.4 W2.1 H2 drd | 9,021.66 | 9,122.50 | 1.12 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+100.84) |
| icecream up to 3,2 | FLOOR | L3.2 W2.1 H2 drd | 11,635.46 | 11,766.18 | 1.12 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+130.72) |
| icecream up to 3,2 | FLOOR | L2.4 W2.1 H2 foam_4g | 9,906.05 | 10,006.89 | 1.02 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+100.84) |
| icecream up to 3,2 | FLOOR | L3.2 W2.1 H2 foam_4g | 12,808.64 | 12,939.36 | 1.02 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+130.72) |
| icecream up to 3,2 | FLOOR | L2.4 W2.1 H2 srd | 9,021.66 | 9,122.50 | 1.12 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+100.84) |
| icecream up to 3,2 | FLOOR | L3.2 W2.1 H2 srd | 11,635.46 | 11,766.18 | 1.12 | FLAG | PRICE_DIFF 2*300 INT LAMINATION (+130.72) |
| icecream up to 4.8 | FLOOR | L3.6 W2.3 H2.26 all_pu | 14,967.61 | 13,227.59 | 11.62 | FLAG accepted cause(s) explain -1 914.11 of -1 740.02; unexplained +174.09 | MISSING_IN_MES 12MM PF PLYWOOD (-1914.11) |
| icecream up to 4.8 | FLOOR | L4.2 W2.3 H2.26 all_pu | 17,398.73 | 15,369.86 | 11.66 | FLAG accepted cause(s) explain -2 228.75 of -2 028.87; unexplained +199.88 | MISSING_IN_MES 12MM PF PLYWOOD (-2228.75) |
| icecream up to 4.8 | FLOOR | L4.8 W2.3 H2.26 all_pu | 19,829.85 | 17,512.13 | 11.69 | FLAG accepted cause(s) explain -2 543.40 of -2 317.72; unexplained +225.68 | MISSING_IN_MES 12MM PF PLYWOOD (-2543.40) |
| icecream up to 4.8 | FLOOR | L3.6 W2.3 H2.26 as_sheet | 14,967.61 | 13,227.59 | 11.62 | FLAG accepted cause(s) explain -1 914.11 of -1 740.02; unexplained +174.09 | MISSING_IN_MES 12MM PF PLYWOOD (-1914.11) |
| icecream up to 4.8 | FLOOR | L4.2 W2.3 H2.26 as_sheet | 17,398.73 | 15,369.86 | 11.66 | FLAG accepted cause(s) explain -2 228.75 of -2 028.87; unexplained +199.88 | MISSING_IN_MES 12MM PF PLYWOOD (-2228.75) |
| icecream up to 4.8 | FLOOR | L4.8 W2.3 H2.26 as_sheet | 19,829.85 | 17,512.13 | 11.69 | FLAG accepted cause(s) explain -2 543.40 of -2 317.72; unexplained +225.68 | MISSING_IN_MES 12MM PF PLYWOOD (-2543.40) |
| icecream up to 4.8 | FLOOR | L3.6 W2.3 H2.26 drd | 14,967.61 | 13,227.59 | 11.62 | FLAG accepted cause(s) explain -1 914.11 of -1 740.02; unexplained +174.09 | MISSING_IN_MES 12MM PF PLYWOOD (-1914.11) |
| icecream up to 4.8 | FLOOR | L4.2 W2.3 H2.26 drd | 17,398.73 | 15,369.86 | 11.66 | FLAG accepted cause(s) explain -2 228.75 of -2 028.87; unexplained +199.88 | MISSING_IN_MES 12MM PF PLYWOOD (-2228.75) |
| icecream up to 4.8 | FLOOR | L4.8 W2.3 H2.26 drd | 19,829.85 | 17,512.13 | 11.69 | FLAG accepted cause(s) explain -2 543.40 of -2 317.72; unexplained +225.68 | MISSING_IN_MES 12MM PF PLYWOOD (-2543.40) |
| icecream up to 4.8 | FLOOR | L3.6 W2.3 H2.26 foam_4g | 16,878.07 | 15,138.06 | 10.31 | FLAG accepted cause(s) explain -1 914.11 of -1 740.01; unexplained +174.09 | MISSING_IN_MES 12MM PF PLYWOOD (-1914.11) |
| icecream up to 4.8 | FLOOR | L4.2 W2.3 H2.26 foam_4g | 19,623.24 | 17,594.37 | 10.34 | FLAG accepted cause(s) explain -2 228.75 of -2 028.87; unexplained +199.88 | MISSING_IN_MES 12MM PF PLYWOOD (-2228.75) |
| icecream up to 4.8 | FLOOR | L4.8 W2.3 H2.26 foam_4g | 22,368.42 | 20,050.69 | 10.36 | FLAG accepted cause(s) explain -2 543.40 of -2 317.73; unexplained +225.68 | MISSING_IN_MES 12MM PF PLYWOOD (-2543.40) |
| icecream up to 4.8 | FLOOR | L3.6 W2.3 H2.26 srd | 14,967.61 | 13,227.59 | 11.62 | FLAG accepted cause(s) explain -1 914.11 of -1 740.02; unexplained +174.09 | MISSING_IN_MES 12MM PF PLYWOOD (-1914.11) |
| icecream up to 4.8 | FLOOR | L4.2 W2.3 H2.26 srd | 17,398.73 | 15,369.86 | 11.66 | FLAG accepted cause(s) explain -2 228.75 of -2 028.87; unexplained +199.88 | MISSING_IN_MES 12MM PF PLYWOOD (-2228.75) |
| icecream up to 4.8 | FLOOR | L4.8 W2.3 H2.26 srd | 19,829.85 | 17,512.13 | 11.69 | FLAG accepted cause(s) explain -2 543.40 of -2 317.72; unexplained +225.68 | MISSING_IN_MES 12MM PF PLYWOOD (-2543.40) |

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

### Known defects — accepted, tracked, awaiting a work order (25 cells)

- icecream up to 3,2 · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (8)
- icecream up to 3,2 · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (2)
- icecream up to 4.8 · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (3)
- icecream up to 4.8 · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (12)

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
