# Costing audit — first full run, September 2026 workbook

**Lane:** v1.57 `feat/v1.57-costing-audit` · **Run:** 25 Sep 2026 · **MES:** dev `icb` (in-process, the
`/api/calculate` code path) · **Workbook:** `GRP Costings 2018.xlsx` sha256 `d87a573177dc…` + PRICE 2017 MARCH +
FORMULAS 2018, recalculated by LibreOffice 26.8 · **Tolerance:** 1.0 % per section.

This folder holds the four pack reports (`costing_audit_<pack>.html` — open in a browser, click a cell → section
table → line triage; `.csv`; `.md` summary) and `discover_tick_through.txt`, the auto-detected cell map of the three
§3.0 sheets for Michael's one-time tick-through. Later runs are CI artifacts, not committed.

| pack | scenarios | PASS | ACCEPTED (tracked) | UNVERIFIABLE | SKIP | unaccepted |
|---|---:|---:|---:|---:|---:|---:|
| smoke (3 bodies × 3 lengths × 2 variants) | 18 | 135 | 54 | 9 | 36 | **0** |
| chillers (2.3 / 5.5 / 4.9 & UP) | 84 | 662 | 244 | 0 | 168 | **0** |
| freezers (2.3 / 4.8 / 4.9 & UP) | 54 | 427 | 128 | 27 | 108 | **0** |
| icecream (3,2 / 4.8 / 4.9 up) | 48 | 294 | 182 | 40 | 96 | **0** |

`ACCEPTED` is not "right": every accepted cell is covered by an entry in
`backend/tests/costing_audit/accepted_differences.yaml` of kind **known_defect** — the mechanism is diagnosed, the
entry carries a one-line reason and a `review_by: 2026-10-31`, and it renders amber. **That file is the work-order
list.** Delete an entry when its fix lands and CI enforces the fix from then on; an entry left past its review date
turns its cells EXPIRED and fails the gate.

## Findings, ranked by rand impact per quote

Tags: **[MES]** a defect in the MES BOM/formulas · **[DATA]** a price/quantity/line difference between the MES BOM and
Burt's sheet, to reconcile with Burt · **[RULING]** the two sides disagree by design; Michael/Burt must say which is
right. Rand figures are per body at the swept sizes; the triage tables in the HTML carry the exact lines.

1. **[MES] ICECREAM 4.9 UP prices every quote at 6.7 m.** Its SIDES, ROOF, FLOOR, ALUMINIUM, SUB FRAME + LIGHT BOX
   ASSY and REFLEXITE TAPE formulas carry the literal `6.7` where every other body has `length`
   (`(6.7+{Waste})*(height-0.125+{Waste})`, `6.7*2`, …). At 4.9 m MES is **+R10k** over Burt (SIDES +19 %, ROOF
   +19 %, FLOOR +12 %, ALUMINIUM +25 %); above 6.7 m it under-prices. Burt's sheet uses C4.
2. **[MES] PU insulation costs R0 on the chiller bodies** (CHILLER 2.3 METER, CHILLER MEDIUM, CHILLER LARGE) and on
   FREEZER 2.3 METER's roof/floor: the PU lines' quantity formulas end in a literal `×0`
   (`2.44*1.22*0*2`, `1.22*2.44*0*(length+{Waste})/1.22`), baked in at import. Selecting PU in the calculator
   changes the flags and thickness but the line stays R0 — **−R1.1k (FRONT) to −R7.7k (SIDES) per panel**, roughly
   −R10k on a 5.5 m all-PU chiller. The icecream/freezer bodies use `{FRONT PU}`-style tokens and price correctly.
3. **[MES] DRD PU on CHILLER 2.3 METER and CHILLER LARGE is priced at the raw 32D rate** (R4 100 × 2.98 sheets):
   **+R11.6k / +R23.3k** on a PU double rear door, against Burt's R185.20 per sheet.
4. **[MES] ALU EXTRUTION FLOOR defaults ON for ICECREAM UP TO 3,2 and UP TO 4.8** and adds **R13k–R27k** per quote
   (`13 × length` m at R428.95). Burt's icecream sheets have no such line or flag.
5. **[MES] SRD EPS costs R0 on the chillers** (formula ends in `*0`): an EPS single rear door is under-priced by
   R400–R780. On Burt's side the 4MM PF PLYWOOD / GLUE LINE rows under SRD are R0 instead — both sides carry
   dead lines here.
6. **[MES] FREEZER LARGE side panels are sized from WIDTH, not HEIGHT**:
   `(length+{Waste})*(width-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}+{Waste})`. +1.2 % at W 2.6 / H 2.56; grows with the gap.
