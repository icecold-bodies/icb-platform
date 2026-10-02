"""RT2 Part 1c, R6.4 — the audit honours the BODY's default foam grade.

A real new quote opens on its body's default_insulation_foam (Body Templates, migration
0050). So the audit's MES probe sends that grade for every scenario whose variant does
not name one, and the golden prices Burt's sheet at the pack's `foam_default`. foam_4g /
foam_32d (and a custom variant with `foam:`) keep their own grade on both sides. When the
two defaults disagree the probe says so in a note — the PU cells then show a genuine
quoting difference instead of being silently compared at two grades.

The probe test is DB-backed (the isolated _test database), marker RT2F, purged at setup
and teardown. The pack test is pure.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.costing_audit.mapping import SHEET_TO_TRAILER                                  # noqa: E402
from tools.costing_audit.scenarios import PanelSpec, Scenario, expand_pack, load_pack     # noqa: E402
from tools.costing_audit.sheet_map import discover_sheet                                  # noqa: E402
from tests.costing_audit.synthetic import build_workbook, SHEET                           # noqa: E402

MARK = "RT2F"


# ── the pack side (pure) ──────────────────────────────────────────────────────

def _pack(tmp_path, extra: str):
    p = tmp_path / "p.yaml"
    p.write_text(f'name: unit\nbodies:\n  - sheet: "{SHEET}"\n    lengths: [4.0]\n{extra}', encoding="utf-8")
    return load_pack(p)


def test_variants_without_a_grade_take_the_packs_foam_default(tmp_path):
    SHEET_TO_TRAILER.setdefault(SHEET, 999)
    f, v, _ = build_workbook(front="pu", drd="pu")
    sm = discover_sheet(f, v)
    pack = _pack(tmp_path, '    foam_default: 4G\n'
                           '    variants: [as_sheet, all_eps, srd, foam_4g, foam_32d, thin, thin32]\n'
                           '    custom_variants:\n'
                           '      thin: {door: drd, panels: {FRONT: "pu:0.03"}}\n'
                           '      thin32: {door: drd, foam: 32D, panels: {FRONT: "pu:0.03"}}\n')
    by = {s.variant: s for s in expand_pack(pack, {SHEET: sm})}
    for var in ("as_sheet", "all_eps", "srd", "thin"):          # no grade named → the body's
        assert (by[var].foam, by[var].sets_foam) == ("4G", False), var
    assert (by["foam_4g"].foam, by["foam_4g"].sets_foam) == ("4G", True)
    assert (by["foam_32d"].foam, by["foam_32d"].sets_foam) == ("32D", True)
    assert (by["thin32"].foam, by["thin32"].sets_foam) == ("32D", True)


def test_without_foam_default_every_body_stays_32d(tmp_path):
    SHEET_TO_TRAILER.setdefault(SHEET, 999)
    f, v, _ = build_workbook(front="eps", drd="eps")
    sm = discover_sheet(f, v)
    by = {s.variant: s for s in expand_pack(_pack(tmp_path, '    variants: [as_sheet, foam_4g]\n'), {SHEET: sm})}
    assert (by["as_sheet"].foam, by["as_sheet"].sets_foam) == ("32D", False)
    assert (by["foam_4g"].foam, by["foam_4g"].sets_foam) == ("4G", True)


def test_a_bad_grade_in_a_pack_is_refused(tmp_path):
    SHEET_TO_TRAILER.setdefault(SHEET, 999)
    with pytest.raises(ValueError, match="foam_default"):
        _pack(tmp_path, '    foam_default: 50D\n    variants: [as_sheet]\n')
    with pytest.raises(ValueError, match="custom variant"):
        _pack(tmp_path, '    variants: [x]\n    custom_variants:\n      x: {foam: 80D}\n')


def test_a_golden_written_before_rt2_derives_the_grade_from_its_variant():
    """Goldens committed before RT2 carry no foam_explicit key: foam_4g still names its
    grade, every other variant opens on the body's default."""
    from tools.costing_audit.runner import scenario_from_golden
    base = dict(id="x", pack="p", sheet=SHEET, trailer_id=1, length=4.0, width=2.0, height=2.0,
                door="drd", foam="4G", panels={}, flags={}, gate_mode="as_sheet", section_map={})
    assert scenario_from_golden({**base, "variant": "foam_4g"}).sets_foam is True
    assert scenario_from_golden({**base, "variant": "as_sheet", "foam": "32D"}).sets_foam is False


# ── the probe side (DB-backed) ────────────────────────────────────────────────

def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture()
def body():
    from app.database import BillOfMaterial, Material, SessionLocal, TrailerType
    with SessionLocal() as db:
        _purge(db)
        tt = TrailerType(name=f"{MARK} BODY", is_active=True, default_insulation_foam="4G")
        db.add(tt)
        db.flush()
        mats = {}
        for n in ("FRONT EPS", "FRONT PU"):
            m = Material(name=f"{MARK} {n}", unit_of_measure="each", price_per_unit=0.0)
            db.add(m)
            db.flush()
            mats[n] = m
            db.add(BillOfMaterial(trailer_type_id=tt.id, material_id=m.id, is_body_option=True,
                                  body_option_group="FRONT", body_option_subgroup="INSULATION",
                                  variable_value=0.06 if n.endswith("EPS") else 0.0))
        db.commit()
        tid = tt.id
    yield tid
    with SessionLocal() as db:
        _purge(db)


def _sc(tid: int, variant: str, foam: str, explicit=None) -> Scenario:
    return Scenario(id=f"{MARK}~{variant}", pack="unit", sheet=SHEET, trailer_id=tid, variant=variant,
                    length=4.0, width=2.0, height=2.0, door="drd", foam=foam,
                    panels={"FRONT": PanelSpec("pu", 0.06)}, flags={}, foam_explicit=explicit)


def _set_default(tid: int, grade: str) -> None:
    from app.database import SessionLocal, TrailerType
    with SessionLocal() as db:
        db.get(TrailerType, tid).default_insulation_foam = grade
        db.commit()


def test_the_probe_opens_a_gradeless_variant_on_the_bodys_default(body):
    from tools.costing_audit.mes_probe import MesProbe
    probe = MesProbe(log=lambda *_: None)
    try:
        payload, _, notes = probe.build_payload(_sc(body, "as_sheet", "4G", explicit=False))
        assert payload["insulation_foam"] == "4G"            # the body opens on 4G …
        assert not [n for n in notes if n.startswith("foam:")]   # … and the golden agrees: no note
        payload, _, _ = probe.build_payload(_sc(body, "foam_32d", "32D", explicit=True))
        assert payload["insulation_foam"] == "32D"           # a named grade wins over the default
    finally:
        probe.close()


def test_the_probe_says_so_when_the_two_defaults_disagree(body):
    from tools.costing_audit.mes_probe import MesProbe
    _set_default(body, "32D")       # e.g. prod before the window sets the four 4G bodies
    probe = MesProbe(log=lambda *_: None)
    try:
        payload, _, notes = probe.build_payload(_sc(body, "as_sheet", "4G", explicit=False))
        assert payload["insulation_foam"] == "32D"           # what a new quote really opens on
        assert any("opens on 32D" in n and "Burt's sheet at 4G" in n for n in notes), notes
        payload, _, _ = probe.build_payload(_sc(body, "foam_4g", "4G"))   # pre-RT2 golden: derived
        assert payload["insulation_foam"] == "4G"
    finally:
        probe.close()
