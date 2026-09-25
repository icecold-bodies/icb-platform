"""Comparator on fabricated golden vs fabricated MES output: every status,
every triage class, the accepted/expired machinery, and the NEGATIVE CONTROL
(a known 5 % price error must be flagged and named; removing it must PASS)."""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.costing_audit.accepted import Accepted, load_accepted          # noqa: E402
from tools.costing_audit.compare import compare_scenario, build_report, triage_lines   # noqa: E402
from tools.costing_audit.mes_probe import MesResult, MesLine               # noqa: E402
from tools.costing_audit.report import write_all                           # noqa: E402

SHEET = "TEST BODY"


def _golden(sections: dict, *, variant="as_sheet", findings=None) -> dict:
    return {"scenario": {"id": f"t~{variant}", "sheet": SHEET, "trailer_id": 999, "variant": variant,
                         "length": 5.0, "width": 2.0, "height": 2.0, "door": "drd", "foam": "32D",
                         "panels": {}, "flags": {}, "gate_mode": "as_sheet", "section_map": {}},
            "grand_total": sum((s.get("total") or 0.0) for s in sections.values()),
            "findings": findings or [], "sections": sections}


def _gsec(lines, status="OK", reason=None, mult=1.0):
    total = sum((l.get("total") or 0.0) for l in lines) * mult
    return {"total": total, "raw_total": total / mult if mult else None, "status": status, "reason": reason,
            "gates": {}, "lines": lines, "multiplier": mult}


def _line(desc, qty, price, total=None, stale=False):
    return {"desc": desc, "qty": qty, "price": price, "total": qty * price if total is None else total, "stale": stale}


def _mes(sections: dict[str, list[MesLine]], *, extra_sections=None) -> MesResult:
    lines = [l for ls in sections.values() for l in ls]
    totals = {k: sum(l.total for l in ls if not l.excluded) for k, ls in sections.items()}
    totals.update(extra_sections or {})
    return MesResult(trailer_id=999, trailer_name="TEST", sections=totals,
                     grand_total=sum(totals.values()), lines=lines, payload={})


def _ml(section, desc, qty, price, excluded=False, formula=None):
    return MesLine(section=section, desc=desc, qty=qty, price=price, total=qty * price, excluded=excluded, formula=formula)


BASE_GOLDEN = {
    "FRONT": _gsec([_line("SKIN", 4.0, 100.0), _line("EPS", 4.0, 50.0), _line("GLUE LINE", 4.0, 10.0), _line("GLUE LINE", 4.0, 10.0)]),
    "SIDES": _gsec([_line("SKIN", 10.0, 100.0)], mult=2.0),
    "SRD": _gsec([_line("DOOR SKIN", 4.0, 80.0, total=0.0)]),          # gated off: total 0
    "DOOR FITTINGS (STALE)": _gsec([_line("RIVETS", 10, 0.5, stale=True)], status="UNVERIFIABLE", reason="STALE_LINK"),
}


def _base_mes(front_eps_price=50.0):
    return _mes({
        "FRONT": [_ml("FRONT", "SKIN", 4.0, 100.0), _ml("FRONT", "EPS", 4.0, front_eps_price),
                  _ml("FRONT", "GLUE LINE", 4.0, 10.0), _ml("FRONT", "GLUE LINE", 4.0, 10.0)],
        "SIDES": [_ml("SIDES", "SKIN", 20.0, 100.0)],                    # x2 already applied
        "SRD": [],
    })


def test_pass_skip_unverifiable_and_unmapped():
    cells = compare_scenario(_golden(BASE_GOLDEN), _base_mes(), tolerance_pct=1.0, accepted=[])
    by = {c.section_excel: c for c in cells}
    assert by["FRONT"].status == "PASS" and by["FRONT"].variance_pct == 0.0
    assert by["SIDES"].status == "PASS"                    # Excel J (x2) vs MES totals (x2)
    assert by["SRD"].status == "SKIP"                      # both zero: the door not fitted
    assert by["DOOR FITTINGS (STALE)"].status == "UNVERIFIABLE"
    assert by["DOOR FITTINGS (STALE)"].reason == "STALE_LINK"
    g = _golden({**BASE_GOLDEN, "MEAT RAILS": _gsec([_line("RAIL", 2.0, 300.0)])})
    by = {c.section_excel: c for c in compare_scenario(g, _base_mes(), tolerance_pct=1.0, accepted=[])}
    assert by["MEAT RAILS"].status == "UNMAPPED"


