"""v1.54 — the costing page lists a saved costing's BOM in the calculator's order (journey).

Michael (15 Sep): "when the user views the BOM in a costing the items must be in the same
order as in the costings. this order is the same as the body type is on the template."

The body below is built so the three candidate orders all DISAGREE, which is what gives
the assertion teeth:

  template rows     FRONT: ZETA PANEL(1), ALPHA PANEL(2)   SIDES: ZULU SHEET(3), ALPHA SHEET(4)
  stored costing    SIDES first (its global section sort is lower), each section A–Z
  => the calculator shows the template order; before v1.54 the costing page showed the
     stored one.

The script: open the body in the calculator → read its BOM lines in ON-SCREEN order →
they are the template order → save → open the costing page → its bill of materials lists
the same lines in the same order.

Marker rows J154BO* only — created and purged here. Base-aware (MES_BASE).
"""
from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, admin_session, shot  # noqa: E402

T = 20_000
JOURNEY = "costing_bom_order"
MARK = "J154BO"
ORDER = ["ZETA PANEL", "ALPHA PANEL", "ZULU SHEET", "ALPHA SHEET"]   # template order


def _base() -> str:
    return os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_costings.calculations c USING icb_costings.customers cu "
                    "WHERE c.customer_id = cu.id AND cu.name LIKE 'J154BO%'"))
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'J154BO%')"))
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE 'J154BO%'"))
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE 'J154BO%'"))
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE 'J154BO%'"))
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'J154BO%'"))
    db.commit()


@pytest.fixture(scope="module")
def body():
    from app.database import (SessionLocal, TrailerType, BillOfMaterial, BOMSection,
                              Material, Customer)
    with SessionLocal() as db:
        _purge(db)
        sides = BOMSection(name=f"{MARK} SIDES", sort_order=1, is_optional=False)
        front = BOMSection(name=f"{MARK} FRONT", sort_order=2, is_optional=False)
        tt = TrailerType(name=f"{MARK} BODY", is_active=True, default_length=6.0,
                         default_width=2.5, default_height=2.4)
        cust = Customer(name=f"{MARK} Carriers", bp_code=f"{MARK}1", is_active=True)
        mats = {n: Material(name=f"{MARK} {n}", unit_of_measure="each",
                            price_per_unit=10.0, is_active=True) for n in ORDER}
        db.add_all([sides, front, tt, cust, *mats.values()])
        db.flush()
        rows = {}
        for n, sec, so in ((ORDER[0], front, 1), (ORDER[1], front, 2),
                           (ORDER[2], sides, 3), (ORDER[3], sides, 4)):
            rows[n] = BillOfMaterial(trailer_type_id=tt.id, material_id=mats[n].id,
                                     formula_expression="1", waste_percentage=0,
                                     bom_section=sec.name, bom_section_id=sec.id, sort_order=so)
            db.add(rows[n])
        db.commit()
        ids = {"tt": tt.id, "customer": cust.id,
               "template_order": [str(rows[n].id) for n in ORDER]}
    yield ids
    with SessionLocal() as db:
        _purge(db)


def test_the_costing_page_lists_the_bom_in_the_calculator_order(page: Page, body) -> None:
    base = _base()
    admin_session(page, base=base)

    # ── the calculator: the lines in on-screen order ────────────────────────
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(body["tt"]))
    page.select_option("#f-ratio", "")
    lines = page.locator("#bom-area tr.calc-grp-row[data-bom-id]")
    expect(lines).to_have_count(4, timeout=T)
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    calculator_order = lines.evaluate_all("els => els.map(e => e.dataset.bomId)")
    assert calculator_order == body["template_order"], \
        f"the calculator itself no longer shows the template order: {calculator_order}"
    # The sections open collapsed; the rows are in the DOM either way (read above), but
    # the screenshot should show them.
    if "Expand" in (page.locator("#bom-collapse-txt").text_content() or ""):
        page.click("#bom-collapse-lbl")
    shot(page, "01-calculator-template-order", JOURNEY)

    page.select_option("#cust-select", value=str(body["customer"]))
    page.click("#approve-btn")
    rec_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec_id:
            break
    assert rec_id, "the costing did not save"
    from app.database import CalculationRecord, SessionLocal
    import json as _json
    with SessionLocal() as db:
        rec = db.get(CalculationRecord, int(rec_id))
        quote = rec.quote_number
        stored = [str(it["bom_id"]) for it in _json.loads(rec.result_json)["items"]]
    assert stored != calculator_order, \
        "premise: the stored order must differ from the calculator's, or this proves nothing"

    # ── the costing page: the same lines, the same order ────────────────────
    page.goto("/mes-app/costings")
    expect(page.get_by_test_id("costings-table")).to_be_visible(timeout=T)
    page.locator("[data-testid='costing-row']").filter(has_text=quote).first.click()
    rows = page.get_by_test_id("live-bom-row")
    expect(rows).to_have_count(4, timeout=T)
    costing_page_order = rows.evaluate_all("els => els.map(e => e.dataset.bomId)")
    rows.first.scroll_into_view_if_needed()
    shot(page, "02-costing-page-same-order", JOURNEY)
    assert costing_page_order == calculator_order, (
        f"costing page {costing_page_order} != calculator {calculator_order}")
