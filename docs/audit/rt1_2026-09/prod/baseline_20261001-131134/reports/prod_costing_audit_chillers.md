## Costing audit — pack `chillers` — PASS

- Run: 2026-10-01T11:11:41+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-09-25T14:12:11+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 98 scenarios
- Cells: ACCEPTED 20, PASS 1009, SKIP 224
- Full report: `prod_costing_audit_chillers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Known defects — accepted, tracked, awaiting a work order (20 cells)

- 4.9 & UP CHILLER AND 2.5 WIDE · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (8)
- UP TO 2.3 CHILLER BODY · DRD · [RULING] Burt's UP TO 2.3 CHILLER sheet charges the double rear door's EPS line (R432) even when the door is PU — the line carries no insulation gate, so the sheet prices EPS and PU together. MES charges PU only. Burt to confirm which is right. — review by 2026-10-31 (3)
- UP TO 2.3 CHILLER BODY · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (3)
- UP TO 2.3 CHILLER BODY · SRD · [DATA] PROD SRD EPS line priced differently from Burt on CHILLER 2.3 / CHILLER LARGE (-R127 to -R148). — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · SRD · [RULING] Burt's SRD sections carry 4MM PF PLYWOOD and one GLUE LINE at R0 (the total cells are hard-coded 0) where MES charges them: +R480 to +R590 per single rear door. Does a single rear door get the inner plywood skin? — review by 2026-10-31 (3)

### Oracle findings and probe notes

- 4.9 & UP CHILLER AND 2.5 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (56)
- 4.9 & UP CHILLER AND 2.5 WIDE: NO_4G_REFERENCE: the PU lines hard-code a rate (no [1]PU! reference) — 4G cannot be expressed on this sheet (8)
- UP TO 2.3 CHILLER BODY: MES master '1ST ROW KICKPLATE' has no flag on the sheet — left at body default OFF (21)
- UP TO 2.3 CHILLER BODY: MES master '2ND ROW KICKPLATE' has no flag on the sheet — left at body default OFF (21)
- UP TO 2.3 CHILLER BODY: MES master 'RICE GRAIN FLOOR' has no flag on the sheet — left at body default OFF (21)
- UP TO 2.3 CHILLER BODY: NO_4G_REFERENCE: the PU lines hard-code a rate (no [1]PU! reference) — 4G cannot be expressed on this sheet (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (21)
- UP TO 5.5 CHILLER AND 2.3 WIDE: NO_4G_REFERENCE: the PU lines hard-code a rate (no [1]PU! reference) — 4G cannot be expressed on this sheet (3)
