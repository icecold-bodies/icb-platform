## Costing audit — pack `freezers` — PASS

- Run: 2026-10-22T10:40:22+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-19T12:48:09+00:00 · workbook month 2026-09 · GRP sha256 `ed4d57bcd6d5` · 54 scenarios
- Cells: ACCEPTED 72, PASS 501, SKIP 117
- Full report: `prod_freezers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Known defects — accepted, tracked, awaiting a work order (24 cells)

- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [BURT] SMALL MOUNTING BRACKET on FREEZER MEDIUM: Burt's sheet prices BIG and SMALL at R68.80 (G178 / G179); the MES prices the small bracket on its own (-R125.68). Burt to decide (fix list B-08). — review by 2026-11-30 (24)

### Tolerated differences (48 cells)

- UP TO 4.8 MT FREEZER  (2 · DRD DOOR FITTINGS · [MES AHEAD] FREEZER MEDIUM DRD DOOR FITTINGS: Michael changed prod on purpose - CSLB HINGES 6 -> 4 on the double rear door (bom 2447; -R293.46 = 2 x R146.73); Burt's sheet has not caught up (keep in step: E-03). — review by 2026-11-30 (20)
- UP TO 4.8 MT FREEZER  (2 · FLOOR · [MES AHEAD] FREEZER MEDIUM FLOOR: Michael changed prod on purpose - 12MM PF PLYWOOD R223.15 -> R267.79 per m2 (bom 2483 lost its /2.98 and material 956 went R665 -> R267.79, 6 Oct 12:43); on roof_floor_eps also EPS R156.56 -> R206.00 per m2 (materials 127 and 133, 7 Oct); Burt's sheet has not caught up (keep in step: E-01, E-02). — review by 2026-11-30 (24)
- UP TO 4.8 MT FREEZER  (2 · ROOF · [MES AHEAD] FREEZER MEDIUM ROOF: Michael changed prod on purpose - EPS R156.56 -> R206.00 per m2 (materials 127 and 133, 7 Oct; roof_floor_eps); Burt's sheet has not caught up (keep in step: E-02). — review by 2026-11-30 (4)

### Oracle findings and probe notes

- UP TO 2,3 MTR FREEZER: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (12)