def test_negative_control_five_percent_price_error_is_flagged_then_passes():
    """Inject a 5 % price error into the MES EPS line: the FRONT section must
    FLAG and the triage must name PRICE_DIFF on EPS as the likely cause.
    Remove the injection: PASS. (An audit that cannot fail is worthless.)"""
    broken = _base_mes(front_eps_price=52.5)
    cells = compare_scenario(_golden(BASE_GOLDEN), broken, tolerance_pct=1.0, accepted=[])
    front = next(c for c in cells if c.section_excel == "FRONT")
    assert front.status == "FLAG"
    assert front.variance_pct == pytest.approx(round(10.0 / 680.0 * 100.0, 3), abs=1e-3)
    assert front.likely_cause.startswith("PRICE_DIFF EPS (+10.00)")
    eps = next(t for t in front.triage if t.desc == "EPS")
    assert eps.cls == "PRICE_DIFF" and eps.excel_price == 50.0 and eps.mes_price == 52.5
    assert all(t.cls == "OK" for t in front.triage if t.desc != "EPS")
    fixed = compare_scenario(_golden(BASE_GOLDEN), _base_mes(), tolerance_pct=1.0, accepted=[])
    assert next(c for c in fixed if c.section_excel == "FRONT").status == "PASS"


def test_presence_both_directions_and_extra_section():
    mes = _base_mes()
    mes.sections["FRONT"] = 0.0
    mes.lines = [l for l in mes.lines if l.section != "FRONT"]
    mes.sections["OPTIONAL EXTRAS"] = 500.0
    mes.lines.append(_ml("OPTIONAL EXTRAS", "TOOLBOX", 1.0, 500.0))
    cells = compare_scenario(_golden(BASE_GOLDEN), mes, tolerance_pct=1.0, accepted=[])
    by = {(c.section_excel or c.section_mes): c for c in cells}
    assert by["FRONT"].status == "PRESENCE" and by["FRONT"].reason == "MISSING_IN_MES"
    assert {t.cls for t in by["FRONT"].triage} == {"MISSING_IN_MES"}
    assert by["OPTIONAL EXTRAS"].status == "PRESENCE" and by["OPTIONAL EXTRAS"].reason == "EXTRA_SECTION_IN_MES"
    g = _golden({**BASE_GOLDEN, "SRD": _gsec([_line("DOOR SKIN", 4.0, 80.0)])})   # Excel prices SRD, MES has none
    by = {c.section_excel: c for c in compare_scenario(g, _base_mes(), tolerance_pct=1.0, accepted=[])}
    assert by["SRD"].status == "PRESENCE" and by["SRD"].reason == "MISSING_IN_MES"


def test_triage_classes_qty_both_extra_group_and_zero_formula_hint():
    excel = [_line("SKIN", 4.0, 100.0), _line("EPS", 4.0, 50.0), _line("PU", 3.0, 185.2),
             _line("TAPPING BLOCKS", 2.0, 234.0)]
    mes = [_ml("F", "SKIN", 4.4, 100.0), _ml("F", "EPS", 4.4, 52.5), _ml("F", "PU", 0.0, 185.2, formula="2.44*1.22*0*2"),
           _ml("F", "TAPPING BLOCKS_200MM", 6.0, 68.0), _ml("F", "TAPPING BLOCKS_250MM", 6.0, 68.0),
           _ml("F", "GALV PLATE", 1.0, 240.0), _ml("F", "HIDDEN", 1.0, 999.0, excluded=True)]
    tri, cause = triage_lines(excel, mes)
    cls = {t.desc: t.cls for t in tri}
    assert cls["SKIN"] == "QTY_DIFF" and cls["EPS"] == "BOTH" and cls["PU"] == "QTY_DIFF"
    assert next(t for t in tri if t.desc == "PU").hint == "ZERO_FORMULA"
    assert cls["TAPPING BLOCKS ~ 2 MES line(s)"] == "GROUP_DIFF"
    assert cls["GALV PLATE"] == "EXTRA_IN_MES"
    assert "HIDDEN" not in cls                                     # excluded MES lines never triage
    assert cause.startswith("QTY_DIFF PU (-555.60) [ZERO_FORMULA]")


def test_triage_scales_excel_lines_by_section_multiplier():
    tri, cause = triage_lines([_line("SKIN", 10.0, 100.0)], [_ml("SIDES", "SKIN", 20.0, 100.0)], multiplier=2.0)
    assert tri[0].cls == "OK" and tri[0].excel_qty == 20.0 and tri[0].excel_total == 2000.0


def test_accepted_and_expired():
    broken = _base_mes(front_eps_price=52.5)
    ok = [Accepted(body=SHEET, section="front", variant="*", reason="known", owner="BA",
                   review_by=date(2099, 1, 1), index=0)]
    cells = compare_scenario(_golden(BASE_GOLDEN), broken, tolerance_pct=1.0, accepted=ok)
    front = next(c for c in cells if c.section_excel == "FRONT")
    assert front.status == "ACCEPTED" and front.accepted["reason"] == "known" and not front.failing
    old = [Accepted(body="999", section="FRONT", variant="as_sheet", reason="known", owner="BA",
                    review_by=date(2020, 1, 1), index=0)]
    cells = compare_scenario(_golden(BASE_GOLDEN), broken, tolerance_pct=1.0, accepted=old, today=date(2026, 9, 25))
    front = next(c for c in cells if c.section_excel == "FRONT")
    assert front.status == "EXPIRED" and front.failing
    wrong_variant = [Accepted(body="*", section="*", variant="all_pu", reason="x", owner="BA", review_by=None, index=0)]
    cells = compare_scenario(_golden(BASE_GOLDEN), broken, tolerance_pct=1.0, accepted=wrong_variant)
    assert next(c for c in cells if c.section_excel == "FRONT").status == "FLAG"


