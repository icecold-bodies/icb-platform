"""v1.57.1: cause-guarded acceptance and offline re-evaluation of a saved run."""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.costing_audit.accepted import Accepted, load_accepted          # noqa: E402
from tools.costing_audit.compare import build_report, reapply_accepted     # noqa: E402
from tools.costing_audit.report import write_all                           # noqa: E402
from tests.costing_audit.test_compare import _golden, _base_mes, _ml, BASE_GOLDEN, SHEET   # noqa: E402


def _report_with_two_mechanisms():
    """FRONT flags on a 5 % EPS price error; SIDES flags on an extra R5k line."""
    mes = _base_mes(front_eps_price=52.5)
    mes.lines.append(_ml("SIDES", "PU", 5.9536, 4100.0))
    mes.sections["SIDES"] += 5.9536 * 4100.0
    return build_report(pack_name="unit", tolerance_pct=1.0, manifest={}, mes_source="fake",
                        goldens={"t~as_sheet": _golden(BASE_GOLDEN)}, results={"t~as_sheet": mes},
                        scenario_ids=["t~as_sheet"], accepted=[], warnings=[])


def test_cause_guard_only_greys_the_named_mechanism():
    rep = _report_with_two_mechanisms()
    by = {c.section_excel: c for c in rep.cells}
    assert by["FRONT"].status == "FLAG" and by["SIDES"].status == "FLAG"
    assert by["SIDES"].likely_cause.startswith("EXTRA_IN_MES PU")
    narrow = [Accepted(body="*", section=["FRONT", "SIDES"], variant="*", reason="eps price", owner="BA",
                       review_by=date(2099, 1, 1), index=0, kind="known_defect", cause="PRICE_DIFF EPS")]
    rep2 = reapply_accepted(rep.to_dict(), narrow)
    by2 = {c.section_excel: c for c in rep2.cells}
    assert by2["FRONT"].status == "ACCEPTED" and by2["FRONT"].base_status == "FLAG"
    assert by2["SIDES"].status == "FLAG"                 # same sections, different mechanism: stays red
    assert rep2.exit_code == 1
    wide = [Accepted(body="*", section="*", variant="*", reason="x", owner="BA", review_by=None, index=0)]
    assert reapply_accepted(rep.to_dict(), wide).exit_code == 0


def test_reapply_round_trips_a_previously_accepted_report():
    rep = _report_with_two_mechanisms()
    acc = [Accepted(body="*", section="*", variant="*", reason="all", owner="BA", review_by=date(2099, 1, 1), index=0)]
    once = reapply_accepted(rep.to_dict(), acc)
    assert all(c.status in ("ACCEPTED", "PASS", "SKIP", "UNVERIFIABLE") for c in once.cells)
    again = reapply_accepted(once.to_dict(), [])            # strip the acceptance: the flags come back
    by = {c.section_excel: c for c in again.cells}
    assert by["FRONT"].status == "FLAG" and by["SIDES"].status == "FLAG"
    legacy = once.to_dict()
    for c in legacy["cells"]:
        c.pop("base_status", None)                          # a report written before v1.57.1
    by = {c.section_excel: c for c in reapply_accepted(legacy, []).cells}
    assert by["FRONT"].status == "FLAG"


def test_reaccept_cli_rewrites_reports(tmp_path):
    from tools.costing_audit.cli import main
    rep = _report_with_two_mechanisms()
    src = tmp_path / "saved.json"
    src.write_text(json.dumps(rep.to_dict(), default=str), encoding="utf-8")
    acc = tmp_path / "acc.yaml"
    acc.write_text('- body: "*"\n  section: "*"\n  variant: "*"\n  cause: [PRICE_DIFF EPS, EXTRA_IN_MES PU]\n'
                   '  kind: known_defect\n  reason: both\n  review_by: 2099-01-01\n', encoding="utf-8")
    rc = main(["reaccept", "--report", str(src), "--accepted", str(acc), "--out", str(tmp_path / "out"), "--stem", "re"])
    assert rc == 0
    md = (tmp_path / "out" / "re.md").read_text(encoding="utf-8")
    assert "Known defects" in md and "acc.yaml" in md
    assert load_accepted(acc)[0].cause == ["PRICE_DIFF EPS", "EXTRA_IN_MES PU"]


def test_env_accepted_list_must_exist(tmp_path, monkeypatch):
    from tools.costing_audit import cli
    import pytest
    with pytest.raises(SystemExit):
        cli._accepted_path(None, "nowhere")
    assert cli._accepted_path(str(tmp_path / "x.yaml"), "nowhere") == tmp_path / "x.yaml"
