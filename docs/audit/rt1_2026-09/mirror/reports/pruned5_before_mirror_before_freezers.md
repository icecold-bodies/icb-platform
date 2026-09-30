## Costing audit — pack `freezers` — FAIL

- Run: 2026-09-30T14:41:53+00:00 · tolerance 1.0 % · MES: in-process localhost/icb_prodmirror (re-evaluated from the run of 2026-09-30T14:33:39+00:00)
- Golden: 2026-09-25T14:14:16+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 54 scenarios
- Cells: PRESENCE 9, UNVERIFIABLE 27, ACCEPTED 24, PASS 522, SKIP 108
- Full report: `mirror_before_freezers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)
- ⚠ accepted list: accepted_differences.prod.pruned5.yaml

### Unaccepted differences (9)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| 4.9 & UP FREEZER BODY (2 | REAR FRAME + FLOOR PLATE | L4.9 W2.6 H2.56 srd | 0.00 | 5,432.11 |  | PRESENCE EXTRA_IN_MES |  |
| 4.9 & UP FREEZER BODY (2 | REAR FRAME + FLOOR PLATE | L6.5 W2.6 H2.56 srd | 0.00 | 5,432.11 |  | PRESENCE EXTRA_IN_MES |  |
| 4.9 & UP FREEZER BODY (2 | REAR FRAME + FLOOR PLATE | L8.2 W2.6 H2.56 srd | 0.00 | 5,432.11 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 2,3 MTR FREEZER | REAR FRAME + FLOOR PLATE | L1.8 W1.68 H1.39 srd | 0.00 | 2,249.35 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 2,3 MTR FREEZER | REAR FRAME + FLOOR PLATE | L2.31 W1.68 H1.39 srd | 0.00 | 2,249.35 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 4.8 MT FREEZER  (2 | REAR FRAME + FLOOR PLATE | L3 W2.5 H2.4 srd | 0.00 | 4,633.77 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 4.8 MT FREEZER  (2 | REAR FRAME + FLOOR PLATE | L4.2 W2.5 H2.4 srd | 0.00 | 4,633.77 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 4.8 MT FREEZER  (2 | REAR FRAME + FLOOR PLATE | L4.8 W2.5 H2.4 srd | 0.00 | 4,633.77 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 4.8 MT FREEZER  (2 | REAR FRAME + FLOOR PLATE | L5.6 W2.5 H2.4 srd | 0.00 | 4,633.77 |  | PRESENCE EXTRA_IN_MES |  |

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
