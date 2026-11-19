## Costing audit — pack `freezers` — FAIL

- Run: 2026-11-18T15:09:27+00:00 · tolerance 1.0 % · MES: in-process 127.0.0.1/icb_platform
- Golden: 2026-10-19T12:48:09+00:00 · workbook month 2026-09 · GRP sha256 `ed4d57bcd6d5` · 54 scenarios
- Cells: FLAG 16, ACCEPTED 64, PASS 493, SKIP 117
- Full report: `prod_freezers.html` (CI artifact)
- ⚠ accepted list: accepted_differences.prod.yaml (--env prod)

### Unaccepted differences (16)

| body | section | scenario | Excel | MES | var % | status | likely cause |
|---|---|---|---:|---:|---:|---|---|
| UP TO 2,3 MTR FREEZER | FLOOR | L1.8 W1.68 H1.39 all_pu | 5,758.93 | 6,112.26 | 6.13 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+714.19) |
| UP TO 2,3 MTR FREEZER | FLOOR | L2.31 W1.68 H1.39 all_pu | 7,070.43 | 7,521.16 | 6.38 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+911.08) |
| UP TO 2,3 MTR FREEZER | FLOOR | L1.8 W1.68 H1.39 as_sheet | 4,854.95 | 5,208.28 | 7.28 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+714.19) |
| UP TO 2,3 MTR FREEZER | FLOOR | L2.31 W1.68 H1.39 as_sheet | 5,917.24 | 6,367.97 | 7.62 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+911.08) |
| UP TO 2,3 MTR FREEZER | FLOOR | L1.8 W1.68 H1.39 drd | 4,854.95 | 5,208.28 | 7.28 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+714.19) |
| UP TO 2,3 MTR FREEZER | FLOOR | L2.31 W1.68 H1.39 drd | 5,917.24 | 6,367.97 | 7.62 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+911.08) |
| UP TO 2,3 MTR FREEZER | FLOOR | L1.8 W1.68 H1.39 foam_4g | 4,854.95 | 5,208.28 | 7.28 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+714.19) |
| UP TO 2,3 MTR FREEZER | FLOOR | L2.31 W1.68 H1.39 foam_4g | 5,917.24 | 6,367.97 | 7.62 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+911.08) |
| UP TO 2,3 MTR FREEZER | FLOOR | L1.8 W1.68 H1.39 roof_floor_eps | 4,854.95 | 5,208.28 | 7.28 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+714.19) |
| UP TO 2,3 MTR FREEZER | FLOOR | L2.31 W1.68 H1.39 roof_floor_eps | 5,917.24 | 6,367.97 | 7.62 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+911.08) |
| UP TO 2,3 MTR FREEZER | FLOOR | L1.8 W1.68 H1.39 srd | 4,854.95 | 5,208.28 | 7.28 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+714.19) |
| UP TO 2,3 MTR FREEZER | FLOOR | L2.31 W1.68 H1.39 srd | 5,917.24 | 6,367.97 | 7.62 | FLAG | EXTRA_IN_MES 9 MM FINN PLYWOOD (+911.08) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L3 W2.5 H2.4 roof_floor_eps | 24,284.64 | 24,631.77 | 1.43 | FLAG ACCEPTED_AMOUNT_CHANGED entry 4 pinned +731.65; actual +347.13 | PRICE_DIFF 12MM PF PLYWOOD (+347.16) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L4.2 W2.5 H2.4 roof_floor_eps | 33,266.83 | 33,750.54 | 1.45 | FLAG ACCEPTED_AMOUNT_CHANGED entry 4 pinned +1019.51; actual +483.71 | PRICE_DIFF 12MM PF PLYWOOD (+483.73) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L4.8 W2.5 H2.4 roof_floor_eps | 37,757.93 | 38,309.92 | 1.46 | FLAG ACCEPTED_AMOUNT_CHANGED entry 4 pinned +1163.44; actual +551.99 | PRICE_DIFF 12MM PF PLYWOOD (+552.03) |
| UP TO 4.8 MT FREEZER  (2 | FLOOR | L5.6 W2.5 H2.4 roof_floor_eps | 43,746.05 | 44,389.10 | 1.47 | FLAG ACCEPTED_AMOUNT_CHANGED entry 4 pinned +1355.36; actual +643.05 | PRICE_DIFF 12MM PF PLYWOOD (+643.08) |

### Known defects — accepted, tracked, awaiting a work order (24 cells)

- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [BURT] SMALL MOUNTING BRACKET on FREEZER MEDIUM: Burt's sheet prices BIG and SMALL at R68.80 (G178 / G179); the MES prices the small bracket on its own (-R125.68). Burt to decide (fix list B-08). — review by 2026-11-30 (24)

### Tolerated differences (40 cells)

- UP TO 4.8 MT FREEZER  (2 · DRD DOOR FITTINGS · [MES AHEAD] FREEZER MEDIUM DRD DOOR FITTINGS: Michael changed prod on purpose - CSLB HINGES 6 -> 4 on the double rear door (bom 2447; -R293.46 = 2 x R146.73); Burt's sheet has not caught up (keep in step: E-03). — review by 2026-11-30 (20)
- UP TO 4.8 MT FREEZER  (2 · FLOOR · [MES AHEAD] FREEZER MEDIUM FLOOR: Michael changed prod on purpose - 12MM PF PLYWOOD R223.15 -> R267.79 per m2 (bom 2483 lost its /2.98 and material 956 went R665 -> R267.79, 6 Oct 12:43); on roof_floor_eps also EPS R156.56 -> R206.00 per m2 (materials 127 and 133, 7 Oct); Burt's sheet has not caught up (keep in step: E-01, E-02). — review by 2026-11-30 (20)

### Oracle findings and probe notes

- UP TO 2,3 MTR FREEZER: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (12)
- UP TO 2,3 MTR FREEZER: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (12)
