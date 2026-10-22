## Costing audit — pack `icecream` — PASS

- Run: 2026-10-22T10:38:21+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-19T12:50:08+00:00 · workbook month 2026-09 · GRP sha256 `ed4d57bcd6d5` · 48 scenarios
- Cells: UNVERIFIABLE 40, ACCEPTED 40, PASS 416, SKIP 116
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

### Known defects — accepted, tracked, awaiting a work order (15 cells)

- icecream up to 4.8 · FLOOR · [PROBE] ICECREAM UP TO 4.8's 12MM PF PLYWOOD floor line (bom 5653) prices only when its draft choice is ticked; the audit probe cannot tick a draft choice, so the FLOOR reads it missing. A probe limit, not a template defect (Michael, 28 Sep). — review by 2026-11-30 (15)

### Tolerated differences (25 cells)

- icecream up to 3,2 · DRD · [BURT SLIP] Burt's rear-door TAPPING row prices the buffer plate, not the tapping blocks: 'icecream up to 3,2'!E41 and 'icecream up to 4.8'!E45 = '[2]SRD FLOOR PLATE'!$F$24*3 instead of TAPING BLOCKS (+R259.72 per door section on Burt's side). MES is right. Clears with Burt's fix list B-01, B-02. — review by 2026-11-30 (8)
- icecream up to 3,2 · SRD · [BURT SLIP] Burt's rear-door TAPPING row prices the buffer plate, not the tapping blocks: 'icecream up to 3,2'!E41 and 'icecream up to 4.8'!E45 = '[2]SRD FLOOR PLATE'!$F$24*3 instead of TAPING BLOCKS (+R259.72 per door section on Burt's side). MES is right. Clears with Burt's fix list B-01, B-02. — review by 2026-11-30 (2)
- icecream up to 4.8 · DRD · [BURT SLIP] Burt's rear-door TAPPING row prices the buffer plate, not the tapping blocks: 'icecream up to 3,2'!E41 and 'icecream up to 4.8'!E45 = '[2]SRD FLOOR PLATE'!$F$24*3 instead of TAPING BLOCKS (+R259.72 per door section on Burt's side). MES is right. Clears with Burt's fix list B-01, B-02. — review by 2026-11-30 (3)
- icecream up to 4.8 · SRD · [BURT SLIP] Burt's rear-door TAPPING row prices the buffer plate, not the tapping blocks: 'icecream up to 3,2'!E41 and 'icecream up to 4.8'!E45 = '[2]SRD FLOOR PLATE'!$F$24*3 instead of TAPING BLOCKS (+R259.72 per door section on Burt's side). MES is right. Clears with Burt's fix list B-01, B-02. — review by 2026-11-30 (12)

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
