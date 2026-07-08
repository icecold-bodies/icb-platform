"""Customer-contacts WO §3.6 — the calculator "Attention" contact picker (journey).

Drives the REAL legacy calculator page (/mes/calculator — the exact template the SPA
iframes at /costings/new) end-to-end: a customer with a primary contact auto-selects it;
switching to a zero-contact customer shows the empty state; the inline "+ Add now"
quick-add POSTs (200 asserted), and the fresh contact comes back selected. Marker rows
J140CC*, created + purged here — no real icb_costings data touched.
"""
from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, admin_session, shot  # noqa: E402

T = 15_000
JOURNEY = "calc_contact_picker"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.customer_contacts cc USING icb_costings.customers c "
        "WHERE cc.customer_id = c.id AND c.name LIKE 'J140CC%'"))
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'J140CC%'"))
    db.commit()


@pytest.fixture()
def contact_customers():
    from app.database import Customer, CustomerContact, SessionLocal
    with SessionLocal() as db:
        _purge(db)
        rich = Customer(name="J140CC Rich Ltd", bp_code="J140CC1", is_active=True, is_dealer=False)
        bare = Customer(name="J140CC Bare Ltd", bp_code="J140CC2", is_active=True, is_dealer=False)
        db.add_all([rich, bare])
        db.flush()
        db.add_all([
            CustomerContact(customer_id=rich.id, name="J140CC Piet", role="Buyer",
                            email="piet@j140cc.co", is_active=True),
            CustomerContact(customer_id=rich.id, name="J140CC Sannie", role="Owner",
                            email="sannie@j140cc.co", is_primary=True, is_active=True),
        ])
        db.commit()
        ids = (rich.id, bare.id)
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def test_calc_attention_picker(page: Page, contact_customers) -> None:
    rich_id, bare_id = contact_customers
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)

    page.goto("/mes/calculator")
    expect(page.locator("#contact-select")).to_be_visible(timeout=T)
    # loadCustomers() has resolved once the list is populated; the change listener is
    # bound synchronously right after that await, so selecting is safe from here on.
    page.wait_for_function(
        "document.querySelectorAll('#cust-select option').length > 1", timeout=30_000)
    expect(page.locator("#contact-select")).to_be_disabled()   # no customer yet

    # customer with contacts → the PRIMARY auto-selects
    with page.expect_response(
            lambda r: f"/api/customers/{rich_id}/contacts" in r.url, timeout=T):
        page.select_option("#cust-select", str(rich_id))
    expect(page.locator("#contact-select")).to_be_enabled(timeout=T)
    picked = page.locator("#contact-select option:checked").text_content() or ""
    assert "Sannie" in picked and "primary" in picked, f"primary not auto-selected: {picked!r}"
    shot(page, "01-primary-autoselected", journey=JOURNEY)

    # zero-contact customer → empty state with "+ Add now"
    with page.expect_response(
            lambda r: f"/api/customers/{bare_id}/contacts" in r.url, timeout=T):
        page.select_option("#cust-select", str(bare_id))
    expect(page.locator("#contact-empty")).to_be_visible(timeout=T)
    shot(page, "02-empty-state-add-now", journey=JOURNEY)

    # inline quick-add → 200 POST → auto-selected
    page.locator("#contact-empty a").click()
    expect(page.locator("#contact-add-form")).to_be_visible(timeout=T)
    page.locator("#contact-new-name").fill("J140CC Nadie Pick")
    page.locator("#contact-new-role").fill("Buyer")
    page.locator("#contact-new-email").fill("nadie@j140cc.co")
    with page.expect_response(
            lambda r: r.url.endswith(f"/api/customers/{bare_id}/contacts")
            and r.request.method == "POST", timeout=T) as ri:
        page.locator("#contact-add-form button:has-text('Save contact')").click()
    assert ri.value.status == 200, f"quick-add returned {ri.value.status}"
    expect(page.locator("#contact-select")).to_be_enabled(timeout=T)
    picked2 = page.locator("#contact-select option:checked").text_content() or ""
    assert "Nadie Pick" in picked2, f"quick-added contact not selected: {picked2!r}"
    shot(page, "03-quickadd-selected", journey=JOURNEY)

    # switching back re-populates from the other customer (no stale carry-over)
    with page.expect_response(
            lambda r: f"/api/customers/{rich_id}/contacts" in r.url, timeout=T):
        page.select_option("#cust-select", str(rich_id))
    picked3 = page.locator("#contact-select option:checked").text_content() or ""
    assert "Sannie" in picked3, f"cascade did not re-populate on customer change: {picked3!r}"
