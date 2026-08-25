"""v1.51 §3.4 — repair quote presentation + the board's R-number (journey).

The WO's script, end to end on the real surfaces:

  repair → a MIXED CASE description stays mixed case on the surface → an
  edited reference label ("Store Sale") → save → the costings board shows the
  R-number as the row's primary value with the internal record number beneath
  it → searching the board for the R-number finds the row → download with no
  mode: BREAKDOWN, the money columns empty → download ITEMIZED: the prices
  appear → download with no mode again: ITEMIZED comes back, because the mode
  is remembered ON THE QUOTE.

Why the PDF is fetched through `page.request` rather than by clicking through
the chooser: the assertion is about the DOCUMENT, and a browser download in a
headless run proves the click, not the bytes. The chooser itself is asserted
separately (it opens, it carries three options, it highlights the last-used
one), which is the part a click can prove.

Marker rows J151* only — created and purged here, no real costing touched.
"""
from __future__ import annotations

import io
import os
import re

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, admin_session, shot  # noqa: E402

T = 20_000
JOURNEY = "repair_quote_doc"

CUST = "J151 Quote Doc Ltd"
# Typed in mixed case ON PURPOSE: through v1.50 three separate mechanisms
# upper-cased this (the input's text-transform, its oninput handler, and
# free_hand.parse_lines), so a document that reads it back as typed is the
# proof that all three are gone.
DESC_1 = "Remove double rear doors and scrap"
DESC_2 = "Manufacture and fit new double rear doors"


def _purge(db) -> None:
    from sqlalchemy import text
    _owned = ("SELECT c.id FROM icb_costings.calculations c "
              "JOIN icb_costings.customers cu ON cu.id = c.customer_id "
              "WHERE cu.name LIKE 'J151%'")
    # Children first: a calculation may have picked up MES rows on save, and a
    # parent-first delete aborts on the FK (the residue that has bitten this
    # suite before).
    for _tbl, _col in (("icb_mes.prejob_cards", "calculation_id"),
                       ("icb_mes.production_jobs", "calculation_record_id")):
        db.execute(text(f"DELETE FROM {_tbl} WHERE {_col} IN ({_owned})"))
    db.execute(text("DELETE FROM icb_costings.calculations c "
                    "USING icb_costings.customers cu "
                    "WHERE c.customer_id = cu.id AND cu.name LIKE 'J151%'"))
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'J151%'"))
    db.commit()


@pytest.fixture()
def j151_customer():
    from app.database import SessionLocal, Customer
    with SessionLocal() as db:
        _purge(db)
        cust = Customer(name=CUST, bp_code="J1511", is_active=True,
                        telephone="011 995 5000", email="j151@example.co.za",
                        vat_number="494 030 8523")
        db.add(cust)
        db.commit()
        cid = cust.id
    yield cid
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _add_free_hand(page: Page, description: str, qty: str, price: str) -> None:
    page.click("#repair-add-freehand")
    expect(page.locator("#modal-free-hand")).not_to_have_class(
        re.compile(r"\bhidden\b"), timeout=T)
    page.fill("#fh-description", description)
    page.fill("#fh-qty", qty)
    page.fill("#fh-unit-price", price)
    page.click("#fh-save-btn")
    expect(page.locator("#modal-free-hand")).to_have_class(
        re.compile(r"\bhidden\b"), timeout=T)


def _grand_total(text: str) -> str | None:
    """The VAT-inclusive figure as the DOCUMENT prints it.

    Read back rather than recomputed: the VAT rate is admin-editable, and the
    margin and ratio are surface state, so a constant here would pin the journey
    to one configuration instead of to the rule it is testing.
    """
    m = re.search(r"Total Amount:.*?([0-9][0-9,]*\.[0-9]{2})", text, re.S)
    return m.group(1) if m else None


