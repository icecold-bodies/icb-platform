## Costing audit — pack `smoke` — PASS

- Run: 2026-10-19T14:22:11+00:00 · tolerance 1.0 % · MES: in-process localhost/icb_prodmirror
- Golden: 2026-10-19T12:43:28+00:00 · workbook month 2026-09 · GRP sha256 `ed4d57bcd6d5` · 18 scenarios
- Cells: ACCEPTED 33, PASS 156, SKIP 45
- Full report: `prod_smoke.html` (CI artifact)

### Known defects — accepted, tracked, awaiting a work order (12 cells)

- UP TO 4.8 MT FREEZER  (2 · SUB FRAME + LIGHT BOX ASSY · [BURT] SMALL MOUNTING BRACKET on FREEZER MEDIUM: Burt's sheet prices BIG and SMALL at R68.80 (G178 / G179); the MES prices the small bracket on its own (-R125.68). Burt to decide (fix list B-08). — review by 2026-11-30 (6)
- icecream up to 4.8 · FLOOR · [PROBE] ICECREAM UP TO 4.8's 12MM PF PLYWOOD floor line (bom 5653) prices only when its draft choice is ticked; the audit probe cannot tick a draft choice, so the FLOOR reads it missing. A probe limit, not a template defect (Michael, 28 Sep). — review by 2026-11-30 (6)

### Tolerated differences (21 cells)

- UP TO 4.8 MT FREEZER  (2 · DRD DOOR FITTINGS · [MES AHEAD] FREEZER MEDIUM DRD DOOR FITTINGS: Michael changed prod on purpose - CSLB HINGES 6 -> 4 on the double rear door (bom 2447; -R293.46 = 2 x R146.73); Burt's sheet has not caught up (keep in step: E-03). — review by 2026-11-30 (6)
- UP TO 4.8 MT FREEZER  (2 · FLOOR · [MES AHEAD] FREEZER MEDIUM FLOOR: Michael changed prod on purpose - 12MM PF PLYWOOD R223.15 -> R267.79 per m2 (bom 2483 lost its /2.98 and material 956 went R665 -> R267.79, 6 Oct 12:43); on roof_floor_eps also EPS R156.56 -> R206.00 per m2 (materials 127 and 133, 7 Oct); Burt's sheet has not caught up (keep in step: E-01, E-02). — review by 2026-11-30 (6)
- UP TO 4.8 MT FREEZER  (2 · ROOF · [MES AHEAD] FREEZER MEDIUM ROOF: Michael changed prod on purpose - EPS R156.56 -> R206.00 per m2 (materials 127 and 133, 7 Oct; roof_floor_eps); Burt's sheet has not caught up (keep in step: E-02). — review by 2026-11-30 (3)
- icecream up to 4.8 · SRD · [BURT SLIP] Burt's rear-door TAPPING row prices the buffer plate, not the tapping blocks: 'icecream up to 3,2'!E41 and 'icecream up to 4.8'!E45 = '[2]SRD FLOOR PLATE'!$F$24*3 instead of TAPING BLOCKS (+R259.72 per door section on Burt's side). MES is right. Clears with Burt's fix list B-01, B-02. — review by 2026-11-30 (6)

### Oracle findings and probe notes

- UP TO 5.5 CHILLER AND 2.3 WIDE: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '1ST ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master '2ND ROW ALU KICK PLATE' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'ALU EXTRUTION FLOOR' has no flag on the sheet — left at body default OFF (6)
- icecream up to 4.8: MES master 'RICE GRAIN ALU FLOOR' has no flag on the sheet — left at body default OFF (6)
