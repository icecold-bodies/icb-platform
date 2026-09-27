"""v1.57.2: an accepted entry must EXPLAIN a FLAG cell's difference, and renamed
lines pair up instead of showing as a big missing + a big extra."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.costing_audit.accepted import Accepted                                  # noqa: E402
from tools.costing_audit.compare import compare_scenario, triage_lines, regroup_renames, LineTriage  # noqa: E402
from tests.costing_audit.test_compare import _golden, _gsec, _line, _mes, _ml       # noqa: E402

FAR = date(2099, 1, 1)


def _acc(cause, i=0, kind="known_defect", reason=None):
    return Accepted(body="*", section="*", variant="*", reason=reason or f"entry {i}", owner="BA",
                    review_by=FAR, index=i, kind=kind, cause=cause)


def _door_case():
    """Burt: one 130*62MM TAPPING BLOCKS line R936 + EPS R432. MES: the blocks as
    two renamed lines (R468 + R468 = R936, nets to zero) and NO EPS line."""
    g = _golden({"DRD": _gsec([_line("DOOR SKIN", 4.0, 100.0), _line("130*62MM TAPPING BLOCKS", 1.0, 936.0),
                              _line("EPS", 3.175, 135.96)])})
    m = _mes({"DRD": [_ml("DRD", "DOOR SKIN", 4.0, 100.0), _ml("DRD", "TAPPING BLOCKS_200MM", 6.0, 78.0),
                      _ml("DRD", "TAPPING BLOCKS_250MM", 6.0, 78.0)]})
    return g, m


def test_renamed_lines_pair_up_and_the_real_cause_surfaces():
    g, m = _door_case()
    cell = next(c for c in compare_scenario(g, m, tolerance_pct=1.0, accepted=[]) if c.section_excel == "DRD")
    by = {t.desc: t for t in cell.triage}
    grouped = by["130*62MM TAPPING BLOCKS ~ TAPPING BLOCKS_200MM + TAPPING BLOCKS_250MM"]
    assert grouped.cls == "OK" and grouped.delta == 0.0
    assert by["EPS"].cls == "MISSING_IN_MES"
    assert cell.likely_cause.startswith("MISSING_IN_MES EPS (-431.")


def test_an_entry_that_does_not_explain_the_difference_leaves_a_flag():
    g, m = _door_case()
    cell = next(c for c in compare_scenario(g, m, tolerance_pct=1.0, accepted=[_acc("TAPPING BLOCKS")])
                if c.section_excel == "DRD")
    assert cell.status == "FLAG"                   # the blocks net to zero; the EPS line is unexplained
    cell = next(c for c in compare_scenario(g, m, tolerance_pct=1.0, accepted=[_acc("EPS")])
                if c.section_excel == "DRD")
    assert cell.status == "ACCEPTED"


def test_partial_explanation_says_what_is_left_and_two_entries_combine():
    g = _golden({"SRD": _gsec([_line("DOOR SKIN", 4.0, 100.0), _line("EPS", 4.0, 125.0), _line("PLYWOOD", 4.0, 0.0, total=0.0)])})
    m = _mes({"SRD": [_ml("SRD", "DOOR SKIN", 4.0, 100.0), _ml("SRD", "EPS", 0.0, 125.0, formula="w*h*0"),
                      _ml("SRD", "PLYWOOD", 4.0, 84.0)]})
    one = next(c for c in compare_scenario(g, m, tolerance_pct=1.0, accepted=[_acc("EPS", 0)]) if c.section_excel == "SRD")
    assert one.status == "FLAG"
    assert "explain -500.00 of -164.00" in one.reason and "unexplained +336.00" in one.reason
    both = next(c for c in compare_scenario(g, m, tolerance_pct=1.0,
                                            accepted=[_acc("EPS", 0, reason="eps x0"), _acc("PLYWOOD", 1, reason="ply")])
                if c.section_excel == "SRD")
    assert both.status == "ACCEPTED"
    assert both.accepted["reason"] == "eps x0" and both.accepted["also"][0]["reason"] == "ply"


def test_presence_cells_are_judged_on_the_reason():
    g = _golden({"REAR FRAME": _gsec([_line("FRAME", 1.0, 700.0, total=0.0)])})
    m = _mes({"REAR FRAME": [_ml("REAR FRAME", "FRAME", 1.0, 700.0)]})
    cell = next(c for c in compare_scenario(g, m, tolerance_pct=1.0, accepted=[_acc("EXTRA_IN_MES")])
                if c.section_excel == "REAR FRAME")
    assert cell.base_status == "PRESENCE" and cell.status == "ACCEPTED"


def test_regroup_on_saved_triage_is_idempotent():
    tri = [LineTriage("130*62MM TAPPING BLOCKS", 1, 936, 936, None, None, None, -936, "MISSING_IN_MES"),
           LineTriage("TAPPING BLOCKS_200MM", None, None, None, 6, 78, 468, 468, "EXTRA_IN_MES"),
           LineTriage("TAPPING BLOCKS_250MM", None, None, None, 6, 78, 468, 468, "EXTRA_IN_MES"),
           LineTriage("GLUE LINE", 1, 1, 1, 1, 1, 1, 0, "OK")]
    once = regroup_renames(tri)
    assert [t.cls for t in once] == ["OK", "OK"]
    assert regroup_renames(once) == once
    tri2, cause = triage_lines([_line("1MM GALV PLATE", 1.0, 240.0)], [_ml("S", "1.2MM GALV PLATE", 1.0, 450.0)])
    assert tri2[0].cls == "GROUP_DIFF" and tri2[0].desc == "1MM GALV PLATE ~ 1.2MM GALV PLATE"
    assert cause.startswith("GROUP_DIFF 1MM GALV PLATE ~ 1.2MM GALV PLATE (+210.00)")
