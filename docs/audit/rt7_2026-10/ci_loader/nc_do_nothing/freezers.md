## Costing audit — pack `freezers` — FAIL

- Run: 2026-10-19T14:23:18+00:00 · tolerance 1.0 % · MES: in-process localhost/icb_prodmirror
- Golden: 2026-10-19T12:48:09+00:00 · workbook month 2026-09 · GRP sha256 `ed4d57bcd6d5` · 54 scenarios
- Cells: FLAG 35, ACCEPTED 68, PASS 470, SKIP 117
- Full report: `nc_freezers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unaccepted differences (35)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| 4.9 & UP FREEZER BODY (2 | FRONT | L4.9 W2.6 H2.56 foam_4g | 6,052.04 | 6,119.32 | 1.11 | FLAG | BOTH PU (+67.35) |
| 4.9 & UP FREEZER BODY (2 | FRONT | L6.5 W2.6 H2.56 foam_4g | 6,052.04 | 6,119.32 | 1.11 | FLAG | BOTH PU (+67.35) |
| 4.9 & UP FREEZER BODY (2 | FRONT | L8.2 W2.6 H2.56 foam_4g | 6,052.04 | 6,119.32 | 1.11 | FLAG | BOTH PU (+67.35) |
| 4.9 & UP FREEZER BODY (2 | ROOF | L4.9 W2.6 H2.56 foam_4g | 13,565.13 | 13,792.77 | 1.68 | FLAG | BOTH PU (+227.72) |
| 4.9 & UP FREEZER BODY (2 | ROOF | L6.5 W2.6 H2.56 foam_4g | 17,903.61 | 18,204.82 | 1.68 | FLAG | BOTH PU (+301.33) |
| 4.9 & UP FREEZER BODY (2 | ROOF | L8.2 W2.6 H2.56 foam_4g | 22,513.24 | 22,892.63 | 1.69 | FLAG | BOTH PU (+379.54) |
| 4.9 & UP FREEZER BODY (2 | SIDES | L4.9 W2.6 H2.56 foam_4g | 23,605.66 | 23,878.68 | 1.16 | FLAG | BOTH PU (+273.27) |
| 4.9 & UP FREEZER BODY (2 | SIDES | L6.5 W2.6 H2.56 foam_4g | 31,113.56 | 31,474.82 | 1.16 | FLAG | BOTH PU (+361.59) |
| 4.9 & UP FREEZER BODY (2 | SIDES | L8.2 W2.6 H2.56 foam_4g | 39,090.70 | 39,545.73 | 1.16 | FLAG | BOTH PU (+455.45) |
| UP TO 2,3 MTR FREEZER | DRD | L1.8 W1.68 H1.39 foam_4g | 3,923.40 | 3,990.73 | 1.72 | FLAG | BOTH PU (+67.35) |
| UP TO 2,3 MTR FREEZER | DRD | L2.31 W1.68 H1.39 foam_4g | 3,923.40 | 3,990.73 | 1.72 | FLAG | BOTH PU (+67.35) |
| UP TO 2,3 MTR FREEZER | FRONT | L1.8 W1.68 H1.39 foam_4g | 3,165.41 | 3,232.75 | 2.13 | FLAG | BOTH PU (+67.35) |
| UP TO 2,3 MTR FREEZER | FRONT | L2.31 W1.68 H1.39 foam_4g | 3,165.41 | 3,232.75 | 2.13 | FLAG | BOTH PU (+67.35) |
| UP TO 2,3 MTR FREEZER | SIDES | L1.8 W1.68 H1.39 foam_4g | 5,834.44 | 5,936.54 | 1.75 | FLAG | BOTH PU (+102.13) |
| UP TO 2,3 MTR FREEZER | SIDES | L2.31 W1.68 H1.39 foam_4g | 7,363.74 | 7,493.98 | 1.77 | FLAG | BOTH PU (+130.28) |
| UP TO 4.8 MT FREEZER  (2 | DRD | L3 W2.5 H2.4 foam_4g | 6,458.11 | 6,525.42 | 1.04 | FLAG | BOTH PU (+67.35) |
| UP TO 4.8 MT FREEZER  (2 | DRD | L4.2 W2.5 H2.4 foam_4g | 6,458.11 | 6,525.42 | 1.04 | FLAG | BOTH PU (+67.35) |
| UP TO 4.8 MT FREEZER  (2 | DRD | L4.8 W2.5 H2.4 foam_4g | 6,458.11 | 6,525.42 | 1.04 | FLAG | BOTH PU (+67.35) |
| UP TO 4.8 MT FREEZER  (2 | DRD | L5.6 W2.5 H2.4 foam_4g | 6,458.11 | 6,525.42 | 1.04 | FLAG | BOTH PU (+67.35) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L3 W2.5 H2.4 foam_4g | 26,117.91 | 26,571.68 | 1.74 | FLAG ACCEPTED_AMOUNT_CHANGED entry 4 pinned +347.13; actual +453.77 | PRICE_DIFF 12MM PF PLYWOOD (+347.16) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L4.2 W2.5 H2.4 foam_4g | 35,821.39 | 36,453.69 | 1.76 | FLAG ACCEPTED_AMOUNT_CHANGED entry 4 pinned +483.71; actual +632.30 | PRICE_DIFF 12MM PF PLYWOOD (+483.73) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L4.8 W2.5 H2.4 foam_4g | 40,673.13 | 41,394.70 | 1.77 | FLAG ACCEPTED_AMOUNT_CHANGED entry 4 pinned +552.00; actual +721.57 | PRICE_DIFF 12MM PF PLYWOOD (+552.03) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L5.6 W2.5 H2.4 foam_4g | 47,142.11 | 47,982.71 | 1.78 | FLAG ACCEPTED_AMOUNT_CHANGED entry 4 pinned +643.05; actual +840.60 | PRICE_DIFF 12MM PF PLYWOOD (+643.08) |
| UP TO 4.8 MT FREEZER  (2 | FRONT | L3 W2.5 H2.4 foam_4g | 5,691.12 | 5,758.42 | 1.18 | FLAG | BOTH PU (+67.35) |
| UP TO 4.8 MT FREEZER  (2 | FRONT | L4.2 W2.5 H2.4 foam_4g | 5,691.12 | 5,758.42 | 1.18 | FLAG | BOTH PU (+67.35) |
| UP TO 4.8 MT FREEZER  (2 | FRONT | L4.8 W2.5 H2.4 foam_4g | 5,691.12 | 5,758.42 | 1.18 | FLAG | BOTH PU (+67.35) |
| UP TO 4.8 MT FREEZER  (2 | FRONT | L5.6 W2.5 H2.4 foam_4g | 5,691.12 | 5,758.42 | 1.18 | FLAG | BOTH PU (+67.35) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L3 W2.5 H2.4 foam_4g | 7,269.63 | 7,376.22 | 1.47 | FLAG | BOTH PU (+106.64) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L4.2 W2.5 H2.4 foam_4g | 10,085.26 | 10,233.79 | 1.47 | FLAG | BOTH PU (+148.59) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L4.8 W2.5 H2.4 foam_4g | 11,493.08 | 11,662.57 | 1.48 | FLAG | BOTH PU (+169.57) |
| UP TO 4.8 MT FREEZER  (2 | ROOF | L5.6 W2.5 H2.4 foam_4g | 13,370.16 | 13,567.61 | 1.48 | FLAG | BOTH PU (+197.54) |
| UP TO 4.8 MT FREEZER  (2 | SIDES | L3 W2.5 H2.4 foam_4g | 14,190.09 | 14,358.31 | 1.19 | FLAG | BOTH PU (+168.38) |
| UP TO 4.8 MT FREEZER  (2 | SIDES | L4.2 W2.5 H2.4 foam_4g | 19,628.30 | 19,862.72 | 1.19 | FLAG | BOTH PU (+234.63) |
| UP TO 4.8 MT FREEZER  (2 | SIDES | L4.8 W2.5 H2.4 foam_4g | 22,347.41 | 22,614.92 | 1.20 | FLAG | BOTH PU (+267.75) |
| UP TO 4.8 MT FREEZER  (2 | SIDES | L5.6 W2.5 H2.4 foam_4g | 25,972.88 | 26,284.52 | 1.20 | FLAG | BOTH PU (+311.91) |

### Known defects — accepted, tracked, awaiting a work order (24 cells)

- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [BURT] SMALL MOUNTING BRACKET on FREEZER MEDIUM: Burt's sheet prices BIG and SMALL at R68.80 (G178 / G179); the MES prices the small bracket on its own (-R125.68). Burt to decide (fix list B-08). — review by 2026-11-30 (24)

### Tolerated differences (44 cells)

- UP TO 4.8 MT FREEZER  (2 · DRD DOOR FITTINGS · [MES AHEAD] FREEZER MEDIUM DRD DOOR FITTINGS: Michael changed prod on purpose - CSLB HINGES 6 -> 4 on the double rear door (bom 2447; -R293.46 = 2 x R146.73); Burt's sheet has not caught up (keep in step: E-03). — review by 2026-11-30 (20)
- UP TO 4.8 MT FREEZER  (2 · FLOOR · [MES AHEAD] FREEZER MEDIUM FLOOR: Michael changed prod on purpose - 12MM PF PLYWOOD R223.15 -> R267.79 per m2 (bom 2483 lost its /2.98 and material 956 went R665 -> R267.79, 6 Oct 12:43); on roof_floor_eps also EPS R156.56 -> R206.00 per m2 (materials 127 and 133, 7 Oct); Burt's sheet has not caught up (keep in step: E-01, E-02). — review by 2026-11-30 (20)
- UP TO 4.8 MT FREEZER  (2 · ROOF · [MES AHEAD] FREEZER MEDIUM ROOF: Michael changed prod on purpose - EPS R156.56 -> R206.00 per m2 (materials 127 and 133, 7 Oct; roof_floor_eps); Burt's sheet has not caught up (keep in step: E-02). — review by 2026-11-30 (4)

### Oracle findings and probe notes

- UP TO 2,3 MTR FREEZER: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (12)