def test_known_defect_kind_passes_but_is_listed_as_a_defect(tmp_path):
    broken = _base_mes(front_eps_price=52.5)
    acc = [Accepted(body="*", section="FRONT", variant="*", reason="EPS price stale", owner="BA",
                    review_by=date(2099, 1, 1), index=0, kind="known_defect")]
    goldens = {"t~as_sheet": _golden(BASE_GOLDEN)}
    rep = build_report(pack_name="unit", tolerance_pct=1.0, manifest={}, mes_source="fake", goldens=goldens,
                       results={"t~as_sheet": broken}, scenario_ids=["t~as_sheet"], accepted=acc, warnings=[])
    assert rep.exit_code == 0
    front = next(c for c in rep.cells if c.section_excel == "FRONT")
    assert front.status == "ACCEPTED" and front.accepted["kind"] == "known_defect"
    md = write_all(rep, tmp_path, stem="unit")["md"].read_text(encoding="utf-8")
    assert "Known defects" in md and "EPS price stale" in md and "Tolerated differences" not in md


def test_accepted_lists_keep_comma_bearing_sheet_names(tmp_path):
    p = tmp_path / "acc.yaml"
    p.write_text('- body: [" UP TO 2,3 MTR FREEZER ", "icecream up to 3,2"]\n'
                 '  section: [FLOOR, "REAR FRAME + FLOOR PLATE"]\n'
                 '  variant: [as_sheet, srd]\n'
                 '  reason: r\n', encoding="utf-8")
    a = load_accepted(p)[0]
    assert a.matches(sheet="icecream up to 3,2", trailer_id=16, section_names=["REAR FRAME & FLOOR PLATE"], variant="srd")
    assert a.matches(sheet=" UP TO 2,3 MTR FREEZER ", trailer_id=19, section_names=["FLOOR"], variant="as_sheet")
    assert not a.matches(sheet="icecream up to 4.8", trailer_id=17, section_names=["FLOOR"], variant="as_sheet")
    assert not a.matches(sheet="icecream up to 3,2", trailer_id=16, section_names=["FLOOR"], variant="all_pu")
    assert a.to_dict()["body"] == [" UP TO 2,3 MTR FREEZER ", "icecream up to 3,2"]


def test_load_accepted_validates(tmp_path):
    p = tmp_path / "acc.yaml"
    p.write_text('- body: "*"\n  section: SIDES\n  reason: r\n  owner: BA\n  review_by: 2026-12-31\n', encoding="utf-8")
    acc = load_accepted(p)
    assert acc[0].review_by == date(2026, 12, 31) and acc[0].variant == "*" and acc[0].kind == "tolerated"
    p.write_text('- body: "*"\n  section: SIDES\n  reason: r\n  kind: maybe\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_accepted(p)
    p.write_text('- body: "*"\n  section: SIDES\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_accepted(p)
    assert load_accepted(tmp_path / "missing.yaml") == []


def test_build_report_no_golden_and_writers(tmp_path):
    goldens = {"t~as_sheet": _golden(BASE_GOLDEN)}
    results = {"t~as_sheet": _base_mes(front_eps_price=52.5), "t~all_pu": _base_mes()}
    rep = build_report(pack_name="unit", tolerance_pct=1.0, manifest={"generated_at": "x", "workbook": {"files": {}}},
                       mes_source="fake", goldens=goldens, results=results, scenario_ids=["t~as_sheet", "t~all_pu"],
                       accepted=[], warnings=["w1"])
    assert rep.exit_code == 1
    assert rep.counts["NO_GOLDEN"] == 1 and rep.counts["FLAG"] == 1
    paths = write_all(rep, tmp_path, stem="unit")
    html = paths["html"].read_text(encoding="utf-8")
    assert "cdn" not in html.lower() and "window.__AUDIT__" in html and "PRICE_DIFF EPS" in html
    md = paths["md"].read_text(encoding="utf-8")
    assert "FAIL" in md and "| FRONT |" in md and "NO_GOLDEN" in md and "w1" in md
    csv_text = paths["csv"].read_text(encoding="utf-8")
    assert csv_text.splitlines()[0].startswith("scenario_id,sheet,")
    assert len(csv_text.splitlines()) == 1 + len(rep.cells)
