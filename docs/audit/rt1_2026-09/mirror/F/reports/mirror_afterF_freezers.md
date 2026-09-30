## Costing audit — pack `freezers` — FAIL

- Run: 2026-09-30T19:16:06+00:00 · tolerance 1.0 % · MES: in-process localhost/icb_prodmirror
- Golden: 2026-09-25T14:14:16+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 54 scenarios
- Cells: FLAG 27, UNVERIFIABLE 27, ACCEPTED 24, PASS 495, SKIP 117
- Full report: `mirror_afterF_freezers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unaccepted differences (27)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| 4.9 & UP FREEZER BODY (2 | FRONT | L4.9 W2.6 H2.56 foam_4g | 6,052.04 | 6,124.76 | 1.20 | FLAG | BOTH PU (+64.58) |
| 4.9 & UP FREEZER BODY (2 | FRONT | L6.5 W2.6 H2.56 foam_4g | 6,052.04 | 6,124.76 | 1.20 | FLAG | BOTH PU (+64.58) |
| 4.9 & UP FREEZER BODY (2 | FRONT | L8.2 W2.6 H2.56 foam_4g | 6,052.04 | 6,124.76 | 1.20 | FLAG | BOTH PU (+64.58) |
| 4.9 & UP FREEZER BODY (2 | ROOF | L4.9 W2.6 H2.56 foam_4g | 13,565.13 | 13,783.42 | 1.61 | FLAG | BOTH PU (+218.37) |
| 4.9 & UP FREEZER BODY (2 | ROOF | L6.5 W2.6 H2.56 foam_4g | 17,903.61 | 18,192.45 | 1.61 | FLAG | BOTH PU (+288.97) |
| 4.9 & UP FREEZER BODY (2 | ROOF | L8.2 W2.6 H2.56 foam_4g | 22,513.24 | 22,877.05 | 1.62 | FLAG | BOTH PU (+363.96) |
| 4.9 & UP FREEZER BODY (2 | SIDES | L4.9 W2.6 H2.56 foam_4g | 23,605.66 | 23,867.46 | 1.11 | FLAG | BOTH PU (+262.05) |
| 4.9 & UP FREEZER BODY (2 | SIDES | L6.5 W2.6 H2.56 foam_4g | 31,113.56 | 31,459.98 | 1.11 | FLAG | BOTH PU (+346.75) |
| 4.9 & UP FREEZER BODY (2 | SIDES | L8.2 W2.6 H2.56 foam_4g | 39,090.70 | 39,527.04 | 1.12 | FLAG | BOTH PU (+436.76) |
| UP TO 2,3 MTR FREEZER | DRD | L1.8 W1.68 H1.39 foam_4g | 3,923.40 | 3,990.40 | 1.71 | FLAG accepted cause(s) explain +0.00 of +67.00; unexplained +67.00 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 1 MES line(s) (-468.00) |
| UP TO 2,3 MTR FREEZER | DRD | L2.31 W1.68 H1.39 foam_4g | 3,923.40 | 3,990.40 | 1.71 | FLAG accepted cause(s) explain +0.00 of +67.00; unexplained +67.00 | GROUP_DIFF 130*62MM TAPPING BLOCKS ~ 1 MES line(s) (-468.00) |
| UP TO 2,3 MTR FREEZER | FRONT | L1.8 W1.68 H1.39 foam_4g | 3,165.41 | 3,229.98 | 2.04 | FLAG | BOTH PU (+64.58) |
| UP TO 2,3 MTR FREEZER | FRONT | L2.31 W1.68 H1.39 foam_4g | 3,165.41 | 3,229.98 | 2.04 | FLAG | BOTH PU (+64.58) |
| UP TO 2,3 MTR FREEZER | SIDES | L1.8 W1.68 H1.39 foam_4g | 5,834.44 | 5,932.34 | 1.68 | FLAG | BOTH PU (+97.94) |
| UP TO 2,3 MTR FREEZER | SIDES | L2.31 W1.68 H1.39 foam_4g | 7,363.74 | 7,488.64 | 1.70 | FLAG | BOTH PU (+124.93) |
| UP TO 4.8 MT FREEZER  (2 | FRONT | L3 W2.5 H2.4 foam_4g | 5,691.12 | 5,755.65 | 1.13 | FLAG | BOTH PU (+64.58) |
| UP TO 4.8 MT FREEZER  (2 | FRONT | L4.2 W2.5 H2.4 foam_4g | 5,691.12 | 5,755.65 | 1.13 | FLAG | BOTH PU (+64.58) |
| UP TO 4.8 MT FREEZER  (2 | FRONT | L4.8 W2.5 H2.4 foam_4g | 5,691.12 | 5,755.65 | 1.13 | FLAG | BOTH PU (+64.58) |
| UP TO 4.8 MT FREEZER  (2 | FRONT | L5.6 W2.5 H2.4 foam_4g | 5,691.12 | 5,755.65 | 1.13 | FLAG | BOTH PU (+64.58) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L3 W2.5 H2.4 foam_4g | 7,269.63 | 7,371.84 | 1.41 | FLAG | BOTH PU (+102.26) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L4.2 W2.5 H2.4 foam_4g | 10,085.26 | 10,227.69 | 1.41 | FLAG | BOTH PU (+142.49) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L4.8 W2.5 H2.4 foam_4g | 11,493.08 | 11,655.61 | 1.41 | FLAG | BOTH PU (+162.61) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L5.6 W2.5 H2.4 foam_4g | 13,370.16 | 13,559.50 | 1.42 | FLAG | BOTH PU (+189.44) |
| UP TO 4.8 MT FREEZER  (2 | SIDES | L3 W2.5 H2.4 foam_4g | 14,190.09 | 14,351.40 | 1.14 | FLAG | BOTH PU (+161.46) |
| UP TO 4.8 MT FREEZER  (2 | SIDES | L4.2 W2.5 H2.4 foam_4g | 19,628.30 | 19,853.09 | 1.15 | FLAG | BOTH PU (+225.00) |
| UP TO 4.8 MT FREEZER  (2 | SIDES | L4.8 W2.5 H2.4 foam_4g | 22,347.41 | 22,603.93 | 1.15 | FLAG | BOTH PU (+256.76) |
| UP TO 4.8 MT FREEZER  (2 | SIDES | L5.6 W2.5 H2.4 foam_4g | 25,972.88 | 26,271.72 | 1.15 | FLAG | BOTH PU (+299.11) |

### Unverifiable (27 cells)

- 4.9 & UP FREEZER BODY (2 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- 4.9 & UP FREEZER BODY (2 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- 4.9 & UP FREEZER BODY (2 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)
- UP TO 2,3 MTR FREEZER · DRD · EXCEL_NO_PRICE:EPS (2 scenarios)
- UP TO 2,3 MTR FREEZER · FRONT · EXCEL_NO_PRICE:EPS (2 scenarios)
- UP TO 2,3 MTR FREEZER · SIDES · EXCEL_NO_PRICE:EPS (2 scenarios)
- UP TO 4.8 MT FREEZER  (2 · DRD · EXCEL_NO_PRICE:EPS (4 scenarios)
- UP TO 4.8 MT FREEZER  (2 · FRONT · EXCEL_NO_PRICE:EPS (4 scenarios)
- UP TO 4.8 MT FREEZER  (2 · SIDES · EXCEL_NO_PRICE:EPS (4 scenarios)

### Known defects — accepted, tracked, awaiting a work order (24 cells)

- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [DATA] SMALL MOUNTING BRACKET priced differently from Burt's sheet on FREEZER MEDIUM (-R126), prod as dev. — review by 2026-10-31 (24)

### Oracle findings and probe notes

- UP TO 2,3 MTR FREEZER: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (12)
