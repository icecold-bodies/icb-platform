"""v1.50 — /admin/quote-numbering administers BOTH numbering series.

Before this, the screen edited the body-costing counter only; the repair
R-series (`quote_counter.series='repair_doc'`, migration 0042) had no admin
surface at all and could only be moved with hand-written SQL.

One stateful click-through, in ONE browser context (banked: stateful loops are
one test), covering what a person actually does on the screen:

  * both labelled blocks render, each preloaded from its OWN counter row
  * the repair preview reads like a real R-number
  * a repair template without the "R-" prefix shows the advisory note and
    still saves — the convention is the admin's, the app only mentions it
  * setting the repair next number saves and SURVIVES A RELOAD
  * lowering the next number raises the app.js confirmModal (never a native
    confirm — it is invisible to Playwright and dead inside embeds), and
    Cancel leaves the stored value alone
  * none of it moves the body block
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402

T = 15_000
JOURNEY = "quote_numbering_admin"
REPAIR_TARGET = 4242


@pytest.fixture()
def restore_counters():
    """Both counters are global rows on the shared journey DB — restore them
    exactly, whatever this journey leaves behind."""
    from app.database import SessionLocal
    from app.quote_numbering import (get_or_create_counter,
                                     SERIES_QUOTE, SERIES_REPAIR_DOC)
    before = {}
    with SessionLocal() as db:
        for s in (SERIES_QUOTE, SERIES_REPAIR_DOC):
            qc = get_or_create_counter(db, s)
            before[s] = (int(qc.next_value), qc.format_template)
        db.commit()
    yield before
    with SessionLocal() as db:
        for s, (nv, tpl) in before.items():
            qc = get_or_create_counter(db, s)
            qc.next_value, qc.format_template = nv, tpl
        db.commit()


def test_both_series_are_administered_from_the_one_screen(
        page: Page, live_server, restore_counters) -> None:
    admin_session(page, live_server)
    page.goto("/admin/quote-numbering")

    body_block   = page.get_by_test_id("qn-block-quote")
    repair_block = page.get_by_test_id("qn-block-repair_doc")
    expect(body_block).to_be_visible(timeout=T)
    expect(repair_block).to_be_visible(timeout=T)
    expect(body_block).to_contain_text("Body costing numbers")
    expect(repair_block).to_contain_text("Repair document numbers (R-series)")

    body_tpl_before  = page.get_by_test_id("qn-template-quote").input_value()
    body_next_before = page.get_by_test_id("qn-next-quote").input_value()

    # Both previews must actually RENDER on load. This is the assertion that
    # caught the page's inline api() shadowing app.js's without carrying
    # X-CSRF-Token: the preview POST answered 403 and the preview box read
    # "CSRF token missing" in red instead of a sample number.
    expect(page.locator("#qn-status")).to_have_text("Template OK.", timeout=T)
    expect(page.locator("#qn-status-repair_doc")).to_have_text("Template OK.", timeout=T)
    expect(page.get_by_test_id("qn-preview-quote")).not_to_have_text("…", timeout=T)

    # Each block preloads from its OWN row: the R-series preview is an R-number.
    repair_tpl = page.get_by_test_id("qn-template-repair_doc")
    repair_tpl.fill("R-{counter}")
    expect(page.get_by_test_id("qn-preview-repair_doc")).to_have_text("R-2547", timeout=T)
    # ...and the note stays away while the convention is being kept.
    expect(page.locator("#qn-note-repair_doc")).to_be_hidden()
    shot(page, "01-both-blocks", journey=JOURNEY)

    # v1.50 — the ratified convention is BUILDABLE on the screen: both new
    # placeholders are offered as chips, and the preview reads like the
    # document people already know.
    expect(page.locator("#ph-list code", has_text="{customer}")).to_be_visible(timeout=T)
    expect(page.locator("#ph-list code", has_text="{vehicle_registration}")).to_be_visible()
    repair_tpl.fill("R-{counter} {customer} {vehicle_registration}")
    expect(page.get_by_test_id("qn-preview-repair_doc")).to_have_text(
        "R-2547 ATLANTIC SEAFOODS CA 123-456", timeout=T)
    expect(page.locator("#qn-status-repair_doc")).to_have_text("Template OK.")
    shot(page, "05-convention-template", journey=JOURNEY)
    repair_tpl.fill("R-{counter}")
    expect(page.get_by_test_id("qn-preview-repair_doc")).to_have_text("R-2547", timeout=T)

    # A template that drops the prefix is NOTED, never blocked.
    repair_tpl.fill("REP{counter}")
    expect(page.locator("#qn-note-repair_doc")).to_be_visible(timeout=T)
    expect(page.locator("#qn-note-repair_doc")).to_contain_text('does not start with "R-"')
    page.get_by_test_id("qn-save-repair_doc").click()
    expect(page.locator("#qn-save-status-repair_doc")).to_have_text("Saved.", timeout=T)
    shot(page, "02-prefix-note", journey=JOURNEY)

    # Back to the real convention, and set the next number Michael wants.
    repair_tpl.fill("R-{counter}")
    expect(page.locator("#qn-note-repair_doc")).to_be_hidden(timeout=T)
    page.get_by_test_id("qn-next-repair_doc").fill(str(REPAIR_TARGET))
    page.get_by_test_id("qn-save-repair_doc").click()
    expect(page.locator("#qn-save-status-repair_doc")).to_have_text("Saved.", timeout=T)

    # It PERSISTED — a reload reads it back off the repair row, not off a
    # left-over form value.
    page.reload()
    expect(page.get_by_test_id("qn-next-repair_doc")).to_have_value(str(REPAIR_TARGET), timeout=T)
    expect(page.get_by_test_id("qn-template-repair_doc")).to_have_value("R-{counter}")
    shot(page, "03-repair-saved", journey=JOURNEY)

    # Lowering warns through the app.js modal, and Cancel means cancel.
    page.get_by_test_id("qn-next-repair_doc").fill(str(REPAIR_TARGET - 100))
    page.get_by_test_id("qn-save-repair_doc").click()
    expect(page.locator("#confirm-message")).to_be_visible(timeout=T)
    expect(page.locator("#confirm-message")).to_contain_text("may be reissued")
    shot(page, "04-lowering-warning", journey=JOURNEY)
    page.locator("#confirm-cancel").click()
    expect(page.locator("#qn-save-status-repair_doc")).to_have_text("Cancelled.", timeout=T)

    page.reload()
    expect(page.get_by_test_id("qn-next-repair_doc")).to_have_value(str(REPAIR_TARGET), timeout=T)

    # Through all of that the body block never moved.
    expect(page.get_by_test_id("qn-template-quote")).to_have_value(body_tpl_before)
    expect(page.get_by_test_id("qn-next-quote")).to_have_value(body_next_before)

    from app.database import SessionLocal
    from app.quote_numbering import get_or_create_counter, SERIES_QUOTE
    with SessionLocal() as db:
        qc = get_or_create_counter(db, SERIES_QUOTE)
        assert (int(qc.next_value), qc.format_template) == restore_counters[SERIES_QUOTE], \
            "administering the R-series moved the body counter"
        db.commit()