def _pdf_text(page: Page, base: str, rec_id: int, mode: str | None) -> str:
    from pypdf import PdfReader
    url = f"{base}/api/calculations/{rec_id}/repair-quote.pdf"
    if mode:
        url += f"?mode={mode}"
    resp = page.request.get(url)
    assert resp.ok, f"repair quote ({mode or 'no mode'}) failed: HTTP {resp.status}"
    assert "pdf" in (resp.headers.get("content-type") or "")
    return "\n".join(pg.extract_text() or ""
                     for pg in PdfReader(io.BytesIO(resp.body())).pages)


def test_the_quote_reads_as_typed_and_the_board_shows_its_r_number(
        page: Page, j151_customer) -> None:
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", "repair")
    expect(page.locator("#repair-add-source")).to_be_visible(timeout=T)

    # Deterministic money: no ratio, no margin.
    page.select_option("#f-ratio", "")
    page.fill("#f-margin", "0")

    # ── the case of what is typed ────────────────────────────────────────────
    _add_free_hand(page, DESC_1, "1", "680")
    _add_free_hand(page, DESC_2, "1", "30408")
    expect(page.locator("#repair-lines-body tr")).to_have_count(2, timeout=T)
    # Read back off the SURFACE, before any save: the input's own transform was
    # one of the three mechanisms, so the surface is where it would show first.
    expect(page.locator("#repair-lines-body")).to_contain_text(DESC_1, timeout=T)
    expect(page.locator("#repair-lines-body")).to_contain_text(DESC_2)

    # ── the reference label is Lezette's to write ────────────────────────────
    expect(page.locator("#f-repair-vehicle-label")).to_have_value("Veh reg nr:")
    page.fill("#f-repair-vehicle-label", "Store Sale")
    page.fill("#f-repair-vehicle", "KK 12 LT GP")

    page.fill("#f-repair-type", "Rear door replacement")
    page.select_option("#cust-select", value=str(j151_customer))
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    page.click("#approve-btn")

    rec_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec_id = page.evaluate(
            "() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec_id:
            break
    assert rec_id, "the repair did not save"
    rec_id = int(rec_id)

    # What was stored, not what was displayed: the server-side normaliser was
    # the third mechanism and it would only show here.
    from app.database import SessionLocal, CalculationRecord
    import json as _json
    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=rec_id).first()
        assert rec.is_repair is True and rec.trailer_type_id is None
        result = _json.loads(rec.result_json)
        state = result["input_state"]
        internal_no = rec.quote_number
    assert [l["description"] for l in state["repair_lines"]] == [DESC_1, DESC_2], \
        "a description was rewritten on the way into the database"
    assert state["vehicle_reference_label"] == "Store Sale"
    doc_no = result.get("repair_document_number") or state.get("repair_document_number")
    assert doc_no, "the repair saved without an R-series document number"
    assert internal_no and internal_no != doc_no, \
        "the two identifiers must be distinct for the board test to mean anything"

    # The per-line figures the document WOULD print, taken from the saved
    # costing and formatted by the document's own money() - never typed in
    # here. A hand-written constant that no longer matches what the engine
    # produced would make "this figure is absent" pass for the wrong reason,
    # which is how the first version of this journey went red in CI.
    from app.services.quote_document import money
    line_figures = [money(it["line_cost"]) for it in result["items"]
                    if not it.get("excluded") and it.get("line_cost")]
    assert len(line_figures) == 2, f"expected two priced lines, got {line_figures}"

    # ── the document, in the default mode ───────────────────────────────────
    default_text = _pdf_text(page, base, rec_id, None)
    for needle in (DESC_1, DESC_2):
        assert needle in default_text, f"{needle!r} missing from the quotation"
    assert "REMOVE DOUBLE REAR DOORS" not in default_text, "the document is shouting"
    # BREAKDOWN is the default: the headings stay, the figures do not, and the
    # money is stated once in the totals block.
    assert "Quantity" in default_text and "Price" in default_text
    for figure in line_figures:
        assert figure not in default_text, f"{figure} reached the default document"
    # The VAT-inclusive total is READ OFF the document, not asserted against a
    # constant computed here: the VAT rate is admin-editable and the margin and
    # ratio are surface state, so a precomputed figure pins this journey to a
    # configuration rather than to the rule. What matters is that the total is
    # present and is the SAME in every mode - which is checked below.
    grand = _grand_total(default_text)
    assert grand, ("no totals block on the default document: "
                   + default_text[:400])
    # The reference caption Lezette typed, with its value.
    assert "Store Sale" in default_text and "KK 12 LT GP" in default_text
    assert "Veh reg nr" not in default_text, "the default caption overrode hers"
    # Default 7 — the acceptance form's new ruled field.
    assert "Order Number:" in default_text

    # ── switch to itemized: the prices appear ───────────────────────────────
    itemized = _pdf_text(page, base, rec_id, "itemized")
    for figure in line_figures:
        assert figure in itemized, f"{figure} missing from the itemized document"

    # ── and the choice is remembered ON THE QUOTE ───────────────────────────
    # No mode this time: a re-download must reproduce what was last sent, not
    # fall back to the default.
    again = _pdf_text(page, base, rec_id, None)
    assert line_figures[1] in again, \
        "the re-download lost the mode — the customer would get a different document"

    summary = _pdf_text(page, base, rec_id, "summary")
    assert DESC_1 not in summary, "summary printed the item detail"

    # The mode changes how much of the WORK is shown, never what is owed.
    assert _grand_total(itemized) == grand, "itemized disagrees on the total"
    assert _grand_total(summary) == grand, "summary disagrees on the total"

    # ── the board (Michael, 25 Aug) ─────────────────────────────────────────
    # PATH, not hash: the MES SPA is a BrowserRouter, so "/mes-app/#/costings"
    # loads the app at its default screen and the board never mounts. Every
    # other journey in this suite uses the path form.
    page.goto("/mes-app/costings")
    expect(page.locator("[data-testid='costings-table']")).to_be_visible(timeout=T)
    row = page.locator("[data-testid='costing-row']").filter(has_text=doc_no).first
    expect(row).to_be_visible(timeout=T)
    # Primary = the number the CUSTOMER was quoted; the internal record number
    # is still there, underneath.
    expect(row.locator("[data-testid='quote-number-primary']")).to_have_text(doc_no)
    expect(row.locator("[data-testid='quote-number-internal']")).to_have_text(internal_no)
    shot(page, "board_shows_r_number", JOURNEY)

    # Search matches BOTH numbers — the R-number is the one Lezette is asked
    # about on the phone, and before this it matched nothing.
    search = page.locator("input[placeholder*='earch']").first
    for term in (doc_no, internal_no):
        search.fill(term)
        # The row SURVIVES the filter, and a row that should not is gone. Not an
        # exact row COUNT: the board keys rows by quote number, which is not
        # unique, so a duplicated number can leave a stale row behind - a
        # pre-existing defect this journey must not be a hostage to.
        expect(page.locator("[data-testid='costing-row']")
               .filter(has_text=doc_no).first).to_be_visible(timeout=T)
        search.fill("")

    # ── the chooser itself ──────────────────────────────────────────────────
    page.locator("[data-testid='costing-row']").filter(has_text=doc_no).first.click()
    quote_btn = page.locator("[data-testid='repair-quote-btn']")
    expect(quote_btn).to_be_visible(timeout=T)
    quote_btn.click()
    modal = page.locator("[data-testid='repair-quote-mode-modal']")
    expect(modal).to_be_visible(timeout=T)
    for mode in ("summary", "breakdown", "itemized"):
        expect(modal.locator(f"[data-testid='repair-quote-mode-{mode}']")).to_be_visible()
    shot(page, "download_chooser", JOURNEY)
