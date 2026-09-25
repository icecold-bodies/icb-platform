"""Sheet-map discovery on the synthetic workbook (no Burt data, no LibreOffice)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.costing_audit.sheet_map import discover_sheet, render_text   # noqa: E402
from tests.costing_audit.synthetic import build_workbook                # noqa: E402


def test_discovers_inputs_flags_and_sections():
    f, v, exp = build_workbook()
    sm = discover_sheet(f, v)
    assert sm.label_col == "A"
    assert sm.inputs == {"LENGTH": "C4", "WIDTH": "C5", "HEIGHT": "C6"}
    assert sm.input_values == {"LENGTH": 5.0, "WIDTH": 2.0, "HEIGHT": 2.0}
    assert [x.label for x in sm.flags] == ["FRONT EPS", "FRONT PU", "DRD EPS", "DRD PU", "RICE GRAIN FLOOR"]
    assert sm.flag_by_label("front pu").flag_cell == "D9"
    assert [s.name for s in sm.sections] == ["FRONT", "DRD", "DRD DOOR FITTINGS", "SIDES", "SPRAY PAINTING"]
    assert sm.selfcheck_ok, sm.warnings
    assert sm.grand_total_cell == "J44"


def test_section_geometry_and_gates():
    f, v, exp = build_workbook()
    sm = discover_sheet(f, v)
    by = {s.name: s for s in sm.sections}
    front = by["FRONT"]
    assert (front.header_row, front.total_row) == (15, 19)
    assert (front.qty_col, front.price_col, front.total_col) == ("F", "G", "H")
    assert [l.desc for l in front.lines] == ["SKIN", "EPS", "PU"]
    assert front.gated_cells == ["J19"]
    assert front.cached_total == pytest.approx(exp["FRONT"])
    drd = by["DRD"]
    # both the EPS-gated TOTAL row and the PU-gated row below it are the section's money
    assert drd.gated_cells == ["J25", "J26"]
    assert [g.flag_labels for g in drd.gate_cells] == [["DRD EPS"], ["DRD PU"]]
    fittings = by["DRD DOOR FITTINGS"]
    assert (fittings.qty_col, fittings.price_col, fittings.total_col) == ("D", "E", "F")
    assert fittings.gated_cells == ["J32", "J33"]
    sides = by["SIDES"]
    assert sides.cached_total == pytest.approx(exp["SIDES"])       # the x2 is in J
    spray = by["SPRAY PAINTING"]
    assert spray.header_row is None and spray.total_row is None
    assert spray.gated_cells == ["J42"] and spray.cached_total == 750.0


def test_selfcheck_detects_a_broken_grand_total():
    """Prove the check can fail: a grand total that does not equal the section sum."""
    f, v, exp = build_workbook()
    v["J44"] = exp["GRAND"] + 100.0
    sm = discover_sheet(f, v)
    assert sm.selfcheck_ok is False
    assert any("self-check" in w for w in sm.warnings)


def test_stale_link_marks_line_and_section_unverifiable():
    f, v, exp = build_workbook(stale_rivets=True)
    sm = discover_sheet(f, v, stale_links={3: "PRICE 20.04.2004.xls"})
    fittings = next(s for s in sm.sections if s.name == "DRD DOOR FITTINGS")
    assert [l.stale_link for l in fittings.lines] == [False, True]
    assert fittings.unverifiable == "STALE_LINK"
    assert all(s.unverifiable is None for s in sm.sections if s.name != "DRD DOOR FITTINGS")


def test_override_pins_label_col_and_renames():
    f, v, exp = build_workbook()
    sm = discover_sheet(f, v, override={"label_col": "A", "rename": {"SPRAY PAINTING": "PAINT"},
                                        "ignore": ["SIDES"]})
    names = [s.name for s in sm.sections]
    assert "PAINT" in names and "SIDES" not in names
    assert sm.source == "override"


def test_render_text_mentions_every_section():
    f, v, exp = build_workbook()
    text = render_text(discover_sheet(f, v))
    for name in ("FRONT", "DRD DOOR FITTINGS", "SIDES", "self-check OK"):
        assert name in text
