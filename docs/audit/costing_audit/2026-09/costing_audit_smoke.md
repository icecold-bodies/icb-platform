## Costing audit — pack `smoke` — PASS

- Run: 2026-09-25T14:17:06+00:00 · tolerance 1.0 % · MES: in-process localhost/icb
- Golden: 2026-09-25T14:09:05+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 18 scenarios
- Cells: UNVERIFIABLE 9, ACCEPTED 54, PASS 135, SKIP 36
- Full report: `costing_audit_smoke.html` (CI artifact)

### Unverifiable (9 cells)

- UP TO 4.8 MT FREEZER  (2 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- UP TO 4.8 MT FREEZER  (2 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- UP TO 4.8 MT FREEZER  (2 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)

### Known defects — accepted, tracked, awaiting a work order (54 cells)

- UP TO 4.8 MT FREEZER  (2 · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (3)
- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [DATA] Excel line 1MM GALV PLATE (R157-R240) has no MES line on this body. — review by 2026-10-31 (6)
- UP TO 5.5 CHILLER AND 2.3 WIDE · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (6)
- UP TO 5.5 CHILLER AND 2.3 WIDE · FLOOR · [MES] chiller PU insulation lines carry a literal x0 quantity formula (2.44*1.22*0*2, 1.22*2.44*0*(length+{Waste})/1.22): PU prices at R0 on FRONT/SIDES/ROOF/FLOOR (ZERO_FORMULA); the icecream/freezer bodies use {PANEL PU} tokens and price live. SIDES/ROOF/FLOOR skins also hard-code both roof and floor deductions where Burt's cells deduct only the roof under PU. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · FRONT · [MES] chiller PU insulation lines carry a literal x0 quantity formula (2.44*1.22*0*2, 1.22*2.44*0*(length+{Waste})/1.22): PU prices at R0 on FRONT/SIDES/ROOF/FLOOR (ZERO_FORMULA); the icecream/freezer bodies use {PANEL PU} tokens and price live. SIDES/ROOF/FLOOR skins also hard-code both roof and floor deductions where Burt's cells deduct only the roof under PU. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · ROOF · [MES] chiller PU insulation lines carry a literal x0 quantity formula (2.44*1.22*0*2, 1.22*2.44*0*(length+{Waste})/1.22): PU prices at R0 on FRONT/SIDES/ROOF/FLOOR (ZERO_FORMULA); the icecream/freezer bodies use {PANEL PU} tokens and price live. SIDES/ROOF/FLOOR skins also hard-code both roof and floor deductions where Burt's cells deduct only the roof under PU. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · SIDES · [MES] chiller PU insulation lines carry a literal x0 quantity formula (2.44*1.22*0*2, 1.22*2.44*0*(length+{Waste})/1.22): PU prices at R0 on FRONT/SIDES/ROOF/FLOOR (ZERO_FORMULA); the icecream/freezer bodies use {PANEL PU} tokens and price live. SIDES/ROOF/FLOOR skins also hard-code both roof and floor deductions where Burt's cells deduct only the roof under PU. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · SUB FRAME + LIGHT BOX ASSY · [DATA] MES prices 1.2MM GALV PLATE R449.52 where Excel prices 1MM GALV PLATE R239.72. — review by 2026-10-31 (6)
- icecream up to 4.8 · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (3)
- icecream up to 4.8 · DRD DOOR FITTINGS · [DATA] icecream 4.8 door lines: 4MM PF PLYWOOD quantity, 28779 DOOR CAPPING (-R324), 3MM 3CR12 FLOOR PLATE (+R77.50) differ from Burt's sheet (2-6 % of the section) - see the triage. — review by 2026-10-31 (3)
- icecream up to 4.8 · FLOOR · [MES] master ALU EXTRUTION FLOOR defaults ON for ICECREAM UP TO 3,2 and UP TO 4.8 and adds R13k-R27k (13 x length m at R428.95); Burt's sheets have no such line or flag. — review by 2026-10-31 (6)
- icecream up to 4.8 · REAR FRAME + FLOOR PLATE · [DATA] icecream 4.8 door lines: 4MM PF PLYWOOD quantity, 28779 DOOR CAPPING (-R324), 3MM 3CR12 FLOOR PLATE (+R77.50) differ from Burt's sheet (2-6 % of the section) - see the triage. — review by 2026-10-31 (3)
- icecream up to 4.8 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- icecream up to 4.8 · SRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (3)

### Oracle findings and probe notes

- UP TO 5.5 CHILLER AND 2.3 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default ON (6)
- icecream up to 4.8: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (6)
