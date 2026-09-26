## Costing audit — pack `explosive` — PASS

- Run: 2026-09-26T07:45:15+00:00 · tolerance 1.0 % · MES: in-process localhost/icb
- Golden: 2026-09-26T07:10:40+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 54 scenarios
- Cells: UNVERIFIABLE 36, ACCEPTED 135, PASS 405, SKIP 108
- Full report: `costing_audit_explosive.html` (CI artifact)

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

### Known defects — accepted, tracked, awaiting a work order (135 cells)

- EXPLOSIVE 2.7 TO 4.8 · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (12)
- EXPLOSIVE 2.7 TO 4.8 · FLOOR · [MES] EXPLOSIVE 2.7 TO 4.8 FLOOR carries a PU line (+R680) on dev that Burt's sheet does not have (the explosive sheets carry no FLOOR EPS/PU rows); prod does not carry it. — review by 2026-10-31 (18)
- EXPLOSIVE 2.7 TO 4.8 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- EXPLOSIVE 2.7 TO 4.8 · SRD · [MES] DEV: the single-rear-door PU line carries a literal x0 quantity formula (2.44*1.22*0*2) on the freezer, icecream and explosive bodies: PU on an SRD prices at R0 (-R1.5k to -R2.2k per quote). Prod has the opposite defect on the same line (R4 100 raw rate, +R23k) - see accepted_differences.prod.yaml. — review by 2026-10-31 (3)
- EXPLOSIVE 2.7 TO 4.8 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE R126 (Excel R42), 28782 BIG HORIZ CAPPING R197.20 (Excel R240.58), ALU CORNERS R45 (Excel R54.90), 28780 BIG VERTICAL renamed 28778; Burt prices 2317 DOOR RUBBER / 28777 DOOR CAPPING at R0 on some sheets. — review by 2026-10-31 (3)
- EXPLOSIVE 2.7 TO 4.8 · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's MOUNTING CLEATS line has no MES line on EXPLOSIVE 2.7 TO 4.8 (-R240). — review by 2026-10-31 (18)
- EXPLOSIVE 4.9 AND UP · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (12)
- EXPLOSIVE 4.9 AND UP · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- EXPLOSIVE 4.9 AND UP · SRD · [MES] DEV: the single-rear-door PU line carries a literal x0 quantity formula (2.44*1.22*0*2) on the freezer, icecream and explosive bodies: PU on an SRD prices at R0 (-R1.5k to -R2.2k per quote). Prod has the opposite defect on the same line (R4 100 raw rate, +R23k) - see accepted_differences.prod.yaml. — review by 2026-10-31 (3)
- EXPLOSIVE 4.9 AND UP · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE R126 (Excel R42), 28782 BIG HORIZ CAPPING R197.20 (Excel R240.58), ALU CORNERS R45 (Excel R54.90), 28780 BIG VERTICAL renamed 28778; Burt prices 2317 DOOR RUBBER / 28777 DOOR CAPPING at R0 on some sheets. — review by 2026-10-31 (3)
- EXPLOSIVE 4.9 AND UP · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE line (R157-R240): missing from the MES BOM on CHILLER 2.3, CHILLER LARGE, FREEZER MEDIUM and the explosive bodies; CHILLER MEDIUM carries 1.2MM GALV PLATE at R449.52 (or, since 26 Sep on dev, a 1MM line at another price). — review by 2026-10-31 (18)
- EXPLOSIVE UP TO 2.7 · DRD · [DATA] 130*62MM TAPPING BLOCKS: Excel 2 x R234 per size (R936 a double door) vs MES 6 x R68 per size (R816): R60 per size, 1-3 % of the door section. — review by 2026-10-31 (12)
- EXPLOSIVE UP TO 2.7 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- EXPLOSIVE UP TO 2.7 · SRD · [MES] DEV: the single-rear-door PU line carries a literal x0 quantity formula (2.44*1.22*0*2) on the freezer, icecream and explosive bodies: PU on an SRD prices at R0 (-R1.5k to -R2.2k per quote). Prod has the opposite defect on the same line (R4 100 raw rate, +R23k) - see accepted_differences.prod.yaml. — review by 2026-10-31 (3)
- EXPLOSIVE UP TO 2.7 · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE R126 (Excel R42), 28782 BIG HORIZ CAPPING R197.20 (Excel R240.58), ALU CORNERS R45 (Excel R54.90), 28780 BIG VERTICAL renamed 28778; Burt prices 2317 DOOR RUBBER / 28777 DOOR CAPPING at R0 on some sheets. — review by 2026-10-31 (3)
- EXPLOSIVE UP TO 2.7 · SUB FRAME + LIGHT BOX ASSY · [DATA] Burt's 1MM GALV PLATE line (R157-R240): missing from the MES BOM on CHILLER 2.3, CHILLER LARGE, FREEZER MEDIUM and the explosive bodies; CHILLER MEDIUM carries 1.2MM GALV PLATE at R449.52 (or, since 26 Sep on dev, a 1MM line at another price). — review by 2026-10-31 (18)

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
