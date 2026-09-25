"""Packs load and expand; workbooks are git-ignored; the mapping tables hold."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.costing_audit import PACKS_DIR, TESTS_DIR, BACKEND_DIR                       # noqa: E402
from tools.costing_audit.mapping import SHEET_TO_TRAILER, norm_key, SectionMapper, sheet_slug  # noqa: E402
from tools.costing_audit.scenarios import load_pack, expand_pack, NAMED_VARIANTS          # noqa: E402
from tools.costing_audit.sheet_map import discover_sheet                                   # noqa: E402
from tests.costing_audit.synthetic import build_workbook, SHEET                            # noqa: E402


def test_every_committed_pack_loads():
    packs = sorted(PACKS_DIR.glob("*.yaml"))
    assert packs, "no packs committed"
    for p in packs:
        pack = load_pack(p)
        assert pack.bodies and all(b["sheet"] in SHEET_TO_TRAILER for b in pack.bodies)
        for b in pack.bodies:
            assert set(b.get("variants") or []) <= set(NAMED_VARIANTS) | set(b.get("custom_variants") or {})


def test_smoke_pack_is_small_enough_for_ci():
    pack = load_pack(PACKS_DIR / "smoke.yaml")
    n = sum(len(b.get("lengths") or [1]) * len(b.get("widths") or [1]) * len(b.get("heights") or [1])
            * len(b.get("variants") or [1]) for b in pack.bodies)
    assert n <= 24


def test_expand_pack_builds_the_six_named_variants(tmp_path):
    SHEET_TO_TRAILER.setdefault(SHEET, 999)
    f, v, _ = build_workbook(front="eps", drd="eps")
    sm = discover_sheet(f, v)
    p = tmp_path / "p.yaml"
    p.write_text(f'name: unit\nbodies:\n  - sheet: "{SHEET}"\n    lengths: [4.0, 5.0]\n'
                 '    variants: [as_sheet, all_eps, all_pu, srd, drd, foam_4g]\n'
                 '    custom_variants:\n      thin:\n        door: drd\n        panels: {FRONT: "pu:0.03"}\n',
                 encoding="utf-8")
    pack = load_pack(p)
    scs = expand_pack(pack, {SHEET: sm})
    assert len(scs) == 2 * 6
    by = {(s.length, s.variant): s for s in scs}
    assert by[(4.0, "as_sheet")].panels["FRONT"].insulation == "eps"
    assert by[(4.0, "all_pu")].panels["FRONT"].insulation == "pu" and by[(4.0, "all_pu")].panels["FRONT"].thickness == 0.06
    assert by[(4.0, "all_pu")].panels["DRD"].insulation == "pu"
    assert by[(4.0, "srd")].door == "srd" and by[(4.0, "srd")].panels["DRD"].insulation == "none"
    assert by[(4.0, "foam_4g")].foam == "4G" and by[(4.0, "as_sheet")].foam == "32D"
    assert by[(5.0, "drd")].width == 2.0 and by[(5.0, "drd")].height == 2.0     # sheet values by default
    ids = [s.id for s in scs]
    assert len(set(ids)) == len(ids)


def test_pack_validation_errors(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text('name: bad\nbodies:\n  - sheet: "NOT A SHEET"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_pack(p)
    p.write_text('name: bad\ngate_mode: nope\nbodies:\n  - sheet: "icecream up to 4.8"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_pack(p)


def test_section_name_matching():
    m = SectionMapper(["REAR FRAME & FLOOR PLATE", "SRD DOOR FITTINGS", "SUB FRAME + LIGHT BOX ASSY"],
                      overrides={"AUT/TRUCK_LIGHT/CL": "SUB FRAME + LIGHT BOX ASSY"})
    assert m.to_mes("REAR FRAME + FLOOR PLATE") == "REAR FRAME & FLOOR PLATE"
    assert m.to_mes("DOOR FITTINGS SRD") == "SRD DOOR FITTINGS"
    assert m.to_mes("AUT/TRUCK_LIGHT/CL") == "SUB FRAME + LIGHT BOX ASSY"
    assert m.to_mes("MEAT RAILS") is None
    assert norm_key(" Sub  frame + light box assy ") == norm_key("SUB FRAME + LIGHT BOX ASSY")
    assert sheet_slug(" 4.9 & UP CHILLER AND 2.5 WIDE ") == "4_9_up_chiller_and_2_5_wide"


def test_workbooks_are_gitignored_and_none_committed():
    """Rule 6: Burt's workbooks never enter git."""
    gi = (TESTS_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "*.xlsx" in gi and "*.xls" in gi
    repo = BACKEND_DIR.parent
    for pattern in ("tests/costing_audit/a.xlsx", "tests/costing_audit/golden/x/b.xls"):
        r = subprocess.run(["git", "check-ignore", "-q", f"backend/{pattern}"], cwd=repo)
        assert r.returncode == 0, f"{pattern} is not ignored"
    tracked = subprocess.run(["git", "ls-files", "backend/tests/costing_audit"], cwd=repo,
                             capture_output=True, text=True).stdout.splitlines()
    assert not [t for t in tracked if t.lower().endswith((".xlsx", ".xls", ".xlsm"))]
