## Costing audit — pack `explosive` — FAIL

- Run: 2026-10-19T13:19:27+00:00 · tolerance 1.0 % · MES: in-process localhost/icb_prodmirror
- Golden: 2026-10-01T18:02:46+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 54 scenarios
- Cells: FLAG 6, UNVERIFIABLE 36, ACCEPTED 3, PASS 522, SKIP 117
- Full report: `prod_explosive.html` (CI artifact)

### Unaccepted differences (6)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| EXPLOSIVE 4.9 AND UP | SRD | L4.9 W2.6 H2.1 srd | 6,546.17 | 6,455.05 | 1.39 | FLAG accepted cause(s) explain -6.59 of -91.12; unexplained -84.53 | BOTH PU (-64.58) |
| EXPLOSIVE 4.9 AND UP | SRD | L8 W2.6 H2.1 srd | 6,546.17 | 6,455.05 | 1.39 | FLAG accepted cause(s) explain -6.59 of -91.12; unexplained -84.53 | BOTH PU (-64.58) |
| EXPLOSIVE 4.9 AND UP | SRD | L14.7 W2.6 H2.1 srd | 6,546.17 | 6,455.05 | 1.39 | FLAG accepted cause(s) explain -6.59 of -91.12; unexplained -84.53 | BOTH PU (-64.58) |
| EXPLOSIVE UP TO 2.7 | FRONT | L1.8 W1.2 H1.6 foam_4g | 4,004.28 | 3,960.14 | 1.10 | FLAG | BOTH PU (-44.14) |
| EXPLOSIVE UP TO 2.7 | FRONT | L2.3 W1.2 H1.6 foam_4g | 4,004.28 | 3,960.14 | 1.10 | FLAG | BOTH PU (-44.14) |
| EXPLOSIVE UP TO 2.7 | FRONT | L2.7 W1.2 H1.6 foam_4g | 4,004.28 | 3,960.14 | 1.10 | FLAG | BOTH PU (-44.14) |

### Unverifiable (36 cells)

- EXPLOSIVE 2.7 TO 4.8 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 2.7 TO 4.8 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 2.7 TO 4.8 · ROOF · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 2.7 TO 4.8 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 4.9 AND UP · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 4.9 AND UP · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 4.9 AND UP · ROOF · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE 4.9 AND UP · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE UP TO 2.7 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE UP TO 2.7 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE UP TO 2.7 · ROOF · EXCEL_NO_PRICE:EPS (3 scenarios)
- EXPLOSIVE UP TO 2.7 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)

### Known defects — accepted, tracked, awaiting a work order (3 cells)

- EXPLOSIVE UP TO 2.7 · SRD · [DATA] 0.9 MM ALU PLATE on the EXPLOSIVE UP TO 2.7 single rear door priced/quantified differently from Burt's sheet (-R325), prod as dev. — review by 2026-10-31 (3)

### Oracle findings and probe notes

- EXPLOSIVE 4.9 AND UP: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE 4.9 AND UP: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE 4.9 AND UP: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE 4.9 AND UP: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default ON (18)
- EXPLOSIVE 4.9 AND UP: mixed PU references on the sheet as saved: 1x 32D (C17) + 4x 4G (C19); normalised to 4G for this scenario (18)
- EXPLOSIVE UP TO 2.7: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE UP TO 2.7: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE UP TO 2.7: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE UP TO 2.7: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default ON (18)
