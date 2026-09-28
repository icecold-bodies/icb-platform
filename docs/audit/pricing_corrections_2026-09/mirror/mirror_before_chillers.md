## Costing audit — pack `chillers` — FAIL

- Run: 2026-09-28T09:54:44+00:00 · tolerance 1.0 % · MES: in-process localhost/icb_prodmirror
- Golden: 2026-09-25T14:12:11+00:00 · workbook month 2026-09 · GRP sha256 `d87a573177dc` · 98 scenarios
- Cells: FLAG 11, PRESENCE 14, ACCEPTED 66, PASS 966, SKIP 196
- Full report: `mirror_before_chillers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unaccepted differences (25)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| 4.9 & UP CHILLER AND 2.5 WIDE | REAR FRAME + FLOOR PLATE | L4.9 W2.5 H2.56 srd_pu | 0.00 | 5,472.97 |  | PRESENCE EXTRA_IN_MES |  |
| 4.9 & UP CHILLER AND 2.5 WIDE | REAR FRAME + FLOOR PLATE | L4.9 W2.6 H2.56 srd_pu | 0.00 | 5,502.42 |  | PRESENCE EXTRA_IN_MES |  |
| 4.9 & UP CHILLER AND 2.5 WIDE | REAR FRAME + FLOOR PLATE | L5.8 W2.5 H2.56 srd_pu | 0.00 | 5,472.97 |  | PRESENCE EXTRA_IN_MES |  |
| 4.9 & UP CHILLER AND 2.5 WIDE | REAR FRAME + FLOOR PLATE | L5.8 W2.6 H2.56 srd_pu | 0.00 | 5,502.42 |  | PRESENCE EXTRA_IN_MES |  |
| 4.9 & UP CHILLER AND 2.5 WIDE | REAR FRAME + FLOOR PLATE | L7.5 W2.5 H2.56 srd_pu | 0.00 | 5,472.97 |  | PRESENCE EXTRA_IN_MES |  |
| 4.9 & UP CHILLER AND 2.5 WIDE | REAR FRAME + FLOOR PLATE | L7.5 W2.6 H2.56 srd_pu | 0.00 | 5,502.42 |  | PRESENCE EXTRA_IN_MES |  |
| 4.9 & UP CHILLER AND 2.5 WIDE | REAR FRAME + FLOOR PLATE | L8.5 W2.5 H2.56 srd_pu | 0.00 | 5,472.97 |  | PRESENCE EXTRA_IN_MES |  |
| 4.9 & UP CHILLER AND 2.5 WIDE | REAR FRAME + FLOOR PLATE | L8.5 W2.6 H2.56 srd_pu | 0.00 | 5,502.42 |  | PRESENCE EXTRA_IN_MES |  |
| 4.9 & UP CHILLER AND 2.5 WIDE | SRD | L4.9 W2.5 H2.56 srd_pu | 5,072.40 | 28,439.49 | 460.67 | FLAG accepted cause(s) explain +60.00 of +23 367.09; unexplained +23 307.09 | BOTH PU (+23307.15) |
| 4.9 & UP CHILLER AND 2.5 WIDE | SRD | L4.9 W2.6 H2.56 srd_pu | 5,218.97 | 28,586.06 | 447.73 | FLAG accepted cause(s) explain +60.00 of +23 367.09; unexplained +23 307.09 | BOTH PU (+23307.15) |
| 4.9 & UP CHILLER AND 2.5 WIDE | SRD | L5.8 W2.5 H2.56 srd_pu | 5,072.40 | 28,439.49 | 460.67 | FLAG accepted cause(s) explain +60.00 of +23 367.09; unexplained +23 307.09 | BOTH PU (+23307.15) |
| 4.9 & UP CHILLER AND 2.5 WIDE | SRD | L5.8 W2.6 H2.56 srd_pu | 5,218.97 | 28,586.06 | 447.73 | FLAG accepted cause(s) explain +60.00 of +23 367.09; unexplained +23 307.09 | BOTH PU (+23307.15) |
| 4.9 & UP CHILLER AND 2.5 WIDE | SRD | L7.5 W2.5 H2.56 srd_pu | 5,072.40 | 28,439.49 | 460.67 | FLAG accepted cause(s) explain +60.00 of +23 367.09; unexplained +23 307.09 | BOTH PU (+23307.15) |
| 4.9 & UP CHILLER AND 2.5 WIDE | SRD | L7.5 W2.6 H2.56 srd_pu | 5,218.97 | 28,586.06 | 447.73 | FLAG accepted cause(s) explain +60.00 of +23 367.09; unexplained +23 307.09 | BOTH PU (+23307.15) |
| 4.9 & UP CHILLER AND 2.5 WIDE | SRD | L8.5 W2.5 H2.56 srd_pu | 5,072.40 | 28,439.49 | 460.67 | FLAG accepted cause(s) explain +60.00 of +23 367.09; unexplained +23 307.09 | BOTH PU (+23307.15) |
| 4.9 & UP CHILLER AND 2.5 WIDE | SRD | L8.5 W2.6 H2.56 srd_pu | 5,218.97 | 28,586.06 | 447.73 | FLAG accepted cause(s) explain +60.00 of +23 367.09; unexplained +23 307.09 | BOTH PU (+23307.15) |
| UP TO 2.3 CHILLER BODY | REAR FRAME + FLOOR PLATE | L1.8 W1.8 H1.8 srd_pu | 0.00 | 2,447.57 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 2.3 CHILLER BODY | REAR FRAME + FLOOR PLATE | L2.3 W1.8 H1.8 srd_pu | 0.00 | 2,447.57 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 2.3 CHILLER BODY | REAR FRAME + FLOOR PLATE | L2.7 W1.8 H1.8 srd_pu | 0.00 | 2,447.57 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 5.5 CHILLER AND 2.3 WIDE | REAR FRAME + FLOOR PLATE | L3 W2.3 H2.3 srd_pu | 0.00 | 3,129.75 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 5.5 CHILLER AND 2.3 WIDE | REAR FRAME + FLOOR PLATE | L4.2 W2.3 H2.3 srd_pu | 0.00 | 3,129.75 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 5.5 CHILLER AND 2.3 WIDE | REAR FRAME + FLOOR PLATE | L5.5 W2.3 H2.3 srd_pu | 0.00 | 3,129.75 |  | PRESENCE EXTRA_IN_MES |  |
| UP TO 5.5 CHILLER AND 2.3 WIDE | SRD | L3 W2.3 H2.3 srd_pu | 3,927.25 | 28,239.64 | 619.07 | FLAG accepted cause(s) explain +528.00 of +24 312.39; unexplained +23 784.39 | BOTH PU (+23307.15) |
| UP TO 5.5 CHILLER AND 2.3 WIDE | SRD | L4.2 W2.3 H2.3 srd_pu | 3,927.25 | 28,239.64 | 619.07 | FLAG accepted cause(s) explain +528.00 of +24 312.39; unexplained +23 784.39 | BOTH PU (+23307.15) |
| UP TO 5.5 CHILLER AND 2.3 WIDE | SRD | L5.5 W2.3 H2.3 srd_pu | 3,927.25 | 28,239.64 | 619.07 | FLAG accepted cause(s) explain +528.00 of +24 312.39; unexplained +23 784.39 | BOTH PU (+23307.15) |

### Known defects — accepted, tracked, awaiting a work order (66 cells)

- 4.9 & UP CHILLER AND 2.5 WIDE · FLOOR · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (8)
- 4.9 & UP CHILLER AND 2.5 WIDE · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (8)
- 4.9 & UP CHILLER AND 2.5 WIDE · ROOF · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (8)
- UP TO 2.3 CHILLER BODY · DRD · [RULING] Burt's UP TO 2.3 CHILLER sheet charges the double rear door's EPS line (R432) even when the door is PU — the line carries no insulation gate, so the sheet prices EPS and PU together. MES charges PU only. Burt to confirm which is right. — review by 2026-10-31 (3)
- UP TO 2.3 CHILLER BODY · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- UP TO 2.3 CHILLER BODY · SRD · [DATA] 130*62MM TAPPING BLOCKS: on prod the icecream and EXPLOSIVE 4.9 AND UP bodies price them differently from Burt (missing or one size only); the chillers/freezers match. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · DRD DOOR FITTINGS · [MES] PROD CHILLER MEDIUM DRD DOOR FITTINGS: 2317 DOOR RUBBER quantity formula ends in *0 (ZERO_FORMULA): -R672 per double door. — review by 2026-10-31 (15)
- UP TO 5.5 CHILLER AND 2.3 WIDE · FLOOR · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · FRONT · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · REAR FRAME + FLOOR PLATE · [RULING] Burt gates REAR FRAME + FLOOR PLATE on the DRD flags, so a single-rear-door body carries R0 there; MES always includes the section (R2.4k-R5.5k). Which is right needs Burt/Michael. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · ROOF · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
- UP TO 5.5 CHILLER AND 2.3 WIDE · SIDES · [RULING] PROD prices chiller PU at R334.50/sheet (the September 32D rate) where Burt's chiller sheets hard-code a 2018 rate (3090 -> R185.20/sheet): MES +R890 (front) to +R4k (sides) per PU panel. Prod is likely the current one; Burt's sheets need the [1]PU! link. — review by 2026-10-31 (3)
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
