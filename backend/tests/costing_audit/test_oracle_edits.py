"""The oracle's scenario edits on a synthetic sheet: input write, flag block,
gate handling, foam substitution, revert — plus the read-back of a recalculated
copy (simulated by the values twin). No LibreOffice needed."""
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.costing_audit import excel_oracle as eo                        # noqa: E402
from tools.costing_audit.mapping import SHEET_TO_TRAILER                  # noqa: E402
from tools.costing_audit.scenarios import Scenario, PanelSpec, sheet_state  # noqa: E402
from tools.costing_audit.sheet_map import discover_sheet                  # noqa: E402
from tests.costing_audit.synthetic import build_workbook, SHEET           # noqa: E402


class FakeOracle(eo.ExcelOracle):
    """ExcelOracle without the workbook files: the in-memory synthetic sheets stand in."""
    def __init__(self, ws_formulas, ws_values):
        self.wb = ws_formulas.parent
        self.wbv = ws_values.parent
        self.stale = {}
        self.overrides = {}
        self.maps = {}
        self.log = lambda *a, **k: None
        self.soffice = None
        self.slim = False
        SHEET_TO_TRAILER.setdefault(SHEET, 999)


def _scenario(**kw) -> Scenario:
    base = dict(id="t", pack="t", sheet=SHEET, trailer_id=999, variant="custom", length=6.0, width=2.5,
                height=2.2, door="drd", foam="32D",
                panels={"FRONT": PanelSpec("pu", 0.04), "DRD": PanelSpec("eps", 0.05)},
                flags={"RICE GRAIN FLOOR": "Y"}, gate_mode="as_sheet")
    base.update(kw)
    return Scenario(**base)


def test_apply_writes_inputs_flags_and_reverts_cleanly():
    f, v, _ = build_workbook()
    o = FakeOracle(f, v)
    sm = o.discover(SHEET)
    before = {c: f[c].value for c in ("C4", "C5", "C6", "C8", "D8", "C9", "D9", "C10", "D10", "C11", "D11", "D12")}
    undo, findings = o._apply(_scenario(), sm)
    assert (f["C4"].value, f["C5"].value, f["C6"].value) == (6.0, 2.5, 2.2)
    assert (f["C8"].value, f["D8"].value) == (0.0, "N")        # FRONT EPS off
    assert (f["C9"].value, f["D9"].value) == (0.04, "Y")       # FRONT PU on at 0.04
    assert (f["C10"].value, f["D10"].value) == (0.05, "Y")     # DRD EPS on
    assert (f["C11"].value, f["D11"].value) == (0.0, "N")
    assert f["D12"].value == "Y"                               # other flag from the scenario
    assert findings == []
    o._revert(SHEET, undo)
    assert {c: f[c].value for c in before} == before


def test_gate_mode_force_writes_door_gates_and_eps_flag_mode_sets_carrier():
    f, v, _ = build_workbook()
    o = FakeOracle(f, v)
    sm = o.discover(SHEET)
    undo, _ = o._apply(_scenario(gate_mode="force", door="drd"), sm)
    assert (f["I25"].value, f["I26"].value, f["I32"].value, f["I33"].value) == (1, 1, 1, 1)
    o._revert(SHEET, undo)
    assert f["I25"].value.startswith("=IF(")
    undo, _ = o._apply(_scenario(gate_mode="force", door="srd"), sm)
    assert (f["I25"].value, f["I26"].value) == (0, 0)
    o._revert(SHEET, undo)
    undo, _ = o._apply(_scenario(gate_mode="eps_flag", panels={"FRONT": PanelSpec("pu", 0.04)}), sm)
    assert (f["C8"].value, f["D8"].value, f["D9"].value) == (0.0, "Y", "Y")   # EPS Y carries the gate, thickness 0
    o._revert(SHEET, undo)


def test_foam_substitution_and_mix_findings():
    f, v, _ = build_workbook()
    o = FakeOracle(f, v)
    sm = o.discover(SHEET)
    undo, findings = o._apply(_scenario(foam="4G"), sm)
    assert f["G18"].value == "=C9*[1]PU!$C$19/2.98"
    assert findings == []
    o._revert(SHEET, undo)
    assert f["G18"].value == "=C9*[1]PU!$C$17/2.98"
    # a sheet saved on the 4G reference is normalised to 32D, and says so
    f["G18"] = "=C9*[1]PU!$C$19/2.98"
    undo, findings = o._apply(_scenario(foam="32D"), sm)
    assert f["G18"].value == "=C9*[1]PU!$C$17/2.98"
    assert any("normalised" in x for x in findings)
    o._revert(SHEET, undo)
    # a hard-coded PU rate has no 4G spelling
    f["G18"] = "=C9*3090/2.98"
    undo, findings = o._apply(_scenario(foam="4G"), sm)
    assert any(x.startswith("NO_4G_REFERENCE") for x in findings)
    o._revert(SHEET, undo)


def test_read_back_sums_gated_cells_and_flags_unverifiable(tmp_path):
    f, v, exp = build_workbook(front="pu", drd="pu")
    o = FakeOracle(f, v)
    sm = o.discover(SHEET)
    out = tmp_path / "recalc.xlsx"
    v.parent.save(out)                       # the values twin plays the recalculated copy
    sc = _scenario(panels={"FRONT": PanelSpec("pu", 0.05), "DRD": PanelSpec("pu", 0.05)})
    g = o._read(out, sc, sm, findings=[])
    assert g.grand_total == pytest.approx(exp["GRAND"])
    assert g.sections["FRONT"].total == pytest.approx(exp["FRONT"])
    assert g.sections["DRD"].total == pytest.approx(exp["DRD"])          # via the PU-gated row
    assert g.sections["DRD"].gates == {"I25": 0, "I26": 1}
    assert g.sections["SIDES"].multiplier == pytest.approx(2.0)
    assert [l.desc for l in g.sections["FRONT"].lines] == ["SKIN", "EPS", "PU"]
    assert g.sections["FRONT"].lines[2].total == pytest.approx(exp["FRONT"] - 100.0 * 4.0)
    # NO_4G_REFERENCE turns PU-bearing sections unverifiable
    g4 = o._read(out, Scenario(**{**sc.__dict__, "foam": "4G"}), sm,
                 findings=["NO_4G_REFERENCE: hard-coded"])
    assert g4.sections["FRONT"].status == "UNVERIFIABLE" and g4.sections["FRONT"].reason == "NO_4G_REFERENCE"
    assert g4.sections["SIDES"].status == "OK"


def test_sheet_state_reads_burts_saved_block():
    f, v, _ = build_workbook(front="pu", drd="eps", other_flag="Y")
    sm = discover_sheet(f, v)
    panels, door, others = sheet_state(sm)
    assert panels["FRONT"].insulation == "pu" and panels["FRONT"].thickness == 0.05
    assert panels["DRD"].insulation == "eps"
    assert door == "drd"
    assert others == {"RICE GRAIN FLOOR": "Y"}


def test_workbook_fingerprint_changes_with_content(tmp_path):
    for name in eo.WORKBOOK_FILES:
        (tmp_path / name).write_bytes(b"a")
    a = eo.workbook_fingerprint(tmp_path)
    (tmp_path / eo.GRP_FILE).write_bytes(b"b")
    b = eo.workbook_fingerprint(tmp_path)
    assert a[eo.GRP_FILE] != b[eo.GRP_FILE] and a[eo.PRICE_FILE] == b[eo.PRICE_FILE]
