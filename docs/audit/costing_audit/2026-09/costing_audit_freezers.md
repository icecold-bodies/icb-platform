## Costing audit — pack `freezers` — PASS

- Run: 2026-09-26T07:45:09+00:00 · tolerance 1.0 % · MES: in-process localhost/icb
- Golden: 2026-09-25T14:14:16+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 54 scenarios
- Cells: UNVERIFIABLE 27, ACCEPTED 128, PASS 427, SKIP 108
- Full report: `costing_audit_freezers.html` (CI artifact)

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

### Known defects — accepted, tracked, awaiting a work order (128 cells)

- 4.9 & UP FREEZER BODY (2 · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (12)
- 4.9 & UP FREEZER BODY (2 · FLOOR · [DATA] 100*50 LVL Beam quantity: MES ((length+{Waste})/0.356-7.27/1.22)*2.736 = R3 187 vs Burt's beam count x spacing = R3 825 at 4.9 m (-R640, 2.8 % of the section). — review by 2026-10-31 (12)
- 4.9 & UP FREEZER BODY (2 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- 4.9 & UP FREEZER BODY (2 · SIDES · [MES] FREEZER LARGE SIDES skin formulas take the panel height from WIDTH: (length+{Waste})*(width-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}+{Waste}) where Burt uses HEIGHT (C6); +1.2 % at W 2.6 / H 2.56 and growing with the W-H gap. — review by 2026-10-31 (15)
- 4.9 & UP FREEZER BODY (2 · SRD · [MES] DEV: the single-rear-door PU line carries a literal x0 quantity formula (2.44*1.22*0*2) on the freezer, icecream and explosive bodies: PU on an SRD prices at R0 (-R1.5k to -R2.2k per quote). Prod has the opposite defect on the same line (R4 100 raw rate, +R23k) - see accepted_differences.prod.yaml. — review by 2026-10-31 (3)
- 4.9 & UP FREEZER BODY (2 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE R126 (Excel R42), 28782 BIG HORIZ CAPPING R197.20 (Excel R240.58), ALU CORNERS R45 (Excel R54.90), 28780 BIG VERTICAL renamed 28778; Burt prices 2317 DOOR RUBBER / 28777 DOOR CAPPING at R0 on some sheets. — review by 2026-10-31 (3)
- UP TO 2,3 MTR FREEZER · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (8)
- UP TO 2,3 MTR FREEZER · FLOOR · [MES] FREEZER 2.3 METER ROOF/FLOOR PU lines carry a literal x0 quantity formula (1.22*2.44*0*(length+{Waste})/1.22): PU prices at R0 (ZERO_FORMULA), -R1.4k to -R1.8k per panel. — review by 2026-10-31 (2)
- UP TO 2,3 MTR FREEZER · REAR FRAME + FLOOR PLATE · [DATA] 3MM 3CR12 FLOOR PLATE priced R1 040.16 in MES vs R965.76 on Burt's sheet (+R59-R63, 2-3 % of the section). — review by 2026-10-31 (10)
- UP TO 2,3 MTR FREEZER · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (2)
- UP TO 2,3 MTR FREEZER · ROOF · [MES] FREEZER 2.3 METER ROOF/FLOOR PU lines carry a literal x0 quantity formula (1.22*2.44*0*(length+{Waste})/1.22): PU prices at R0 (ZERO_FORMULA), -R1.4k to -R1.8k per panel. — review by 2026-10-31 (2)
- UP TO 2,3 MTR FREEZER · SRD · [MES] DEV: the single-rear-door PU line carries a literal x0 quantity formula (2.44*1.22*0*2) on the freezer, icecream and explosive bodies: PU on an SRD prices at R0 (-R1.5k to -R2.2k per quote). Prod has the opposite defect on the same line (R4 100 raw rate, +R23k) - see accepted_differences.prod.yaml. — review by 2026-10-31 (2)
- UP TO 2,3 MTR FREEZER · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE R126 (Excel R42), 28782 BIG HORIZ CAPPING R197.20 (Excel R240.58), ALU CORNERS R45 (Excel R54.90), 28780 BIG VERTICAL renamed 28778; Burt prices 2317 DOOR RUBBER / 28777 DOOR CAPPING at R0 on some sheets. — review by 2026-10-31 (2)
- UP TO 4.8 MT FREEZER  (2 · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (16)
- UP TO 4.8 MT FREEZER  (2 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (4)
- UP TO 4.8 MT FREEZER  (2 · SRD · [MES] DEV: the single-rear-door PU line carries a literal x0 quantity formula (2.44*1.22*0*2) on the freezer, icecream and explosive bodies: PU on an SRD prices at R0 (-R1.5k to -R2.2k per quote). Prod has the opposite defect on the same line (R4 100 raw rate, +R23k) - see accepted_differences.prod.yaml. — review by 2026-10-31 (4)
- UP TO 4.8 MT FREEZER  (2 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE R126 (Excel R42), 28782 BIG HORIZ CAPPING R197.20 (Excel R240.58), ALU CORNERS R45 (Excel R54.90), 28780 BIG VERTICAL renamed 28778; Burt prices 2317 DOOR RUBBER / 28777 DOOR CAPPING at R0 on some sheets. — review by 2026-10-31 (4)
- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE line (R157-R240): missing from the MES BOM on CHILLER 2.3, CHILLER LARGE, FREEZER MEDIUM and the explosive bodies; CHILLER MEDIUM carries 1.2MM GALV PLATE at R449.52 (or, since 26 Sep on dev, a 1MM line at another price). — review by 2026-10-31 (24)

### Oracle findings and probe notes

- UP TO 2,3 MTR FREEZER: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (12)
