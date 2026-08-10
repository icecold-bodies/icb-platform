"""v1.45 §3.4 — "Email it instead…" on the Preview and Export dialogs (journey).

What this proves that the unit tests can't: the WIRING. On the embed the dialog
lives in the React parent while the calculator state (and therefore the send)
lives in the iframe, so a click has to cross postMessage twice — request down,
result back up — before the button can leave "Sending…". That round-trip is the
fiddly part and it is what this journey exercises end to end.

Deliberate scope note: the journey server has no SMTP configured (nor should a
test box send real mail), so the send completes as the ratified LOUD failure —
a 503 surfaced verbatim in the dialog. That is itself a required behaviour: the
sibling notification helpers log-and-continue, and this one must not, because
the user is sitting in front of the dialog. The success path — attachment,
filename, Cc, draft-vs-quotation framing, byte-identical document — is asserted
at MIME level in tests/test_costing_email.py with SMTP stubbed.

Marker J145EM; purged both sides.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402

T = 15_000
JOURNEY = "costing_email"
MARK = "J145EM"
CONTACT_EMAIL = "attention@j145em.co.za"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.calculations WHERE trailer_type_id IN "
        "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text(
        "DELETE FROM icb_costings.bill_of_materials WHERE material_id IN "
        "(SELECT id FROM icb_costings.materials WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.customer_contacts WHERE email = :e"),
               {"e": CONTACT_EMAIL})
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    """Calculable marker body + a customer whose contact carries a known email
    (the recipient pre-fill), + an approved-shaped record for the Export side."""
    from app.database import (BillOfMaterial, CalculationRecord, Customer,
                              CustomerContact, Material, SessionLocal, TrailerType, User)
    with SessionLocal() as db:
        _purge(db)
        tt = TrailerType(name=f"{MARK} EMAIL BODY", is_active=True,
                         default_length=6.0, default_width=2.4, default_height=2.4)
        db.add(tt)
        db.flush()
        mat = Material(name=f"{MARK} PANEL SHEET", unit_of_measure="m2", price_per_unit=250.0)
        db.add(mat)
        db.flush()
        db.add(BillOfMaterial(trailer_type_id=tt.id, material_id=mat.id,
                              formula_expression="1", waste_percentage=0,
                              bom_section="PANELS", sort_order=1))
        cust = Customer(name=f"{MARK} CUSTOMER")
        db.add(cust)
        db.flush()
        db.add(CustomerContact(customer_id=cust.id, name="Jo Buyer",
                               email=CONTACT_EMAIL, is_primary=True, is_active=True))
        admin = db.query(User).filter_by(username="admin").first()
        rec = CalculationRecord(
            trailer_type_id=tt.id, user_id=admin.id, customer_id=cust.id,
            status="pending", quote_number=f"{MARK}/01/2026",
            contact_email=CONTACT_EMAIL,
            dimensions_json=json.dumps({"length": 6.0, "width": 2.4, "height": 2.4}),
            result_json=json.dumps({
                "items": [{"category": "PANELS", "material": f"{MARK} PANEL SHEET",
                           "material_code": "", "formula": "1", "quantity": 1.0,
                           "unit": "m2", "unit_price": 250.0, "waste_pct": 0,
                           "line_cost": 250.0, "last_updated": None}],
                "category_totals": {"PANELS": 250.0},
                "grand_total": 250.0, "cost_per_sqm": 17.36,
                # /results iterates result.geometry unguarded (banked trap)
                "geometry": {"floor_area": 14.4, "surface_area": 71.0,
                             "wall_area": 28.8, "roof_area": 14.4},
            }))
        db.add(rec)
        db.commit()
        ids = {"trailer": tt.id, "rec": rec.id, "cust": cust.id, "name": tt.name}
    yield ids
    with SessionLocal() as db:
        _purge(db)


def _select_trailer_and_wait_bom(page: Page, frame, trailer_id: str, attempts: int = 4) -> None:
    """select_option → loadBOM is one-shot and can be lost while the embed settles
    (banked v1.44 flake class) — re-select until a BOM row renders."""
    row = frame.locator("[data-material-id]").first
    for _ in range(attempts):
        frame.locator("#trailer-select").select_option(trailer_id)
        try:
            expect(row).to_be_visible(timeout=8_000)
            return
        except AssertionError:
            continue
    raise AssertionError("BOM rows never rendered")


def test_preview_dialog_email_round_trip(page: Page, live_server: str, staged) -> None:
    """Embed side: pre-fill from the selected contact, then the postMessage
    round-trip carries the outcome back into the dialog."""
    ids = staged
    admin_session(page, base=live_server)
    page.goto("/mes-app/costings/new")

    frame = page.frame_locator("iframe[title='Calculator (live costing app)']")
    expect(frame.locator("#trailer-select")).to_be_visible(timeout=30_000)
    _select_trailer_and_wait_bom(page, frame, str(ids["trailer"]))

    # Pick the customer + its contact so the dialog has something to pre-fill.
    frame.locator("#cust-select").select_option(str(ids["cust"]))
    contact = frame.locator("#contact-select")
    expect(contact.locator("option")).to_have_count(2, timeout=T)   # placeholder + Jo Buyer
    contact.select_option(index=1)
    frame.locator("#f-length").fill("6.5")
    expect(frame.locator("#approve-btn")).to_be_enabled(timeout=30_000)

    page.get_by_test_id("preview-btn").click()
    expect(page.get_by_test_id("export-confirm")).to_be_visible(timeout=T)

    page.get_by_test_id("export-email-open").click()
    to = page.get_by_test_id("export-email-to")
    expect(to).to_be_visible(timeout=T)
    expect(to).to_have_value(CONTACT_EMAIL)                 # pre-filled from the contact
    page.get_by_test_id("export-email-note").fill("Draft for your review.")
    shot(page, "01-preview-email-panel", journey=JOURNEY)

    # Send: crosses parent → iframe → server → iframe → parent. The journey box has
    # no SMTP, so the ratified LOUD failure is what must come back — and crucially
    # the button must leave "Sending…" rather than hang.
    page.get_by_test_id("export-email-send").click()
    outcome = page.locator("[data-testid='export-email-sent'], [data-testid='export-email-error']")
    expect(outcome.first).to_be_visible(timeout=T)
    expect(page.get_by_test_id("export-email-send")).to_be_enabled(timeout=T)
    shot(page, "02-preview-email-outcome", journey=JOURNEY)


def test_email_send_blocked_until_an_address_is_entered(page: Page, live_server: str,
                                                        staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    page.goto("/mes-app/costings/new")
    frame = page.frame_locator("iframe[title='Calculator (live costing app)']")
    expect(frame.locator("#trailer-select")).to_be_visible(timeout=30_000)
    _select_trailer_and_wait_bom(page, frame, str(ids["trailer"]))
    frame.locator("#f-length").fill("6.5")
    expect(frame.locator("#approve-btn")).to_be_enabled(timeout=30_000)

    page.get_by_test_id("preview-btn").click()
    expect(page.get_by_test_id("export-confirm")).to_be_visible(timeout=T)
    page.get_by_test_id("export-email-open").click()
    # No customer picked → nothing to pre-fill → Send stays disabled until typed.
    expect(page.get_by_test_id("export-email-to")).to_have_value("")
    expect(page.get_by_test_id("export-email-send")).to_be_disabled()
    page.get_by_test_id("export-email-to").fill("someone@example.com")
    expect(page.get_by_test_id("export-email-send")).to_be_enabled()
    shot(page, "03-send-enabled-after-typing", journey=JOURNEY)


def test_results_page_export_dialog_has_email(page: Page, live_server: str, staged) -> None:
    """Legacy /results side: the same panel, pre-filled from the record's saved
    Attention contact, and the send reports an outcome rather than hanging."""
    ids = staged
    admin_session(page, base=live_server)
    page.goto(f"/results/{ids['rec']}")

    page.locator("#excel-export-btn").click()
    expect(page.locator("#modal-export-options")).to_be_visible(timeout=T)
    page.locator("#exp-email-toggle").click()
    to = page.locator("#exp-email-to")
    expect(to).to_be_visible(timeout=T)
    expect(to).to_have_value(CONTACT_EMAIL)                 # snapshot on the record
    shot(page, "04-results-email-panel", journey=JOURNEY)

    page.locator("#exp-email-send").click()
    expect(page.locator("#exp-email-msg")).to_be_visible(timeout=T)
    expect(page.locator("#exp-email-send")).to_be_enabled(timeout=T)
    shot(page, "05-results-email-outcome", journey=JOURNEY)
