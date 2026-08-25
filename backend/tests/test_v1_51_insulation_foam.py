"""v1.51 — PU insulation foam grade: 32D PU FOAM (default) vs 4G FOAM.

Burt hand-switched his workbook between the two PU grades; the MES replaces that
with ONE explicit selection per costing, under BODY OPTIONS. Stored BOM prices
are the 32D side (migration 0046 normalises the baked-4G categories), and 4G is
DERIVED at calculation time by the price-list ratio 5875/4310.

Everything here is a pure-function test — no DB, no request context — mirroring
test_body_options_display.py. The three things that must hold:

  1. WHICH rows are foam (`is_pu_foam_row`) — "PU INJECTION" is a different
     product and "FRONT PU" is a toggle, so neither may be graded.
  2. THE ARITHMETIC (`_build_bom_items`) — a foam line's unit price is the stored
     price on 32D and exactly ratio x that on 4G, while every other line and any
     hand-typed price override stays byte-identical.
  3. THE CLASSIFIER (migration 0046) — a rate identifies its grade, the 2.99 typo
     is corrected rather than replicated, and anything unrecognised is refused.
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routers.calculator import _build_bom_items, _derive_body_options_display
from app.services import insulation_foam as pu_foam


RATIO = 5875.0 / 4310.0            # 1.3631090487238979
RATE_32D = 4310.0 * (1.22 * 2.44) / 2.98
RATE_4G = 5875.0 * (1.22 * 2.44) / 2.98


# ── migration 0046, loaded by path (alembic versions are not an import package) ──

def _load_migration():
    path = (Path(__file__).resolve().parent.parent
            / "alembic" / "versions" / "0046_pu_foam_4g_normalisation.py")
    spec = importlib.util.spec_from_file_location("mig0046", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()


# ── BOM row stand-ins ────────────────────────────────────────────────────────

def _row(id, name, price, *, override=None, is_body_option=False,
         section="FRONT", formula="1", subgroup=None):
    return SimpleNamespace(
        id=id, is_body_option=is_body_option,
        body_option_group=section if is_body_option else None,
        body_option_subgroup=subgroup,
        body_option_linked=None, body_option_linked_id=None,
        body_option_default=False, variable_value=None,
        bom_section=section, bom_section_id=None, bom_conditions=None,
        formula_expression=formula, waste_percentage=0.0,
        unit_price_override=override,
        skin_formula_id=None, skin_formula=None, skin_formula_region=None,
        taping_block_id=None, taping_block=None,
        floor_plate_id=None, floor_plate=None,
        mounting_cleat_id=None, mounting_cleat=None,
        material_id=id + 1000,
        material=SimpleNamespace(
            name=name, unit_of_measure="m²", price_per_unit=price,
            sap_code="", material_code="",
            category=SimpleNamespace(name=section)),
    )


def _bom():
    """One PU foam cost line per real section, plus the things that must NOT be
    graded: the EPS sibling, the PU-injection product, and the toggle row."""
    return [
        _row(1, "PU", 258.32, section="DRD"),                       # material price
        _row(2, "PU", 430.54, override=430.54, section="ROOF"),     # row override
        _row(3, "EPS", 127.72, section="SIDES"),
        _row(4, "PU INJECTION", 60.0, section="SIDES"),
        _row(5, "30MM PU INJECTION", 60.0, section="FLOOR"),
        _row(6, "FRONT PU", 0.0, is_body_option=True,
             section="FRONT", subgroup="INSULATION"),
    ]


@pytest.fixture(autouse=True)
def _stub_sections(monkeypatch):
    """_build_bom_items reads the cached BOMSection snapshot; stub it so the
    resolution is testable without a database."""
    from app import services
    snap = services.SectionSnapshot(
        order={}, mults_by_id={}, mults_by_name={},
        optional_by_id={}, optional_by_name={}, by_id={})
    monkeypatch.setattr("app.routers.calculator.get_section_snapshot", lambda: snap)


def _prices(foam, overrides=None):
    items = _build_bom_items(_bom(), {}, overrides or {}, {}, None,
                             insulation_foam=foam)
    return {it["material_name"] + "/" + it["category_name"]: it["price_per_unit"]
            for it in items}


# ── 1. which rows are foam ───────────────────────────────────────────────────

def test_only_the_section_pu_foam_rows_are_graded():
    by_name = {r.material.name: r for r in _bom()}
    assert pu_foam.is_pu_foam_row(by_name["PU"]) is True
    # A different product entirely (R60 each), not the sheet foam.
    assert pu_foam.is_pu_foam_row(by_name["PU INJECTION"]) is False
    assert pu_foam.is_pu_foam_row(by_name["30MM PU INJECTION"]) is False
    assert pu_foam.is_pu_foam_row(by_name["EPS"]) is False
    # "FRONT PU" is the EPS-vs-PU toggle + thickness carrier, never a cost line.
    assert pu_foam.is_pu_foam_row(by_name["FRONT PU"]) is False


def test_grade_normalisation_defaults_to_32d():
    assert pu_foam.normalise("4G") == pu_foam.FOAM_4G
    assert pu_foam.normalise("4g foam") == pu_foam.FOAM_4G
    for junk in (None, "", "32D", "  ", "EPS", "nonsense", 0, True):
        assert pu_foam.normalise(junk) == pu_foam.FOAM_32D
    assert pu_foam.label("4G") == "4G FOAM"
    assert pu_foam.label(None) == "32D PU FOAM"


def test_factor_falls_back_to_the_price_list_ratio():
    assert pu_foam.get_4g_factor(None) == pytest.approx(RATIO)
    # A missing / unparseable / non-positive setting must never price 4G at 32D.
    for bad in (None, SimpleNamespace(value="not-a-number"), SimpleNamespace(value="0")):
        db = SimpleNamespace(query=lambda *_a, **_k: SimpleNamespace(
            filter_by=lambda **_kw: SimpleNamespace(first=lambda: bad)))
        assert pu_foam.get_4g_factor(db) == pytest.approx(RATIO)


# ── 2. the arithmetic ────────────────────────────────────────────────────────

def test_32d_leaves_every_stored_price_untouched():
    assert _prices("32D") == _prices(None) == {
        "PU/DRD": 258.32, "PU/ROOF": 430.54, "EPS/SIDES": 127.72,
        "PU INJECTION/SIDES": 60.0, "30MM PU INJECTION/FLOOR": 60.0,
        "FRONT PU/FRONT": 0.0,
    }


def test_4g_scales_only_the_foam_lines_by_the_ratio():
    base, four_g = _prices("32D"), _prices("4G")
    assert four_g["PU/DRD"] == pytest.approx(258.32 * RATIO)
    assert four_g["PU/ROOF"] == pytest.approx(430.54 * RATIO)
    for key in ("EPS/SIDES", "PU INJECTION/SIDES",
                "30MM PU INJECTION/FLOOR", "FRONT PU/FRONT"):
        assert four_g[key] == base[key], f"{key} must not move with the foam grade"


def test_4g_reaches_the_material_price_and_the_row_override_alike():
    """DRD prices off materials.price_per_unit, ROOF off unit_price_override —
    both are the 32D side and both must grade."""
    four_g = _prices("4G")
    assert four_g["PU/DRD"] / 258.32 == pytest.approx(RATIO)
    assert four_g["PU/ROOF"] / 430.54 == pytest.approx(RATIO)


def test_a_hand_typed_price_override_wins_over_the_grade():
    """A price someone typed is a decision; a default never overwrites a
    decision. The grade applies underneath it, not on top of it."""
    typed = _prices("4G", overrides={"1": 999.0})
    assert typed["PU/DRD"] == 999.0
    assert typed["PU/ROOF"] == pytest.approx(430.54 * RATIO)   # untouched row still grades


def test_the_pair_holds_the_exact_price_list_ratio():
    """Ratified default 5: 4G = 32D x 1.36311 across every PU-using category —
    which holds by construction, because 4G is derived, never stored."""
    base, four_g = _prices("32D"), _prices("4G")
    for key in ("PU/DRD", "PU/ROOF"):
        assert four_g[key] / base[key] == pytest.approx(5875.0 / 4310.0, rel=1e-12)


# ── 3. the classifier (migration 0046) ───────────────────────────────────────

@pytest.mark.parametrize("thickness", [0.041, 0.06, 0.1, 0.12, 0.145])
def test_classifier_recognises_both_grades_at_any_thickness(thickness):
    kind, new = MIG._classify(RATE_32D * thickness, thickness)
    assert (kind, new) == ("32D", None)                    # already 32D — untouched
    kind, new = MIG._classify(RATE_4G * thickness, thickness)
    assert kind == "4G"
    assert new == pytest.approx(RATE_32D * thickness)      # normalised onto 32D


def test_classifier_corrects_burts_2_99_typo_rather_than_replicating_it():
    """Meat Body's front row divides by 2.99. Normalising it must land on the
    SAME 32D value its correctly-typed siblings hold, not 1/2.99th of it."""
    t = 0.06
    typo_price = 5875.0 * (1.22 * 2.44) / 2.99 * t          # 350.94 in the real data
    kind, new = MIG._classify(typo_price, t)
    assert kind == "4G~2.99"
    assert new == pytest.approx(RATE_32D * t, rel=1e-9)     # == the 258.32 sibling


def test_classifier_refuses_anything_it_does_not_recognise():
    """RHINORANGE TRAILER's rows sit on a coherent internal rate of 6373.80 that
    is derived from NEITHER sheet price. Guard: report, write nothing."""
    for price, t in ((637.380, 0.1), (382.430, 0.06), (325.060, 0.051)):
        kind, new = MIG._classify(price, t)
        assert kind == "UNCLASSIFIED"
        assert new is None


def test_classifier_never_touches_a_shared_or_thicknessless_row():
    assert MIG._classify(None, 0.06) == ("SHARED-DEFAULT", None)
    assert MIG._classify(258.32, None) == ("NO-THICKNESS", None)
    assert MIG._classify(258.32, 0) == ("NO-THICKNESS", None)


def test_classifier_band_separates_the_two_closest_classes():
    """4G and the 2.99 typo are only 0.335% apart — the tolerance must not merge
    them, and must not merge a grade with the one below it either."""
    assert MIG.TOLERANCE < abs(MIG.RATE_4G / MIG.RATE_4G_TYPO - 1) / 2
    assert MIG.RATIO_4G == pytest.approx(RATIO, rel=1e-12)


def test_classifier_is_idempotent():
    """Re-running the migration must be a no-op: a normalised row now reads 32D."""
    t = 0.042
    kind, once = MIG._classify(RATE_4G * t, t)
    assert kind == "4G"
    assert MIG._classify(once, t) == ("32D", None)


# ── the quote's saved grade ──────────────────────────────────────────────────

def _insulation_rows():
    return [
        SimpleNamespace(id=1, is_body_option=True, body_option_group="FRONT",
                        body_option_subgroup="INSULATION", variable_value=0.0,
                        material=SimpleNamespace(name="FRONT EPS")),
        SimpleNamespace(id=2, is_body_option=True, body_option_group="FRONT",
                        body_option_subgroup="INSULATION", variable_value=0.06,
                        material=SimpleNamespace(name="FRONT PU")),
    ]


def test_a_saved_record_with_no_foam_key_displays_as_32d():
    """Ratified default 7: existing approvals are frozen and were priced at 32D."""
    derived = _derive_body_options_display(
        _insulation_rows(), {"body_option_selections": {"1": False, "2": True}}, {})
    assert derived["insulation_foam"] == "32D"


def test_a_saved_record_carries_its_own_grade_forward():
    derived = _derive_body_options_display(
        _insulation_rows(),
        {"body_option_selections": {"1": False, "2": True}, "insulation_foam": "4G"},
        {})
    assert derived["insulation_foam"] == "4G"


def test_the_grade_prints_on_the_quote_only_when_the_body_uses_pu():
    from app.routers.exports import _spec_options_from_derived
    pu_quote = {"rear_door": None, "insulation_foam": "4G",
                "panels": [{"location": "FRONT", "insulation": "PU", "thickness_m": 0.06}],
                "floor_type": None}
    assert ("INSULATION FOAM", "4G FOAM") in _spec_options_from_derived(pu_quote)

    eps_quote = dict(pu_quote,
                     panels=[{"location": "FRONT", "insulation": "EPS", "thickness_m": 0.06}])
    labels = [k for k, _ in _spec_options_from_derived(eps_quote)]
    assert "INSULATION FOAM" not in labels
