"""RT5 — the audit packs price only bodies Burt says can exist (RT5_DISPATCH §3.0.2; RT5_RULING_1 Q3 / Q4).

Burt, 5 Oct: (1) no PU insulation on a chiller, any panel; (2) a freezer takes EPS on the ROOF and FLOOR only —
never on the FRONT, SIDES or the doors. The freezer pack's `all_eps` priced a body (2) rules out; RT5 replaces it
with `roof_floor_eps` (EPS roof + floor, PU everywhere else) in the freezers pack AND the smoke pack's freezer.

These tests pin, from the committed packs and golden (no database, no Excel):
  1. every committed golden scenario of every pack follows both rules (the chillers since RT2, the freezers now);
  2. roof_floor_eps is EPS on ROOF + FLOOR at the sheet's EPS thickness and PU on every other panel at its PU
     thickness, the unquoted door none — the expansion, on a synthetic sheet;
  3. the freezer and smoke packs name roof_floor_eps and not all_eps for every freezer sheet;
  4. the totals do not move (RT5_RULING_1 Q4): freezers 54 scenarios, smoke 18; each has 9 / 3 roof_floor_eps.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tools.costing_audit.scenarios import NAMED_VARIANTS, PanelSpec, Scenario, load_pack

HERE = Path(__file__).resolve().parent
PACKS = HERE / "packs"
GOLDEN = HERE / "golden"
FREEZER_EPS_FORBIDDEN = ("FRONT", "SIDES", "DRD", "SRD")


def _kind(sheet: str) -> str | None:
    s = sheet.upper()
    return "CHILLER" if "CHILLER" in s else "FREEZER" if "FREEZER" in s else None


def _golden_scenarios():
    for manifest in sorted(GOLDEN.glob("*/_manifest.json")):
        pack = manifest.parent.name
        for f in sorted(manifest.parent.glob("[!_]*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            for s in doc["scenarios"]:
                yield pack, doc["sheet"], s["scenario"]


def test_every_golden_scenario_follows_burts_two_rules():
    broken, seen = [], {"CHILLER": 0, "FREEZER": 0}
    for pack, sheet, sc in _golden_scenarios():
        kind = _kind(sheet)
        if kind is None:
            continue
        seen[kind] += 1
        for panel, spec in sc["panels"].items():
            ins = spec["insulation"] if isinstance(spec, dict) else spec
            if kind == "CHILLER" and ins == "pu":
                broken.append(f"{pack}: {sc['id']} {panel} PU on a chiller")
            if kind == "FREEZER" and ins == "eps" and panel in FREEZER_EPS_FORBIDDEN:
                broken.append(f"{pack}: {sc['id']} {panel} EPS on a freezer")
    assert seen["CHILLER"] and seen["FREEZER"], seen
    assert not broken, "a pack prices a body Burt says cannot exist:\n" + "\n".join(broken)


class _Flag:
    def __init__(self, thickness):
        self.thickness = thickness


class _SheetMap:
    """Just what expand_pack reads for a body's panels: the flag block (insulation per panel) + thicknesses."""
    def __init__(self):
        self.sheet = "SYNTH FREEZER"
        self.input_values = {"LENGTH": 4.0, "WIDTH": 2.5, "HEIGHT": 2.4}
        self.thick = {("FRONT", "PU"): 0.06, ("SIDES", "PU"): 0.06, ("DRD", "PU"): 0.06, ("SRD", "PU"): 0.0,
                      ("ROOF", "PU"): 0.1, ("FLOOR", "PU"): 0.1, ("ROOF", "EPS"): 0.076, ("FLOOR", "EPS"): 0.08}

    def flag_by_label(self, label):
        panel, _, kind = label.rpartition(" ")
        t = self.thick.get((panel, kind))
        return _Flag(t) if t is not None else None


def test_roof_floor_eps_is_eps_on_roof_and_floor_and_pu_everywhere_else(monkeypatch):
    import tools.costing_audit.scenarios as sc_mod
    assert "roof_floor_eps" in NAMED_VARIANTS
    base = {p: PanelSpec("pu", 0.06) for p in ("FRONT", "DRD", "SIDES", "ROOF", "FLOOR")}
    base["SRD"] = PanelSpec("none", 0.0)
    monkeypatch.setattr(sc_mod, "sheet_state", lambda sm: (dict(base), "drd", {}))
    monkeypatch.setitem(sc_mod.SHEET_TO_TRAILER, "SYNTH FREEZER", 999)
    pack = sc_mod.Pack(name="synth", path=Path("synth.yaml"), tolerance_pct=1.0, gate_mode="as_sheet", raw={},
                       thickness_defaults=sc_mod.DEFAULT_THICKNESS,
                       bodies=[{"sheet": "SYNTH FREEZER", "lengths": [4.0], "variants": ["roof_floor_eps"]}])
    (s,) = sc_mod.expand_pack(pack, {"SYNTH FREEZER": _SheetMap()})
    got = {p: (v.insulation, v.thickness) for p, v in s.panels.items()}
    assert got == {"FRONT": ("pu", 0.06), "DRD": ("pu", 0.06), "SRD": ("none", 0.0), "SIDES": ("pu", 0.06),
                   "ROOF": ("eps", 0.076), "FLOOR": ("eps", 0.08)}
    assert s.door == "drd" and s.variant == "roof_floor_eps" and s.foam_explicit is False


@pytest.mark.parametrize("pack", ["freezers", "smoke"])
def test_the_freezer_sheets_use_roof_floor_eps_not_all_eps(pack):
    doc = yaml.safe_load((PACKS / f"{pack}.yaml").read_text(encoding="utf-8"))
    freezers = [b for b in doc["bodies"] if _kind(b["sheet"]) == "FREEZER"]
    assert freezers
    for b in freezers:
        assert "roof_floor_eps" in b["variants"] and "all_eps" not in b["variants"], (pack, b["sheet"], b["variants"])


@pytest.mark.parametrize("pack,total,rfe", [("freezers", 54, 9), ("smoke", 18, 3)])
def test_the_totals_do_not_move(pack, total, rfe):
    m = json.loads((GOLDEN / pack / "_manifest.json").read_text(encoding="utf-8"))
    assert m["scenario_count"] == total
    ids = [s["id"] for p, _, s in _golden_scenarios() if p == pack]
    assert len(ids) == total
    assert sum(i.endswith("~roof_floor_eps") for i in ids) == rfe
    assert not any(i.endswith("~all_eps") and "FREEZER" in i.upper() for i in ids)
    load_pack(PACKS / f"{pack}.yaml")                          # the pack itself still parses
