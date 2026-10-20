## Costing audit — pack `chillers` — PASS

- Run: 2026-10-20T11:11:22+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-01T17:57:03+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 56 scenarios
- Cells: PASS 590, SKIP 126
- Full report: `prod_chillers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Oracle findings and probe notes

- 4.9 & UP CHILLER AND 2.5 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (32)
- UP TO 2.3 CHILLER BODY: MES master '1ST ROW KICKPLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2.3 CHILLER BODY: MES master '2ND ROW KICKPLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2.3 CHILLER BODY: MES master 'RICE GRAIN FLOOR' has no flag on the sheet — left at body default OFF (12)
- UP TO 5.5 CHILLER AND 2.3 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (12)
