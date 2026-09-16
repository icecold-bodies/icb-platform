"""v1.56 — the costing page shows the parameters the body was priced at (journey).

Michael (16 Sep, with a screenshot of the Quotation / Configuration Overview card):
"Please also add to where the users views the captured costing the parameters of the body
i.e. Len, width and height. currently there is only the body options."

The script: type distinctive parameters into the calculator → save the costing → open it
from the costings list → the overview card reads back exactly what was typed. Then the
other half of the ask: a REPAIR has no geometry, so the row must not appear at all rather
than reading 0 × 0 × 0.

Marker rows J156BP* only — created and purged here. Base-aware (MES_BASE).
"""
from __future__ import annotations

import json
import os

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, admin_session, shot  # noqa: E402

T = 20_000
JOURNEY = "costing_parameters"
MARK = "J156BP"
TYPED = {"f-length": "7.3", "f-width": "2.45", "f-height": "2.9"}


def _base() -> str:
    return os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_costings.calculations c USING icb_costings.customers cu "
                    "WHERE c.customer_id = cu.id AND cu.name LIKE 'J156BP%'"))
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'J156BP%')"))
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE 'J156BP%'"))
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE 'J156BP%'"))
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE 'J156BP%'"))
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'J156BP%'"))
    db.commit()


@pytest.fixture(scope="module")
def staged():
    from app.database import (SessionLocal, TrailerType, BillOfMaterial, BOMSection,
                              Material, Customer, CalculationRecord)
    with SessionLocal() as db:
        _purge(db)
        sec = BOMSection(name=f"{MARK} PANELS", sort_order=1, is_optional=False)
        tt = TrailerType(name=f"{MARK} BODY", is_active=True, default_length=6.0,
                         default_width=2.5, default_height=2.4)
        cust = Customer(name=f"{MARK} Carriers", bp_code=f"{MARK}1", is_active=True)
        mat = Material(name=f"{MARK} SKIN", unit_of_measure="m2", price_per_unit=100.0,
                       is_active=True)
        db.add_all([sec, tt, cust, mat])
        db.flush()
        db.add(BillOfMaterial(trailer_type_id=tt.id, material_id=mat.id,
                              formula_expression="length*width", waste_percentage=0,
                              bom_section=sec.name, bom_section_id=sec.id, sort_order=1))
        # A repair, straight into the shape a repair is stored in: no geometry at all.
        repair = CalculationRecord(
            customer_id=cust.id, dimensions_json="{}", status="pending", is_repair=True,
            quote_number=f"{MARK}R/09/2026",
            result_json=json.dumps({"items": [], "grand_total": 0, "selling_price": 0}),
        )
        db.add(repair)
        db.commit()
        ids = {"tt": tt.id, "customer": cust.id, "repair_quote": repair.quote_number}
    yield ids
    with SessionLocal() as db:
        _purge(db)


def _wait_calc_idle(page: Page, quiet_ms: int = 1_200, timeout_s: int = 60) -> None:
    """`expect(#approve-btn).to_be_enabled()` alone is a LEVEL check (the banked
    level-vs-edge lesson): every dimension edit goes through scheduleCalc()'s 700 ms
    debounce, and the button only goes disabled once that timer fires — approve in the gap
    and the costing is saved from the PREVIOUS calc, defaults and all. Wait for the button
    to STAY enabled across a window longer than the debounce."""
    import time
    approve = page.locator("#approve-btn")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        expect(approve).to_be_enabled(timeout=T)
        page.wait_for_timeout(quiet_ms)
        if approve.is_enabled():
            return
    raise AssertionError(f"the calculator never went idle within {timeout_s}s")


def _open_costing(page: Page, quote: str) -> None:
    page.goto("/mes-app/costings")
    expect(page.get_by_test_id("costings-table")).to_be_visible(timeout=T)
    page.locator("[data-testid='costing-row']").filter(has_text=quote).first.click()
    expect(page.get_by_text("Quotation / Configuration Overview")).to_be_visible(timeout=T)


def test_the_costing_page_reads_back_the_parameters_that_were_typed(page: Page, staged) -> None:
    admin_session(page, base=_base())

    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(staged["tt"]))
    expect(page.locator("#bom-area tr.calc-grp-row[data-bom-id]")).to_have_count(1, timeout=T)
    for field, value in TYPED.items():
        page.fill(f"#{field}", value)
    page.select_option("#cust-select", value=str(staged["customer"]))
    _wait_calc_idle(page)
    page.click("#approve-btn")

    rec_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec_id:
            break
    assert rec_id, "the costing did not save"
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        rec = db.get(CalculationRecord, int(rec_id))
        quote, stored = rec.quote_number, json.loads(rec.dimensions_json)
    assert [str(stored[k]) for k in ("length", "width", "height")] == list(TYPED.values()), \
        f"premise: the costing stored {stored} instead of what was typed"

    _open_costing(page, quote)
    card = page.get_by_test_id("costing-parameters")
    expect(card).to_be_visible(timeout=T)
    shown = " ".join((card.text_content() or "").split())
    assert "7.3 × 2.45 × 2.9 m" in shown, f"the card reads {shown!r}"
    assert "Length × Width × Height" in shown, f"the card does not say which is which: {shown!r}"
    card.scroll_into_view_if_needed()
    shot(page, "01-parameters-on-the-costing", JOURNEY)


def test_a_repair_shows_no_parameters_rather_than_zeroes(page: Page, staged) -> None:
    admin_session(page, base=_base())
    _open_costing(page, staged["repair_quote"])
    expect(page.get_by_test_id("costing-parameters")).to_have_count(0)
    shot(page, "02-repair-has-no-parameters", JOURNEY)
