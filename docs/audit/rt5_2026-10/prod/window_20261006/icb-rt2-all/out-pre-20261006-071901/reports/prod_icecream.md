## Costing audit — pack `icecream` — PASS

- Run: 2026-10-06T05:19:13+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-01T18:00:46+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 48 scenarios
- Cells: UNVERIFIABLE 40, ACCEPTED 43, PASS 413, SKIP 116
- Full report: `prod_icecream.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

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

### Known defects — accepted, tracked, awaiting a work order (43 cells)

- icecream up to 3,2 · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (8)
- icecream up to 3,2 · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (2)
- icecream up to 4.8 · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (3)
- icecream up to 4.8 · DRD DOOR FITTINGS · [DATA] PROD icecream 4.8 double door: PU line quantity (+R1.8k) and CSLB HINGES priced differently from Burt's sheet. — review by 2026-10-31 (3)
- icecream up to 4.8 · FLOOR · [TOOL] ICECREAM UP TO 4.8's 12MM PF PLYWOOD floor line (bom 5653) prices only when its draft choice '12MM PF PLYWOOD' is ticked (beside 9MM BIRCH 11203 and 12MM FINN 11207); the audit probe cannot tick a draft choice, so the FLOOR reads it missing (-R1.9k to -R2.5k). A probe limit, not a template defect (Michael, 28 Sep) — still to confirm which choice the calculator starts with. The ALU EXTRUTION FLOOR default was turned OFF in v1.58. — review by 2026-10-31 (15)
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
