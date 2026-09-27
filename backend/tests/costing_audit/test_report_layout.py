"""v1.57.2 report layout: parameter grid on top (rows = L x W x H per body, columns =
variants), frozen bottom half (sections left, lines right), draggable divider — and
the embedded report data can never close its own <script>."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.costing_audit.compare import build_report                     # noqa: E402
from tools.costing_audit.report import write_html                         # noqa: E402
from tests.costing_audit.test_compare import _golden, _base_mes, BASE_GOLDEN   # noqa: E402


def _report(desc="EPS"):
    mes = _base_mes(front_eps_price=52.5)
    for ln in mes.lines:
        if ln.desc == "EPS":
            ln.desc = desc
    goldens, results, ids = {}, {}, []
    for variant in ("as_sheet", "all_pu"):
        for L in (4.2, 5.5):
            g = _golden(BASE_GOLDEN, variant=variant)
            g["scenario"] = {**g["scenario"], "id": f"t~L{L}~{variant}", "length": L}
            goldens[g["scenario"]["id"]] = g
            results[g["scenario"]["id"]] = mes
            ids.append(g["scenario"]["id"])
    return build_report(pack_name="unit", tolerance_pct=1.0, manifest={}, mes_source="fake",
                        goldens=goldens, results=results, scenario_ids=ids, accepted=[], warnings=[])


def test_layout_has_grid_divider_and_two_bottom_panels(tmp_path):
    out = tmp_path / "r.html"
    write_html(_report(), out)
    html = out.read_text(encoding="utf-8")
    for anchor in ('id="top"', 'id="grid"', 'id="divider"', 'id="bottom"', 'id="left"', 'id="right"'):
        assert anchor in html, anchor
    assert "cdn" not in html.lower() and "<link" not in html          # self-contained
    assert "costingAudit.split" in html and "localStorage" in html    # remembered split …
    assert "try {" in html                                            # … never required
    # variants are columns in canonical order, dimensions are rows
    assert "VARIANT_ORDER = ['as_sheet','all_eps','all_pu','srd','drd','foam_4g']" in html


def test_embedded_data_cannot_close_the_script(tmp_path):
    out = tmp_path / "r.html"
    rep = _report(desc="ZZ </script><script>alert(1)</script>")     # an EXTRA_IN_MES line with a hostile name
    rep.warnings.append("</script><script>alert(2)</script>")
    write_html(rep, out)
    html = out.read_text(encoding="utf-8")
    m = re.search(r"<script>window.__AUDIT__ = (.*?);</script>", html, re.S)
    assert m, "data script not found"
    assert "</script" not in m.group(1)
    data = json.loads(m.group(1).replace("<\\/", "</"))
    assert any("</script>" in (t["desc"] or "") for c in data["cells"] for t in c["triage"])
    assert "</script><script>alert(2)</script>" in data["warnings"]
    assert "&lt;/script&gt;" in html.split("<script>window.__AUDIT__")[0]   # the header warning is escaped
