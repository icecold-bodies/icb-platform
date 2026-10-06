## Costing audit — pack `freezers` — PASS

- Run: 2026-10-05T13:54:19+00:00 · tolerance 1.0 % · MES: in-process icb_prodmirror (read only)
- Golden: 2026-10-05T13:49:45+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 54 scenarios
- Cells: ACCEPTED 24, PASS 549, SKIP 117
- Full report: `mirror_freezers.html` (CI artifact)

### Known defects — accepted, tracked, awaiting a work order (24 cells)

- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [DATA] SMALL MOUNTING BRACKET priced differently from Burt's sheet on FREEZER MEDIUM (-R126), prod as dev. — review by 2026-10-31 (24)

### Oracle findings and probe notes

- UP TO 2,3 MTR FREEZER: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (12)
