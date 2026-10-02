## Costing audit — pack `freezers` — PASS

- Run: 2026-10-02T09:33:45+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-01T17:59:03+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 54 scenarios
- Cells: UNVERIFIABLE 27, ACCEPTED 24, PASS 522, SKIP 117
- Full report: `prod_freezers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

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
