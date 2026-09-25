"""A small synthetic costing workbook in Burt's shape — no ICB data.

`build_workbook()` returns (formulas workbook, values workbook) laid out like a
body sheet: LENGTH/WIDTH/HEIGHT at C4:C6, the flag block at A8:D13 (FRONT and
DRD EPS/PU pairs + one other flag), then FRONT, DRD, DRD DOOR FITTINGS, SIDES
(x2) and SPRAY PAINTING sections with gate cells, and a GRAND TOTAL.

The values twin is what a recalculated copy would read as: every formula
cell's value is computed here in Python from the same inputs, so tests of the
map/oracle read path do not need LibreOffice.
"""
from __future__ import annotations

from openpyxl import Workbook

SHEET = "TEST BODY"
PU_RATE_REF = "[1]PU!$C$17"


def _wb_pair():
    return Workbook(), Workbook()


def build_workbook(*, length=5.0, width=2.0, height=2.0, front="eps", drd="eps", other_flag="N",
                   pu_ref=PU_RATE_REF, stale_rivets=False):
    """Returns (ws_formulas, ws_values, expected) for one sheet named TEST BODY.
    `expected` holds the section totals the values twin encodes."""
    wf, wv = _wb_pair()
    f, v = wf.active, wv.active
    f.title = v.title = SHEET
    t = 0.05     # thickness used for whichever side is on
    front_eps, front_pu = (t, 0.0) if front == "eps" else (0.0, t)
    drd_eps, drd_pu = (t, 0.0) if drd == "eps" else (0.0, t)

    def both(cell, formula, value):
        f[cell] = formula
        v[cell] = value

    def lit(cell, value):
        f[cell] = value
        v[cell] = value

    lit("A4", "LENGTH"); lit("C4", length)
    lit("A5", "WIDTH"); lit("C5", width)
    lit("A6", "HEIGHT"); lit("C6", height)
    flags = [("FRONT EPS", front_eps), ("FRONT PU", front_pu), ("DRD EPS", drd_eps), ("DRD PU", drd_pu)]
    for i, (lab, th) in enumerate(flags, start=8):
        lit(f"A{i}", lab); lit(f"C{i}", th); lit(f"D{i}", "Y" if th > 0 else "N")
    lit("A12", "RICE GRAIN FLOOR"); lit("D12", other_flag)

    # FRONT: label r14, header r15, lines r16-18, TOTAL r19
    lit("A14", "FRONT")
    for c, h in zip("DEFGH", ("WIDTH", "HEIGHT", "M2", "PRICE", "TOTAL")):
        lit(f"{c}15", h)
    area = width * height
    lit("A16", "SKIN"); both("F16", "=C5*C6", area); lit("G16", 100.0); both("H16", "=G16*F16", 100.0 * area)
    lit("A17", "EPS"); both("F17", "=F16", area); lit("G17", 50.0)
    both("I17", '=IF(D8="Y",1,0)', 1 if front_eps else 0)
    both("H17", "=G17*F17*I17", 50.0 * area * (1 if front_eps else 0))
    lit("A18", "PU"); both("F18", "=F16", area)
    both("G18", f"=C9*{pu_ref}/2.98", 0.05 * 4000 / 2.98 if front_pu else 0.0)
    both("I18", '=IF(D9="Y",1,0)', 1 if front_pu else 0)
    pu_line = (0.05 * 4000 / 2.98) * area * (1 if front_pu else 0)
    both("H18", "=G18*F18*I18", pu_line)
    front_total = 100.0 * area + 50.0 * area * (1 if front_eps else 0) + pu_line
    lit("G19", "TOTAL"); both("H19", "=SUM(H16:H18)", front_total); both("J19", "=H19", front_total)

    # DRD: label r21, header r22, lines r23-24, TOTAL r25 (EPS-gated) + r26 (PU-gated)
    lit("A21", "DRD")
    for c, h in zip("DEFGH", ("WIDTH", "HEIGHT", "M2", "PRICE", "TOTAL")):
        lit(f"{c}22", h)
    lit("A23", "DOOR SKIN"); both("F23", "=C5*C6", area); lit("G23", 80.0); both("H23", "=G23*F23", 80.0 * area)
    lit("A24", "GLUE LINE"); both("F24", "=F23", area); lit("G24", 10.0); both("H24", "=G24*F24", 10.0 * area)
    drd_raw = 90.0 * area
    lit("G25", "TOTAL"); both("H25", "=SUM(H23:H24)", drd_raw)
    both("I25", '=IF(D10 ="Y",1,0)', 1 if drd_eps else 0); both("J25", "=I25*H25", drd_raw * (1 if drd_eps else 0))
    both("H26", "=H25", drd_raw); both("I26", '=IF(D11 ="Y",1,0)', 1 if drd_pu else 0)
    both("J26", "=I26*H26", drd_raw * (1 if drd_pu else 0))
    drd_total = drd_raw * (1 if (drd_eps or drd_pu) else 0)

    # DOOR FITTINGS (bare label -> "DRD DOOR FITTINGS"): label r28, header r29, lines r30-31, TOTAL r32
    lit("A28", "DOOR FITTINGS")
    for c, h in zip("DEF", ("QUANT", "PRICE", "TOTAL")):
        lit(f"{c}29", h)
    lit("A30", "HINGES"); lit("D30", 2); lit("E30", 150.0); both("F30", "=E30*D30", 300.0)
    lit("A31", "RIVETS"); lit("D31", 10)
    if stale_rivets:
        both("E31", "=[3]RIVETS!$C$5", 0.5)
    else:
        lit("E31", 0.5)
    both("F31", "=E31*D31", 5.0)
    lit("E32", "TOTAL"); both("F32", "=SUM(F30:F31)", 305.0)
    both("I32", '=IF(D10 ="Y",1,0)', 1 if drd_eps else 0); both("J32", "=F32*I32", 305.0 * (1 if drd_eps else 0))
    both("I33", '=IF(D11 ="Y",1,0)', 1 if drd_pu else 0); both("J33", "=F32*I33", 305.0 * (1 if drd_pu else 0))
    fittings_total = 305.0 * (1 if (drd_eps or drd_pu) else 0)

    # SIDES x2: label r35, header r36, line r37, TOTAL r38 with J = H*2
    lit("A35", "SIDES")
    for c, h in zip("DEFGH", ("LENGTH", "HEIGHT", "M2", "PRICE", "TOTAL")):
        lit(f"{c}36", h)
    side_area = length * height
    lit("A37", "SKIN"); both("F37", "=C4*C6", side_area); lit("G37", 100.0); both("H37", "=G37*F37", 100.0 * side_area)
    lit("G38", "TOTAL"); both("H38", "=SUM(H37:H37)", 100.0 * side_area); both("J38", "=H38*2", 200.0 * side_area)
    sides_total = 200.0 * side_area

    # SPRAY PAINTING: label only, one line carrying J directly
    lit("A40", "SPRAY PAINTING")
    lit("A42", "PAINT"); lit("H42", 750.0); both("J42", "=H42", 750.0)

    lit("G44", "GRAND TOTAL")
    grand = front_total + drd_total + fittings_total + sides_total + 750.0
    both("J44", "=SUM(J19:J43)", grand)
    expected = {"FRONT": front_total, "DRD": drd_total, "DRD DOOR FITTINGS": fittings_total,
                "SIDES": sides_total, "SPRAY PAINTING": 750.0, "GRAND": grand}
    return f, v, expected
