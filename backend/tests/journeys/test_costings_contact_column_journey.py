"""Nadie WO (16 Jul) — Contact column on the costings dashboard (journey).

Real browser over two seeded costing rows: the table gains a "Contact" column
between Customer and Body type; a post-v1.40.5 row shows its attention-of
snapshot (contact_name), a pre-snapshot row renders BLANK (no placeholder).
Column POSITION is asserted by header index so a reorder regression fails loudly.

Rows are seeded directly (the /api/approve pipeline needs the full BOM universe
the test DB doesn't have — test_calculation_contact_api.py precedent); marker
rows NCFJ* purged both sides.
"""
from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402

T = 20_000
JOURNEY = "costings_contact_column"
MARK = "NCFJ"


def _purge():
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        for r in db.query(CalculationRecord).filter(
                CalculationRecord.quote_number.like(f"{MARK}%")).all():
            db.delete(r)
        db.commit()


@pytest.fixture()
def seeded_rows():
    from app.database import CalculationRecord, SessionLocal
    _purge()
    q_with = f"{MARK}{uuid.uuid4().hex[:5].upper()}A"
    q_blank = f"{MARK}{uuid.uuid4().hex[:5].upper()}B"
    with SessionLocal() as db:
        db.add(CalculationRecord(
            quote_number=q_with, dimensions_json="{}",
            result_json='{"items": []}', status="pending",
            contact_name="NCFJ Piet Venter", contact_role="Buyer"))
        db.add(CalculationRecord(
            quote_number=q_blank, dimensions_json="{}",
            result_json='{"items": []}', status="pending"))
        db.commit()
    yield {"with": q_with, "blank": q_blank}
    _purge()


def test_contact_column_renders_between_customer_and_body_type(page: Page, seeded_rows) -> None:
    admin_session(page)
    page.goto("/mes-app/costings")
    table = page.get_by_test_id("costings-table")
    expect(table).to_be_visible(timeout=T)

    # Header position pin: [checkbox] Quote # · Customer · Contact · Body type · …
    headers = table.locator("thead th").all_inner_texts()
    assert headers[1] == "Quote #" and headers[2] == "Customer", f"unexpected header order: {headers}"
    assert headers[3] == "Contact", f"Contact must sit after Customer: {headers}"
    assert headers[4] == "Body type", f"Body type must follow Contact: {headers}"

    # Snapshot row shows the attention-of name in the Contact cell (index 3)…
    row_with = page.locator("tr", has_text=seeded_rows["with"]).first
    expect(row_with).to_be_visible(timeout=T)
    expect(row_with.locator("td").nth(3)).to_have_text("NCFJ Piet Venter")

    # …and a pre-v1.40.5 row (contact_name NULL) renders BLANK — no placeholder.
    row_blank = page.locator("tr", has_text=seeded_rows["blank"]).first
    expect(row_blank).to_be_visible(timeout=T)
    expect(row_blank.locator("td").nth(3)).to_have_text("")

    shot(page, "01-contact-column", journey=JOURNEY)
