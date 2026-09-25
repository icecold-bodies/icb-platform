## Costing audit — pack `icecream` — PASS

- Run: 2026-09-25T14:18:00+00:00 · tolerance 1.0 % · MES: in-process localhost/icb
- Golden: 2026-09-25T14:16:10+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 48 scenarios
- Cells: UNVERIFIABLE 40, ACCEPTED 182, PASS 294, SKIP 96
- Full report: `costing_audit_icecream.html` (CI artifact)

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
- icecream up to 4.8 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · FLOOR · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · ROOF · EXCEL_NO_PRICE:EPS (3 scenarios)
- icecream up to 4.8 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)

### Known defects — accepted, tracked, awaiting a work order (182 cells)

- icecream 4.9 up · ALUMINIUM · [MES] ICECREAM 4.9 UP has the length 6.7 HARD-CODED in its formulas ((6.7+{Waste})*..., 6.7*2) on SIDES, ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY and REFLEXITE TAPE: MES prices this body at 6.7 m whatever length is entered (+R10k at 4.9 m, under-priced above 6.7 m). Burt's sheet uses C4. — review by 2026-10-31 (12)
- icecream 4.9 up · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (12)
- icecream 4.9 up · FLOOR · [MES] ICECREAM 4.9 UP has the length 6.7 HARD-CODED in its formulas ((6.7+{Waste})*..., 6.7*2) on SIDES, ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY and REFLEXITE TAPE: MES prices this body at 6.7 m whatever length is entered (+R10k at 4.9 m, under-priced above 6.7 m). Burt's sheet uses C4. — review by 2026-10-31 (10)
- icecream 4.9 up · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- icecream 4.9 up · REFLEXITE TAPE · [MES] ICECREAM 4.9 UP has the length 6.7 HARD-CODED in its formulas ((6.7+{Waste})*..., 6.7*2) on SIDES, ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY and REFLEXITE TAPE: MES prices this body at 6.7 m whatever length is entered (+R10k at 4.9 m, under-priced above 6.7 m). Burt's sheet uses C4. — review by 2026-10-31 (12)
- icecream 4.9 up · ROOF · [MES] ICECREAM 4.9 UP has the length 6.7 HARD-CODED in its formulas ((6.7+{Waste})*..., 6.7*2) on SIDES, ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY and REFLEXITE TAPE: MES prices this body at 6.7 m whatever length is entered (+R10k at 4.9 m, under-priced above 6.7 m). Burt's sheet uses C4. — review by 2026-10-31 (10)
- icecream 4.9 up · SIDES · [MES] ICECREAM 4.9 UP has the length 6.7 HARD-CODED in its formulas ((6.7+{Waste})*..., 6.7*2) on SIDES, ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY and REFLEXITE TAPE: MES prices this body at 6.7 m whatever length is entered (+R10k at 4.9 m, under-priced above 6.7 m). Burt's sheet uses C4. — review by 2026-10-31 (10)
- icecream 4.9 up · SRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (3)
- icecream 4.9 up · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE R126 (Excel R42), 28782 BIG HORIZ CAPPING R197.20 (Excel R240.58), ALU CORNERS R45 (Excel R54.90), 28780 BIG VERTICAL renamed 28778; Burt prices 2317 DOOR RUBBER / 28777 DOOR CAPPING at R0 on some sheets. — review by 2026-10-31 (3)
- icecream 4.9 up · SUB FRAME + LIGHT BOX ASSY · [MES] ICECREAM 4.9 UP has the length 6.7 HARD-CODED in its formulas ((6.7+{Waste})*..., 6.7*2) on SIDES, ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY and REFLEXITE TAPE: MES prices this body at 6.7 m whatever length is entered (+R10k at 4.9 m, under-priced above 6.7 m). Burt's sheet uses C4. — review by 2026-10-31 (12)
- icecream up to 3,2 · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (8)
- icecream up to 3,2 · FLOOR · [MES] master ALU EXTRUTION FLOOR defaults ON for ICECREAM UP TO 3,2 and UP TO 4.8 and adds R13k-R27k (13 x length m at R428.95); Burt's sheets have no such line or flag. — review by 2026-10-31 (10)
- icecream up to 3,2 · REAR FRAME + FLOOR PLATE · [DATA] 3MM 3CR12 FLOOR PLATE priced R1 040.16 in MES vs R965.76 on Burt's sheet (+R59-R63, 2-3 % of the section). — review by 2026-10-31 (8)
- icecream up to 3,2 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (2)
- icecream up to 3,2 · SRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (2)
- icecream up to 3,2 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE R126 (Excel R42), 28782 BIG HORIZ CAPPING R197.20 (Excel R240.58), ALU CORNERS R45 (Excel R54.90), 28780 BIG VERTICAL renamed 28778; Burt prices 2317 DOOR RUBBER / 28777 DOOR CAPPING at R0 on some sheets. — review by 2026-10-31 (2)
- icecream up to 4.8 · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (12)
- icecream up to 4.8 · DRD DOOR FITTINGS · [DATA] icecream 4.8 door lines: 4MM PF PLYWOOD quantity, 28779 DOOR CAPPING (-R324), 3MM 3CR12 FLOOR PLATE (+R77.50) differ from Burt's sheet (2-6 % of the section) - see the triage. — review by 2026-10-31 (15)
- icecream up to 4.8 · FLOOR · [MES] master ALU EXTRUTION FLOOR defaults ON for ICECREAM UP TO 3,2 and UP TO 4.8 and adds R13k-R27k (13 x length m at R428.95); Burt's sheets have no such line or flag. — review by 2026-10-31 (15)
- icecream up to 4.8 · REAR FRAME + FLOOR PLATE · [DATA] icecream 4.8 door lines: 4MM PF PLYWOOD quantity, 28779 DOOR CAPPING (-R324), 3MM 3CR12 FLOOR PLATE (+R77.50) differ from Burt's sheet (2-6 % of the section) - see the triage. — review by 2026-10-31 (15)
- icecream up to 4.8 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- icecream up to 4.8 · SRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (3)

### Oracle findings and probe notes

- icecream 4.9 up: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- icecream 4.9 up: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- icecream 4.9 up: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default ON (18)
- icecream 4.9 up: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (18)
- icecream up to 3,2: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- icecream up to 3,2: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- icecream up to 3,2: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default ON (12)
- icecream up to 3,2: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (12)
- icecream up to 4.8: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- icecream up to 4.8: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- icecream up to 4.8: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default ON (18)
- icecream up to 4.8: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (18)
