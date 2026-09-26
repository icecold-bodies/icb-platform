## Costing audit — pack `explosive` — PASS

- Run: 2026-09-26T07:44:28+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform (re-evaluated from the run of 2026-09-26T07:16:36+00:00)
- Golden: 2026-09-26T07:10:40+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 54 scenarios
- Cells: UNVERIFIABLE 36, ACCEPTED 164, PASS 376, SKIP 108
- Full report: `prod_costing_audit_explosive.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml

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

### Known defects — accepted, tracked, awaiting a work order (164 cells)

- EXPLOSIVE 2.7 TO 4.8 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- EXPLOSIVE 2.7 TO 4.8 · ROOF · [DATA] PROD explosive bodies carry a 6MM PF PLYWOOD line on ROOF/SIDES where Burt has 4MM PF PLYWOOD (+R60 to +R1.3k), and EXPLOSIVE 4.9 AND UP prices PU as 12.08 x R234.15 per panel where Burt has 2.98 x R172 (+R370 front, +R1.5k sides, +R750 roof). — review by 2026-10-31 (14)
- EXPLOSIVE 2.7 TO 4.8 · SIDES · [DATA] PROD explosive bodies carry a 6MM PF PLYWOOD line on ROOF/SIDES where Burt has 4MM PF PLYWOOD (+R60 to +R1.3k), and EXPLOSIVE 4.9 AND UP prices PU as 12.08 x R234.15 per panel where Burt has 2.98 x R172 (+R370 front, +R1.5k sides, +R750 roof). — review by 2026-10-31 (12)
- EXPLOSIVE 2.7 TO 4.8 · SRD · [MES] PROD: the single-rear-door PU line is priced at the raw 32D rate — 1.22*2.44*2 sheets x R4 100 = R24.4k — where Burt has R245/sheet (R1.5k): +R23k on every SRD quote, on every body (chillers, freezers, icecream, explosive). Largest live-quote error found. — review by 2026-10-31 (3)
- EXPLOSIVE 2.7 TO 4.8 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (3)
- EXPLOSIVE 2.7 TO 4.8 · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE (FREEZER MEDIUM, explosive bodies) / MOUNTING CLEATS (EXPLOSIVE 2.7 TO 4.8) lines have no MES line on prod. — review by 2026-10-31 (18)
- EXPLOSIVE 4.9 AND UP · DRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (12)
- EXPLOSIVE 4.9 AND UP · FRONT · [DATA] PROD explosive bodies carry a 6MM PF PLYWOOD line on ROOF/SIDES where Burt has 4MM PF PLYWOOD (+R60 to +R1.3k), and EXPLOSIVE 4.9 AND UP prices PU as 12.08 x R234.15 per panel where Burt has 2.98 x R172 (+R370 front, +R1.5k sides, +R750 roof). — review by 2026-10-31 (15)
- EXPLOSIVE 4.9 AND UP · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- EXPLOSIVE 4.9 AND UP · ROOF · [DATA] PROD explosive bodies carry a 6MM PF PLYWOOD line on ROOF/SIDES where Burt has 4MM PF PLYWOOD (+R60 to +R1.3k), and EXPLOSIVE 4.9 AND UP prices PU as 12.08 x R234.15 per panel where Burt has 2.98 x R172 (+R370 front, +R1.5k sides, +R750 roof). — review by 2026-10-31 (15)
- EXPLOSIVE 4.9 AND UP · SIDES · [DATA] PROD explosive bodies carry a 6MM PF PLYWOOD line on ROOF/SIDES where Burt has 4MM PF PLYWOOD (+R60 to +R1.3k), and EXPLOSIVE 4.9 AND UP prices PU as 12.08 x R234.15 per panel where Burt has 2.98 x R172 (+R370 front, +R1.5k sides, +R750 roof). — review by 2026-10-31 (15)
- EXPLOSIVE 4.9 AND UP · SRD · [MES] PROD: the single-rear-door PU line is priced at the raw 32D rate — 1.22*2.44*2 sheets x R4 100 = R24.4k — where Burt has R245/sheet (R1.5k): +R23k on every SRD quote, on every body (chillers, freezers, icecream, explosive). Largest live-quote error found. — review by 2026-10-31 (3)
- EXPLOSIVE 4.9 AND UP · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (3)
- EXPLOSIVE 4.9 AND UP · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE (FREEZER MEDIUM, explosive bodies) / MOUNTING CLEATS (EXPLOSIVE 2.7 TO 4.8) lines have no MES line on prod. — review by 2026-10-31 (18)
- EXPLOSIVE UP TO 2.7 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- EXPLOSIVE UP TO 2.7 · SRD · [MES] PROD: the single-rear-door PU line is priced at the raw 32D rate — 1.22*2.44*2 sheets x R4 100 = R24.4k — where Burt has R245/sheet (R1.5k): +R23k on every SRD quote, on every body (chillers, freezers, icecream, explosive). Largest live-quote error found. — review by 2026-10-31 (3)
- EXPLOSIVE UP TO 2.7 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (3)
- EXPLOSIVE UP TO 2.7 · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE (FREEZER MEDIUM, explosive bodies) / MOUNTING CLEATS (EXPLOSIVE 2.7 TO 4.8) lines have no MES line on prod. — review by 2026-10-31 (18)

### Oracle findings and probe notes

- EXPLOSIVE 4.9 AND UP: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE 4.9 AND UP: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE 4.9 AND UP: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE 4.9 AND UP: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default ON (18)
- EXPLOSIVE 4.9 AND UP: mixed PU references on the sheet as saved: 1x 32D (C17) + 4x 4G (C19); normalised to 32D for this scenario (15)
- EXPLOSIVE 4.9 AND UP: mixed PU references on the sheet as saved: 1x 32D (C17) + 4x 4G (C19); normalised to 4G for this scenario (3)
- EXPLOSIVE UP TO 2.7: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE UP TO 2.7: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE UP TO 2.7: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (18)
- EXPLOSIVE UP TO 2.7: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default ON (18)
