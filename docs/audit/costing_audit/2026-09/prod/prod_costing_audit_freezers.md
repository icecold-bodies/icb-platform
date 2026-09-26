## Costing audit — pack `freezers` — PASS

- Run: 2026-09-26T07:44:26+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform (re-evaluated from the run of 2026-09-26T07:16:29+00:00)
- Golden: 2026-09-25T14:14:16+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 54 scenarios
- Cells: UNVERIFIABLE 27, ACCEPTED 80, PASS 475, SKIP 108
- Full report: `prod_costing_audit_freezers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml

### Unverifiable (27 cells)

- 4.9 & UP FREEZER BODY (2 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- 4.9 & UP FREEZER BODY (2 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- 4.9 & UP FREEZER BODY (2 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)
- UP TO 2,3 MTR FREEZER · DRD · EXCEL_NO_PRICE:EPS (2 scenarios)
- UP TO 2,3 MTR FREEZER · FRONT · EXCEL_NO_PRICE:EPS (2 scenarios)
- UP TO 2,3 MTR FREEZER · SIDES · EXCEL_NO_PRICE:EPS (2 scenarios)
- UP TO 4.8 MT FREEZER  (2 · DRD · EXCEL_NO_PRICE:EPS (4 scenarios)
- UP TO 4.8 MT FREEZER  (2 · FRONT · EXCEL_NO_PRICE:EPS (4 scenarios)
- UP TO 4.8 MT FREEZER  (2 · SIDES · EXCEL_NO_PRICE:EPS (4 scenarios)

### Known defects — accepted, tracked, awaiting a work order (80 cells)

- 4.9 & UP FREEZER BODY (2 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- 4.9 & UP FREEZER BODY (2 · SIDES · [MES] FREEZER LARGE SIDES skin formulas take the panel height from WIDTH where Burt uses HEIGHT; +1.2 % at W 2.6 / H 2.56 and growing with the W-H gap (prod too). — review by 2026-10-31 (15)
- 4.9 & UP FREEZER BODY (2 · SRD · [MES] PROD: the single-rear-door PU line is priced at the raw 32D rate — 1.22*2.44*2 sheets x R4 100 = R24.4k — where Burt has R245/sheet (R1.5k): +R23k on every SRD quote, on every body (chillers, freezers, icecream, explosive). Largest live-quote error found. — review by 2026-10-31 (3)
- 4.9 & UP FREEZER BODY (2 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (3)
- UP TO 2,3 MTR FREEZER · FLOOR · [DATA] PROD FREEZER 2.3 METER ROOF/FLOOR PU: 4.51 sheets x R557.50 (R2.5k) where Burt has 2.98 x R311.27 (R1.4k): +R1.1k per panel under PU. — review by 2026-10-31 (2)
- UP TO 2,3 MTR FREEZER · REAR FRAME + FLOOR PLATE · [DATA] 3MM 3CR12 FLOOR PLATE priced R1 040.16 on prod vs R965.76 on Burt's sheet (+R63, 2.8 % of the section) on FREEZER 2.3 METER. — review by 2026-10-31 (12)
- UP TO 2,3 MTR FREEZER · ROOF · [DATA] PROD FREEZER 2.3 METER ROOF/FLOOR PU: 4.51 sheets x R557.50 (R2.5k) where Burt has 2.98 x R311.27 (R1.4k): +R1.1k per panel under PU. — review by 2026-10-31 (2)
- UP TO 2,3 MTR FREEZER · SRD · [MES] PROD: the single-rear-door PU line is priced at the raw 32D rate — 1.22*2.44*2 sheets x R4 100 = R24.4k — where Burt has R245/sheet (R1.5k): +R23k on every SRD quote, on every body (chillers, freezers, icecream, explosive). Largest live-quote error found. — review by 2026-10-31 (2)
- UP TO 2,3 MTR FREEZER · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (2)
- UP TO 4.8 MT FREEZER  (2 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (4)
- UP TO 4.8 MT FREEZER  (2 · SRD · [MES] PROD: the single-rear-door PU line is priced at the raw 32D rate — 1.22*2.44*2 sheets x R4 100 = R24.4k — where Burt has R245/sheet (R1.5k): +R23k on every SRD quote, on every body (chillers, freezers, icecream, explosive). Largest live-quote error found. — review by 2026-10-31 (4)
- UP TO 4.8 MT FREEZER  (2 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (4)
- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE (FREEZER MEDIUM, explosive bodies) / MOUNTING CLEATS (EXPLOSIVE 2.7 TO 4.8) lines have no MES line on prod. — review by 2026-10-31 (24)

### Oracle findings and probe notes

- UP TO 2,3 MTR FREEZER: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (12)
