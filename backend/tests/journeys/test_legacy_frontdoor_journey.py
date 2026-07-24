"""v1.43 — MES sole front door journey (real browser).

Proves the ratified landing chain end-to-end and guards the embed surface the
redirect must NOT break:

* unauthenticated:  "/" → /mes-app/ → /login?next=/mes-app/ (Jinja login, no chrome)
* authenticated:    "/" → /mes-app/ → the React MES shell (top-nav mounts)
* a costing's "Print costing PDF (MES style)" still opens the legacy /results/{id}
  page (CostingDetail window.open — the print/PDF surface Nadie uses daily)

The calculator-iframe-on-/costings/new guard already lives in
test_costings_unified_journey.py (§0.6 contract) and stays green untouched.

Costing rows are seeded directly (the /api/approve pipeline needs the full BOM
universe the test DB doesn't have — test_costings_contact_column_journey.py
precedent); marker rows ZLFD* purged both sides.
"""
from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 20_000
JOURNEY = "legacy_frontdoor"
MARK = "ZLFD"

# Just enough result_json for results.html to render (mirrors
# test_legacy_frontdoor.py — strict |float filters + dict iteration).
RESULT_JSON = ('{"items": [], "grand_total": 0, "selling_price": 0, "cost_per_sqm": 0, '
               '"profit_margin": 0, "profit_amount": 0, "ratio_label": "", "ratio_amount": 0, '
               '"geometry": {}, "category_totals": {}, "category_multipliers": {}}')


def _purge():
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        for r in db.query(CalculationRecord).filter(
                CalculationRecord.quote_number.like(f"{MARK}%")).all():
            db.delete(r)
        db.commit()


@pytest.fixture()
def seeded_costing():
    from app.database import CalculationRecord, SessionLocal
    _purge()
    quote = f"{MARK}{uuid.uuid4().hex[:5].upper()}"
    with SessionLocal() as db:
        rec = CalculationRecord(quote_number=quote, dimensions_json="{}",
                                result_json=RESULT_JSON, status="pending")
        db.add(rec)
        db.commit()
        rec_id = rec.id
    yield {"id": rec_id, "quote": quote}
    _purge()


def test_root_lands_on_login_unauth(page: Page, live_server: str) -> None:
    # Fresh context, no session: the bare root chains to the Jinja login — never
    # the legacy dark GRP dashboard, never MES chrome/data.
    page.goto(f"{live_server}/")
    assert "/login" in page.url and "next=/mes-app/" in page.url, page.url
    expect(page.get_by_text("Trailer Costing System")).to_be_visible(timeout=T)
    shot(page, "01-unauth-root-lands-on-login", journey=JOURNEY)


def test_root_lands_in_mes_authed(page: Page, live_server: str) -> None:
    # With a session, "/" hands off to the React MES shell (the sole front door).
    admin_session(page, base=live_server)
    page.goto(f"{live_server}/")
    page.wait_for_selector("[data-testid='top-nav']", timeout=30_000)
    assert page.url.startswith(f"{live_server}/mes-app"), page.url
    shot(page, "02-authed-root-lands-in-mes", journey=JOURNEY)


def test_print_costing_pdf_opens_results(page: Page, live_server: str,
                                         seeded_costing) -> None:
    admin_session(page, base=live_server)
    page.goto(f"/mes-app/costings/{seeded_costing['quote']}")
    btn = page.get_by_role("button", name="Print costing PDF (MES style)")
    expect(btn).to_be_visible(timeout=T)
    # window.open(..., 'noopener') severs the opener, so the new tab arrives as a
    # context page event — page.expect_popup() would never fire.
    with page.context.expect_page(timeout=T) as new_page_info:
        btn.click()
    popup = new_page_info.value
    popup.wait_for_load_state()
    assert f"/results/{seeded_costing['id']}" in popup.url, popup.url
    # The legacy results page rendered (title = "Results <quote>"), not a login bounce.
    assert seeded_costing["quote"] in popup.title(), popup.title()
    shot(popup, "03-print-pdf-opens-results", journey=JOURNEY)
