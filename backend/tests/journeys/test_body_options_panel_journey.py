"""v1.42 §3.4 — Body options panel journey (costing detail page).

Admin opens a costing's detail page and sees the door/insulation/floor-type
summary derived server-side from the saved input_state + BOM body-option rows
(see calculator.py::_derive_body_options_display, wired into GET
/api/calculations/{id} as the additive `body_options_display` key). Covers both
states: a populated panel on a record with a full input_state snapshot (a
minimal trailer + 4 BOM body-option rows — not the full priced BOM universe,
since /api/approve's own compute path is untouched by this WO), and the muted
"not recorded" fallback on a genuine CI-seeded mockup-derived costing (those
carry no trailer_type_id/body_variables at all — scripts/seed_from_mockup.py).
J1420BOP markers; purge at setup AND teardown.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "body_options_panel"
MARK = "J1420BOP"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_costings.calculations WHERE quote_number LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text(
        "DELETE FROM icb_costings.bill_of_materials WHERE material_id IN "
        "(SELECT id FROM icb_costings.materials WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    """A minimal trailer + FRONT/DRD EPS-PU body-option pairs + a saved
    calculation snapshotting a real choice (PU front, EPS rear door) — enough
    for the derivation helper without the full priced BOM universe."""
    from app.database import BillOfMaterial, CalculationRecord, Material, SessionLocal, TrailerType
    with SessionLocal() as db:
        _purge(db)
        trailer = TrailerType(name=f"{MARK} Test Trailer", is_active=True)
        db.add(trailer)
        db.flush()

        def _mat(name):
            m = Material(name=f"{MARK} {name}", unit_of_measure="each", price_per_unit=0.0)
            db.add(m)
            db.flush()
            return m

        front_eps, front_pu = _mat("FRONT EPS"), _mat("FRONT PU")
        drd_eps, drd_pu = _mat("DRD EPS"), _mat("DRD PU")

        def _bom(material, group, value):
            row = BillOfMaterial(trailer_type_id=trailer.id, material_id=material.id,
                                 is_body_option=True, body_option_group=group,
                                 body_option_subgroup="INSULATION", variable_value=value)
            db.add(row)
            db.flush()
            return row

        r_feps = _bom(front_eps, "FRONT", 0.0)
        r_fpu = _bom(front_pu, "FRONT", 0.06)
        r_deps = _bom(drd_eps, "DRD", 0.06)
        r_dpu = _bom(drd_pu, "DRD", 0.0)

        result_json = {
            "items": [],
            "body_variables": {
                front_eps.name: 0.0, front_pu.name: 0.06,
                drd_eps.name: 0.06, drd_pu.name: 0.0,
            },
            "input_state": {
                "body_option_selections": {
                    str(r_feps.id): False, str(r_fpu.id): True,
                    str(r_deps.id): True, str(r_dpu.id): False,
                },
                "ui_snapshot": {"drd_srd": {"DRD": True, "SRD": False}},
            },
        }
        calc = CalculationRecord(
            quote_number=f"{MARK}/07/2026", trailer_type_id=trailer.id,
            status="pending", dimensions_json="{}",
            result_json=json.dumps(result_json),
        )
        db.add(calc)
        db.commit()
        quote_number = calc.quote_number
    yield {"quote_number": quote_number}
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


@pytest.fixture(scope="module")
def seeded_costing():
    """A genuine mockup-seeded costing (never our own J1420BOP marker rows) —
    these carry no trailer_type_id/body_variables at all, so they exercise the
    muted-fallback path deterministically regardless of test/fixture ordering."""
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        calc = (db.query(CalculationRecord)
                .filter(CalculationRecord.quote_number.isnot(None),
                        ~CalculationRecord.quote_number.like(f"{MARK}%"),
                        CalculationRecord.trailer_type_id.is_(None))
                .order_by(CalculationRecord.id.asc()).first())
        if calc is None:
            pytest.skip("no seeded (non-body-data) costing on this DB to exercise the muted fallback")
        return calc.quote_number


def _goto_costing(page: Page, quote_number: str) -> None:
    from urllib.parse import quote
    page.goto(f"/mes-app/costings/{quote(quote_number, safe='')}")
    expect(page.get_by_test_id("top-nav")).to_be_visible(timeout=T)


def test_populated_panel_on_snapshot_record(page: Page, staged) -> None:
    admin_session(page)
    _goto_costing(page, staged["quote_number"])
    panel = page.get_by_test_id("body-options-panel")
    expect(panel).to_be_visible(timeout=T)
    expect(panel.get_by_text("Rear door — DRD · EPS 60 mm")).to_be_visible(timeout=T)
    expect(panel.get_by_text("Front — PU 60 mm")).to_be_visible(timeout=T)
    expect(page.get_by_test_id("body-options-not-recorded")).to_have_count(0)
    shot(page, "01-populated-panel", journey=JOURNEY)


def test_muted_fallback_on_seeded_costing(page: Page, seeded_costing: str) -> None:
    admin_session(page)
    _goto_costing(page, seeded_costing)
    panel = page.get_by_test_id("body-options-panel")
    expect(panel).to_be_visible(timeout=T)
    expect(page.get_by_test_id("body-options-not-recorded")).to_be_visible(timeout=T)
    shot(page, "02-muted-fallback", journey=JOURNEY)
