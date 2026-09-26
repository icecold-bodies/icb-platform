## Costing audit — pack `chillers` — PASS

- Run: 2026-09-26T07:44:26+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform (re-evaluated from the run of 2026-09-26T07:16:25+00:00)
- Golden: 2026-09-25T14:12:11+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 84 scenarios
- Cells: ACCEPTED 124, PASS 782, SKIP 168
- Full report: `prod_costing_audit_chillers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml

### Known defects — accepted, tracked, awaiting a work order (124 cells)

- 4.9 & UP CHILLER AND 2.5 WIDE · DRD · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (8)
- 4.9 & UP CHILLER AND 2.5 WIDE · FLOOR · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (8)
- 4.9 & UP CHILLER AND 2.5 WIDE · FRONT · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (8)
- 4.9 & UP CHILLER AND 2.5 WIDE · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (8)
- 4.9 & UP CHILLER AND 2.5 WIDE · ROOF · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (8)
- 4.9 & UP CHILLER AND 2.5 WIDE · SIDES · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (8)
- 4.9 & UP CHILLER AND 2.5 WIDE · SRD · [DATA] PROD SRD EPS line priced differently from Burt on CHILLER 2.3 / CHILLER LARGE (-R127 to -R148). — review by 2026-10-31 (8)
- 4.9 & UP CHILLER AND 2.5 WIDE · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (8)
- UP TO 2.3 CHILLER BODY · DRD · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 2.3 CHILLER BODY · FLOOR · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 2.3 CHILLER BODY · FRONT · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 2.3 CHILLER BODY · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- UP TO 2.3 CHILLER BODY · ROOF · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 2.3 CHILLER BODY · SIDES · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 2.3 CHILLER BODY · SRD · [DATA] PROD SRD EPS line priced differently from Burt on CHILLER 2.3 / CHILLER LARGE (-R127 to -R148). — review by 2026-10-31 (3)
- UP TO 2.3 CHILLER BODY · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · DRD DOOR FITTINGS · [MES] PROD CHILLER MEDIUM DRD DOOR FITTINGS: 2317 DOOR RUBBER quantity formula ends in *0 (ZERO_FORMULA): -R672 per double door. — review by 2026-10-31 (15)
- UP TO 5.5 CHILLER AND 2.3 WIDE · FLOOR · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · FRONT · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · ROOF · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · SIDES · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · SRD DOOR FITTINGS · [DATA] SRD DOOR FITTINGS on every body: MES CSLB HINGES R293.46 x2 (Excel R146.73 x2 - the pair price applied per hinge) and SILPLUS X WHITE R232.30 (Excel R116.15); per body also 34MM LOCKING POLE, 28782 BIG HORIZ CAPPING, ALU CORNERS, 28780/28778 BIG VERTICAL. — review by 2026-10-31 (3)

### Oracle findings and probe notes

- 4.9 & UP CHILLER AND 2.5 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (48)
- 4.9 & UP CHILLER AND 2.5 WIDE: NO_4G_REFERENCE: the PU lines hard-code a rate (no [1]PU! reference) — 4G cannot be expressed on this sheet (8)
- UP TO 2.3 CHILLER BODY: MES master '1ST ROW KICKPLATE' has no flag on the sheet — left at body default OFF (18)
- UP TO 2.3 CHILLER BODY: MES master '2ND ROW KICKPLATE' has no flag on the sheet — left at body default OFF (18)
- UP TO 2.3 CHILLER BODY: MES master 'RICE GRAIN FLOOR' has no flag on the sheet — left at body default OFF (18)
- UP TO 2.3 CHILLER BODY: NO_4G_REFERENCE: the PU lines hard-code a rate (no [1]PU! reference) — 4G cannot be expressed on this sheet (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (18)
- UP TO 5.5 CHILLER AND 2.3 WIDE: NO_4G_REFERENCE: the PU lines hard-code a rate (no [1]PU! reference) — 4G cannot be expressed on this sheet (3)
