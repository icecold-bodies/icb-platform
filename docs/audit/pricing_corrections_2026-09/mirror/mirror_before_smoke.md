## Costing audit — pack `smoke` — PASS

- Run: 2026-09-28T09:54:39+00:00 · tolerance 1.0 % · MES: in-process localhost/icb_prodmirror
- Golden: 2026-09-25T14:09:05+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 18 scenarios
- Cells: UNVERIFIABLE 9, ACCEPTED 39, PASS 150, SKIP 36
- Full report: `mirror_before_smoke.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unverifiable (9 cells)

- UP TO 4.8 MT FREEZER  (2 · DRD · EXCEL_NO_PRICE:EPS (3 scenarios)
- UP TO 4.8 MT FREEZER  (2 · FRONT · EXCEL_NO_PRICE:EPS (3 scenarios)
- UP TO 4.8 MT FREEZER  (2 · SIDES · EXCEL_NO_PRICE:EPS (3 scenarios)

### Known defects — accepted, tracked, awaiting a work order (39 cells)

- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [DATA] SMALL MOUNTING BRACKET priced differently from Burt's sheet on FREEZER MEDIUM (-R126), prod as dev. — review by 2026-10-31 (6)
- UP TO 5.5 CHILLER AND 2.3 WIDE · DRD DOOR FITTINGS · [MES] PROD CHILLER MEDIUM DRD DOOR FITTINGS: 2317 DOOR RUBBER quantity formula ends in *0 (ZERO_FORMULA): -R672 per double door. — review by 2026-10-31 (6)
- UP TO 5.5 CHILLER AND 2.3 WIDE · FLOOR · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · FRONT · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · ROOF · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · SIDES · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- icecream up to 4.8 · DRD · [DATA] PROD icecream 4.8 double door: PU line quantity (+R1.8k) and CSLB HINGES priced differently from Burt's sheet. — review by 2026-10-31 (3)
- icecream up to 4.8 · DRD DOOR FITTINGS · [DATA] PROD icecream 4.8 double door: PU line quantity (+R1.8k) and CSLB HINGES priced differently from Burt's sheet. — review by 2026-10-31 (3)
- icecream up to 4.8 · FLOOR · [MES] master ALU EXTRUTION FLOOR defaults ON for ICECREAM UP TO 3,2 and UP TO 4.8 and adds R13k-R27k (13 x length m at R428.95); Burt's sheets have no such line or flag. On PROD ICECREAM UP TO 4.8 the FLOOR also lacks Burt's 12MM PF PLYWOOD line (-R2.5k) — consistent with the ALU floor option replacing the plywood floor; to confirm in prod's Body Templates. — review by 2026-10-31 (6)
- icecream up to 4.8 · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)

### Oracle findings and probe notes

- UP TO 5.5 CHILLER AND 2.3 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default ON (6)
- icecream up to 4.8: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (6)
