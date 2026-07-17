"""v1.42 — OPTIONAL-name-prefix sections are opt-in (excluded until enabled).

Michael's rule (17 Jul): any BOM section whose name starts with "OPTIONAL"
(case-insensitive) behaves like OPTIONAL EXTRAS — its lines are excluded from
costing totals unless the user enables the section — regardless of the stored
BOMSection.is_optional flag. Derived at read time in
services.section_effective_optional; the stored flag is never written.

Covers: the pure rule; the _build_bom_items exclusion gate honouring a
prefix-only section (flag=False) end-to-end against marker rows; and
GET /api/bom-sections returning the EFFECTIVE value (what the calculators'
opt-in UI and the Body Templates red styling read).

House pattern (test_calculation_contact_api.py): live test DB, marker rows
'J142OPT*', module-local fixtures, purge on both sides.
"""
import pytest

from app.services import section_effective_optional

_MARK = "J142OPT"


# ── The rule itself ───────────────────────────────────────────────────────────

def test_flag_true_is_optional_regardless_of_name():
    assert section_effective_optional("EXTRAS", True) is True


def test_prefix_only_is_optional_without_flag():
    assert section_effective_optional("OPTIONAL EXPLOSIVE EXTRAS", False) is True


def test_prefix_is_case_insensitive_and_trimmed():
    assert section_effective_optional("optional extras", False) is True
    assert section_effective_optional("  Optional Fittings", False) is True


def test_plain_name_without_flag_is_not_optional():
    assert section_effective_optional("FRONT", False) is False
    assert section_effective_optional("", False) is False
    assert section_effective_optional(None, False) is False


def test_optional_must_be_a_prefix_not_a_substring():
    assert section_effective_optional("NON OPTIONAL EXTRAS", False) is False


# ── Live fixtures ─────────────────────────────────────────────────────────────

def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.bill_of_materials WHERE material_id IN "
        "(SELECT id FROM icb_costings.materials WHERE name LIKE :m)"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE :m OR name LIKE :om"),
               {"m": f"{_MARK}%", "om": f"OPTIONAL {_MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


@pytest.fixture
def staged(app_mod):
    """Marker trailer + one BOM row in a section named 'OPTIONAL J142OPT EXTRAS'
    whose stored is_optional flag is FALSE — optional purely by name prefix —
    plus a plain marker section as the control."""
    from app.database import (BillOfMaterial, BOMSection, Material, SessionLocal,
                              TrailerType)
    with SessionLocal() as db:
        _purge(db)
        trailer = TrailerType(name=f"{_MARK} TRAILER", is_active=True)
        opt_sec = BOMSection(name=f"OPTIONAL {_MARK} EXTRAS", sort_order=9001,
                             is_optional=False)          # ← prefix rule only
        plain_sec = BOMSection(name=f"{_MARK} PLAIN", sort_order=9002,
                               is_optional=False)
        mat = Material(name=f"{_MARK} WIDGET", unit_of_measure="each", price_per_unit=10.0)
        db.add_all([trailer, opt_sec, plain_sec, mat])
        db.flush()
        row = BillOfMaterial(trailer_type_id=trailer.id, material_id=mat.id,
                             formula_expression="1", bom_section=opt_sec.name,
                             bom_section_id=opt_sec.id)
        plain_row = BillOfMaterial(trailer_type_id=trailer.id, material_id=mat.id,
                                   formula_expression="1", bom_section=plain_sec.name,
                                   bom_section_id=plain_sec.id)
        db.add_all([row, plain_row])
        db.commit()
        ids = {"trailer": trailer.id, "opt_sec": opt_sec.id, "plain_sec": plain_sec.id,
               "row": row.id, "plain_row": plain_row.id}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _items_for(db, ids, enabled):
    from app.database import BillOfMaterial
    from app.routers.calculator import _build_bom_items
    from app.services import _bom_load_options
    rows = (db.query(BillOfMaterial)
            .filter_by(trailer_type_id=ids["trailer"])
            .options(*_bom_load_options()).all())
    dims = {"length": 1.0, "width": 1.0, "height": 1.0}
    return _build_bom_items(rows, dims, {}, {}, db,
                            optional_sections_enabled=enabled)


def test_prefix_named_section_defaults_excluded_and_opts_in(staged):
    from app.database import SessionLocal
    ids = staged
    with SessionLocal() as db:
        # Default: the OPTIONAL-prefixed section's row is excluded, the plain one is not.
        items = _items_for(db, ids, enabled=None)
        by_bid = {it.get("bom_id"): it for it in items}
        opt_it = by_bid[ids["row"]]
        assert opt_it.get("excluded_reason") == "Optional section not enabled"
        assert opt_it.get("section_is_optional") is True
        plain_it = by_bid[ids["plain_row"]]
        assert not plain_it.get("excluded_reason")
        assert not plain_it.get("section_is_optional")

        # Enabling the section by id includes the row — the existing opt-in flow.
        items_on = _items_for(db, ids, enabled=[ids["opt_sec"]])
        assert not {it.get("bom_id"): it for it in items_on}[ids["row"]].get("excluded_reason")


def test_bom_sections_endpoint_reports_effective_optional(app_mod, staged):
    from starlette.testclient import TestClient
    ids = staged
    with TestClient(app_mod.app) as c:
        rows = c.get("/api/bom-sections").json()
        by_id = {r["id"]: r for r in rows}
        assert by_id[ids["opt_sec"]]["is_optional"] is True    # prefix rule, flag False
        assert by_id[ids["plain_sec"]]["is_optional"] is False  # control unchanged
