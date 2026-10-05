## Costing audit — pack `explosive` — PASS

- Run: 2026-10-05T06:19:47+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-01T18:02:46+00:00 · workbook month 2026-09 · GRP sha256 `04c774e2a7de` · 54 scenarios
- Cells: UNVERIFIABLE 36, ACCEPTED 60, PASS 471, SKIP 117
- Full report: `prod_explosive.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

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

### Known defects — accepted, tracked, awaiting a work order (60 cells)

- EXPLOSIVE 2.7 TO 4.8 · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE (FREEZER MEDIUM, explosive bodies) / MOUNTING CLEATS (EXPLOSIVE 2.7 TO 4.8) lines have no MES line on prod. — review by 2026-10-31 (18)
- EXPLOSIVE 4.9 AND UP · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE (FREEZER MEDIUM, explosive bodies) / MOUNTING CLEATS (EXPLOSIVE 2.7 TO 4.8) lines have no MES line on prod. — review by 2026-10-31 (18)
- EXPLOSIVE UP TO 2.7 · SRD · [DATA] 0.9 MM ALU PLATE on the EXPLOSIVE UP TO 2.7 single rear door priced/quantified differently from Burt's sheet (-R325), prod as dev. — review by 2026-10-31 (3)
- EXPLOSIVE UP TO 2.7 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (3)
- EXPLOSIVE UP TO 2.7 · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE (FREEZER MEDIUM, explosive bodies) / MOUNTING CLEATS (EXPLOSIVE 2.7 TO 4.8) lines have no MES line on prod. — review by 2026-10-31 (18)

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
