## Costing audit — pack `chillers` — PASS

- Run: 2026-10-02T12:26:13+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-01T17:57:03+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 56 scenarios
- Cells: ACCEPTED 9, PASS 581, SKIP 126
- Full report: `prod_chillers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Known defects — accepted, tracked, awaiting a work order (9 cells)

- UP TO 5.5 CHILLER AND 2.3 WIDE · DRD DOOR FITTINGS · [BURT] Burt's UP TO 5.5 CHILLER sheet charges no 2317 DOOR RUBBER on its rear doors — the line's totals (F60 single, F97 double) are a literal 0 in every version of his file (25 Aug, 21 Sep) — while MES charges it (CHILLER MEDIUM bom 3216: 11.174 m x R60.18 = R672.45 on the double door). The golden this replaced was built on a local copy that charged it. Burt to confirm whether the CHILLER MEDIUM rear doors take the 2317 rubber. — review by 2026-10-31 (9)

### Oracle findings and probe notes

- 4.9 & UP CHILLER AND 2.5 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (32)
- UP TO 2.3 CHILLER BODY: MES master '1ST ROW KICKPLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2.3 CHILLER BODY: MES master '2ND ROW KICKPLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2.3 CHILLER BODY: MES master 'RICE GRAIN FLOOR' has no flag on the sheet — left at body default OFF (12)
- UP TO 5.5 CHILLER AND 2.3 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (12)
