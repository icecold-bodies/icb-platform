## Costing audit — pack `smoke` — PASS

- Run: 2026-09-30T19:27:15+00:00 · tolerance 1.0 % · MES: in-process localhost/icb_prodmirror (re-evaluated from the run of 2026-09-30T19:15:58+00:00)
- Golden: 2026-09-25T14:09:05+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 18 scenarios
- Cells: UNVERIFIABLE 9, ACCEPTED 15, PASS 171, SKIP 39
- Full report: `mirror_afterF_smoke.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)
- ⚠ accepted list: accepted_differences.prod.candidateF.yaml

### Unverifiable (9 cells)

- UP TO 4.8 MT FREEZER  (2 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- UP TO 4.8 MT FREEZER  (2 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- UP TO 4.8 MT FREEZER  (2 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)

### Known defects — accepted, tracked, awaiting a work order (15 cells)

- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [DATA] SMALL MOUNTING BRACKET priced differently from Burt's sheet on FREEZER MEDIUM (-R126), prod as dev. — review by 2026-10-31 (6)
- icecream up to 4.8 · DRD DOOR FITTINGS · [DATA] PROD icecream 4.8 double door: PU line quantity (+R1.8k) and CSLB HINGES priced differently from Burt's sheet. — review by 2026-10-31 (3)
- icecream up to 4.8 · FLOOR · [TOOL] ICECREAM UP TO 4.8's 12MM PF PLYWOOD floor line (bom 5653) prices only when its draft choice '12MM PF PLYWOOD' is ticked (beside 9MM BIRCH 11203 and 12MM FINN 11207); the audit probe cannot tick a draft choice, so the FLOOR reads it missing (-R1.9k to -R2.5k). A probe limit, not a template defect (Michael, 28 Sep) — still to confirm which choice the calculator starts with. The ALU EXTRUTION FLOOR default was turned OFF in v1.58. — review by 2026-10-31 (6)

### Oracle findings and probe notes

- UP TO 5.5 CHILLER AND 2.3 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (6)
