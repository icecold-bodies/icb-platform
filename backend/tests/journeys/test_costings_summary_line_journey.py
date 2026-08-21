"""WO v1.50 P1 — the END USER in brackets on the costings summary line (marker J150SL).

Nadie, 20 Aug 2026: the end user shipped in #141 as a permanent snapshot on the
costing, but it was only readable by opening the costing. She wants it beside the
customer on the board, so a reseller's twelve quotes tell themselves apart at a
glance.

The whole feature is one table cell, and both of its states matter equally, so
both are asserted against the SAME rendered board in the same browser session:

  a costing WITH an end user   → "{customer} ({end user})"
  a costing WITHOUT one        → the customer name and NOTHING else — no empty
                                 brackets, no dangling separator, not a stray space

The negative is the one that can regress silently. A conditional suffix that
renders `({undefined})` or a lone `()` still looks roughly right in a screenshot
and reads as fine in a passing "contains the customer name" assertion, so the
no-end-user row is asserted on its cell's EXACT text, not on a substring.

Both rows are seeded straight into the database rather than driven through the
calculator: the summary line reads the end_user_company SNAPSHOT column, and #141
already owns the journey that proves picking an end user fills it in. Repeating
that here would test #141's work, not this cell.

Selector policy (WO v4.26.1 §5): data-testid only.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from _common import role_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "costings_summary_line"
MARK = "J150SL"
FULL_USER = "journey_full_summaryline"     # role 'full' = Nadie

CUSTOMER = f"{MARK} Reseller Ltd"
END_USER = f"{MARK} ACME Foods"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.calculations cal USING icb_costings.customers c "
        "WHERE cal.customer_id = c.id AND c.name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text(
        "DELETE FROM icb_costings.customer_end_users eu USING icb_costings.customers c "
        "WHERE eu.customer_id = c.id AND c.name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


def _result_json() -> str:
    import json
    return json.dumps({
        "items": [], "category_totals": {}, "category_multipliers": {},
        "materials_total": 0.0, "cost_per_sqm": 0.0, "geometry": {},
        "chassis": None, "profit_amount": 0.0, "profit_margin": 0.0,
        "ratio_value": 1.0, "ratio_label": "100%", "ratio_amount": 0.0,
        "grand_total": 0.0, "selling_price": 0.0, "net_total": 0.0,
    })


@pytest.fixture(scope="module")
def staged():
    """One customer, two costings on it: one carrying an end-user snapshot, one not."""
    from app.database import (CalculationRecord, Customer, CustomerEndUser,
                              SessionLocal, User)
    created_user = False
    with SessionLocal() as db:
        _purge(db)
        cust = Customer(name=CUSTOMER, bp_code=f"{MARK}1", is_active=True)
        db.add(cust)
        db.flush()
        eu = CustomerEndUser(customer_id=cust.id, company_name=END_USER,
                             contact_name="Thabo Nkosi", contact_role="Fleet",
                             is_primary=True, active=True)
        db.add(eu)
        db.flush()

        user = db.query(User).filter_by(username=FULL_USER).first()
        if user is None:
            user = User(username=FULL_USER, password_hash="x", role="full")
            db.add(user)
            db.flush()
            created_user = True

        with_eu = CalculationRecord(
            trailer_type_id=None, customer_id=cust.id, user_id=user.id,
            is_repair=True, status="pending", quote_number=f"{MARK}-EU",
            dimensions_json="{}", result_json=_result_json(),
            end_user_id=eu.id, end_user_company=END_USER,
            end_user_contact_name="Thabo Nkosi")
        without_eu = CalculationRecord(
            trailer_type_id=None, customer_id=cust.id, user_id=user.id,
            is_repair=True, status="pending", quote_number=f"{MARK}-NONE",
            dimensions_json="{}", result_json=_result_json())
        db.add_all([with_eu, without_eu])
        db.commit()
        ids = {"with": with_eu.quote_number, "without": without_eu.quote_number}

    yield ids

    with SessionLocal() as db:
        _purge(db)
        if created_user:
            u = db.query(User).filter_by(username=FULL_USER).first()
            if u is not None:
                db.delete(u)
        db.commit()


def _cell(page: Page, quote: str):
    """The customer cell of the row for `quote`. Anchored through the row's own
    quote number so a shared search box or a re-sort cannot hand back the wrong
    row — the two seeded costings sit on the SAME customer."""
    # The two quote numbers are deliberately not prefixes of one another
    # ("-EU" / "-NONE"): has_text is a SUBSTRING match, so "…-WITH" would have
    # matched "…-WITHOUT" as well and quietly returned both rows.
    row = page.locator("[data-testid='costing-row']", has_text=quote)
    expect(row).to_have_count(1, timeout=T)
    return row.locator("[data-testid='costing-customer']")


def test_the_end_user_shows_in_brackets_and_is_absent_when_there_is_none(
        page: Page, live_server: str, staged) -> None:
    role_session(page, FULL_USER, base=live_server)
    page.goto("/mes-app/costings")
    expect(page.locator("[data-testid='costings-table']")).to_be_visible(timeout=T)

    # Search down to the two seeded rows so the assertions do not depend on how
    # many other costings the database happens to hold.
    page.get_by_placeholder("Search customer, contact, quote number, body type…").fill(MARK)

    # 1. WITH an end user — customer, then the end user in brackets.
    with_cell = _cell(page, staged["with"])
    expect(with_cell).to_have_text(f"{CUSTOMER} ({END_USER})", timeout=T)
    # The full value is on the row for the truncated case (narrow screens).
    expect(with_cell).to_have_attribute("title", f"{CUSTOMER} ({END_USER})")

    # 2. WITHOUT one — EXACT text, not a substring: empty brackets, a lone
    #    separator or a trailing space would all pass a `contains` assertion and
    #    all of them are the bug this line exists to prevent.
    without_cell = _cell(page, staged["without"])
    expect(without_cell).to_have_text(CUSTOMER, timeout=T)
    expect(without_cell).to_have_attribute("title", CUSTOMER)

    shot(page, "summary_line_end_user_brackets", JOURNEY)
