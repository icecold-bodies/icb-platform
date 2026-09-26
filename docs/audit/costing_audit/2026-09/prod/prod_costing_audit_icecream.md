## Costing audit — pack `icecream` — PASS

- Run: 2026-09-26T07:44:27+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform (re-evaluated from the run of 2026-09-26T07:16:32+00:00)
- Golden: 2026-09-25T14:16:10+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 48 scenarios
- Cells: UNVERIFIABLE 40, ACCEPTED 146, PASS 330, SKIP 96
- Full report: `prod_costing_audit_icecream.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml

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

### Known defects — accepted, tracked, awaiting a work order (146 cells)

- icecream 4.9 up · ALUMINIUM · [MES] ICECREAM 4.9 UP has the length 6.7 HARD-CODED in its ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY and REFLEXITE TAPE formulas on prod too (SIDES is correct on prod): priced at 6.7 m whatever length is entered. — review by 2026-10-31 (12)
- icecream 4.9 up · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (12)
- icecream 4.9 up · FLOOR · [MES] ICECREAM 4.9 UP has the length 6.7 HARD-CODED in its ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY and REFLEXITE TAPE formulas on prod too (SIDES is correct on prod): priced at 6.7 m whatever length is entered. — review by 2026-10-31 (10)
- icecream 4.9 up · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- icecream 4.9 up · REFLEXITE TAPE · [MES] ICECREAM 4.9 UP has the length 6.7 HARD-CODED in its ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY and REFLEXITE TAPE formulas on prod too (SIDES is correct on prod): priced at 6.7 m whatever length is entered. — review by 2026-10-31 (12)
- icecream 4.9 up · ROOF · [MES] ICECREAM 4.9 UP has the length 6.7 HARD-CODED in its ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY and REFLEXITE TAPE formulas on prod too (SIDES is correct on prod): priced at 6.7 m whatever length is entered. — review by 2026-10-31 (10)
- icecream 4.9 up · SRD · [MES] PROD: the single-rear-door PU line is priced at the raw 32D rate — 1.22*2.44*2 sheets x R4 100 = R24.4k — where Burt has R245/sheet (R1.5k): +R23k on every SRD quote, on every body (chillers, freezers, icecream, explosive). Largest live-quote error found. — review by 2026-10-31 (3)
- icecream 4.9 up · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (3)
- icecream 4.9 up · SUB FRAME + LIGHT BOX ASSY · [MES] ICECREAM 4.9 UP has the length 6.7 HARD-CODED in its ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX ASSY and REFLEXITE TAPE formulas on prod too (SIDES is correct on prod): priced at 6.7 m whatever length is entered. — review by 2026-10-31 (12)
- icecream up to 3,2 · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (8)
- icecream up to 3,2 · FLOOR · [MES] master ALU EXTRUTION FLOOR defaults ON for ICECREAM UP TO 3,2 and UP TO 4.8 and adds R13k-R27k (13 x length m at R428.95); Burt's sheets have no such line or flag. — review by 2026-10-31 (10)
- icecream up to 3,2 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (2)
- icecream up to 3,2 · SRD · [DATA] PROD icecream 3,2 SRD carries a 3MM ALU BUFFER PLATE line Burt's sheet does not (+R235). — review by 2026-10-31 (2)
- icecream up to 3,2 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (2)
- icecream up to 4.8 · DRD · [DATA] PROD icecream 4.8 double door: PU line quantity (+R1.8k) and CSLB HINGES priced differently from Burt's sheet. — review by 2026-10-31 (12)
- icecream up to 4.8 · DRD DOOR FITTINGS · [DATA] PROD icecream 4.8 double door: PU line quantity (+R1.8k) and CSLB HINGES priced differently from Burt's sheet. — review by 2026-10-31 (15)
- icecream up to 4.8 · FLOOR · [MES] master ALU EXTRUTION FLOOR defaults ON for ICECREAM UP TO 3,2 and UP TO 4.8 and adds R13k-R27k (13 x length m at R428.95); Burt's sheets have no such line or flag. — review by 2026-10-31 (15)
- icecream up to 4.8 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)

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