7. **[RULING] REAR FRAME + FLOOR PLATE on a single-rear-door body.** Burt gates the section on the DRD flags, so an
   SRD body carries R0 there; MES always includes it (**R2.4k–R5.5k**). Every body, every SRD scenario.
8. **[DATA] SRD DOOR FITTINGS prices on every body**: MES CSLB HINGES R293.46 × 2 where Burt has R146.73 × 2 (the
   pair price applied per hinge); SILPLUS X WHITE R232.30 vs R116.15; per body 34MM LOCKING POLE R126 vs R42,
   28782 BIG HORIZ CAPPING R197.20 vs R240.58, ALU CORNERS R45 vs R54.90, 28780 BIG VERTICAL renamed 28778. Burt
   prices 2317 DOOR RUBBER / 28777 DOOR CAPPING at R0 on some sheets. +R400–R900 per single door.
9. **[DATA] 130*62MM TAPPING BLOCKS on every door section**: Burt 2 × R234 per size (R936 a double door), MES
   6 × R68 per size (R816) — R60 per size, 1–3 % of the door section.
10. **[DATA] SUB FRAME + LIGHT BOX ASSY galv plate**: Burt's `1MM GALV PLATE` (R157–R240) has no MES line on
    CHILLER 2.3, CHILLER LARGE and FREEZER MEDIUM; CHILLER MEDIUM prices `1.2MM GALV PLATE` R449.52 instead.
11. **[DATA] small line differences**: 3MM 3CR12 FLOOR PLATE R1 040.16 (MES) vs R965.76 (2.3 freezer, icecream 3,2);
    100*50 LVL Beam quantity rule on FREEZER LARGE (−R640); icecream 4.8 door lines (4MM PF PLYWOOD quantity,
    28779 DOOR CAPPING −R324, 3MM 3CR12 FLOOR PLATE +R77.50).

**What matched.** At the sheets' saved state every non-door section of every body is within tolerance except the
items above — FRONT, ROOF, FLOOR, ALUMINIUM, SUB FRAME, SPRAY PAINTING, REFLEXITE all PASS on the chillers,
freezers and icecream 3,2/4.8 across the length sweeps; DRD and DRD DOOR FITTINGS PASS on CHILLER MEDIUM and
FREEZER MEDIUM once the tapping-block spelling is set aside.

## Unverifiable — the sheet cannot price it (never PASS, never an MES fault)

- **`all_eps` on the freezers and icecream bodies**: Burt's EPS lines on those sheets point at an empty price cell
  (`[1]EPS!$C$16` and kin), so Excel prices EPS at R0 there. 76 cells `EXCEL_NO_PRICE:EPS`.
- **`foam_4g` on the chillers**: their PU lines hard-code `*3090/2.98` (the 2.98 m² sheet at an old rate) with no
  `[1]PU!$C$17` reference, so 4G cannot be expressed on the sheet. MES applies the 4G factor to any PU row.
  (MES carries the same 3090-based R185.20 override on those lines — both sides are off the September PU price.)
- Not in these packs: TAUT LINER RIGID and BAKERY BODIES (different sheet layout — needs a `sheet_map`), the
  `[3] PRICE 20.04.2004.xls` rivet references (STALE_LINK handling is in the tool, the sheet is not in a pack yet).

## Oracle findings about the workbook itself

- UP TO 5.5 CHILLER now carries an **INSULATION CONTROL PANEL** (C2 = All EPS / All PU, L5 = door type,
  L8–L13 = thicknesses) driving its flag block by formula.
- Every sheet has **two gate rows per door section** — the TOTAL row gated on the EPS flag and a second row gated on
  the PU flag — which is why an all-PU sheet still prices its doors. The section total is the sum of both.
- PU price references: 13 sheets use `[1]PU!$C$17` (32D) or `$C$19` (4G) — RHINORANGE all-4G; MEAT BODY, SMALL
  MEAT BODY, EXPLOSIVE 4.9 AND UP mixed (normalised per scenario, recorded as a finding); the three chillers,
  DRY FREIGHT and Adv Vacuum hard-code a rate.
- MES masters with no counterpart flag on the sheet were left at the body default and are listed per scenario
  under "probe notes" (RICE GRAIN FLOOR, kick plates, ALU EXTRUTION FLOOR — the last is finding 4).

## Reproduce

```
cd backend
python -m tools.costing_audit run --pack chillers            # live dev DB, committed golden
python -m tools.costing_audit golden --pack chillers --workbook-dir "C:\Users\micge\Documents\Burt Costing Model\September costings"
```

Tool README: `backend/tools/costing_audit/README.md`.
