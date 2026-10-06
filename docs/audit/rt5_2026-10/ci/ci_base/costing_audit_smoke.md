## Costing audit — pack `smoke` — PASS

- Run: 2026-10-05T13:55:14+00:00 · tolerance 1.0 % · MES: in-process localhost/icb_test
- Golden: 2026-10-01T17:54:49+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 18 scenarios
- Cells: UNVERIFIABLE 9, ACCEPTED 15, PASS 165, SKIP 45
- Full report: `costing_audit_smoke.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unverifiable (9 cells)

- UP TO 4.8 MT FREEZER  (2 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- UP TO 4.8 MT FREEZER  (2 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- UP TO 4.8 MT FREEZER  (2 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)

### Known defects — accepted, tracked, awaiting a work order (15 cells)

- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [DATA] SMALL MOUNTING BRACKET priced differently from Burt's sheet on FREEZER MEDIUM (-R126), prod as dev. — review by 2026-10-31 (6)
- UP TO 5.5 CHILLER AND 2.3 WIDE · DRD DOOR FITTINGS · [BURT] Burt's UP TO 5.5 CHILLER sheet charges no 2317 DOOR RUBBER on its rear doors — the line's totals (F60 single, F97 double) are a literal 0 in every version of his file (25 Aug, 21 Sep) — while MES charges it (CHILLER MEDIUM bom 3216: 11.174 m x R60.18 = R672.45 on the double door). The golden this replaced was built on a local copy that charged it. Burt to confirm whether the CHILLER MEDIUM rear doors take the 2317 rubber. — review by 2026-10-31 (3)
- icecream up to 4.8 · FLOOR · [TOOL] ICECREAM UP TO 4.8's 12MM PF PLYWOOD floor line (bom 5653) prices only when its draft choice '12MM PF PLYWOOD' is ticked (beside 9MM BIRCH 11203 and 12MM FINN 11207); the audit probe cannot tick a draft choice, so the FLOOR reads it missing (-R1.9k to -R2.5k). A probe limit, not a template defect (Michael, 28 Sep) — still to confirm which choice the calculator starts with. The ALU EXTRUTION FLOOR default was turned OFF in v1.58. — review by 2026-10-31 (6)

### Oracle findings and probe notes

- UP TO 5.5 CHILLER AND 2.3 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (6)
