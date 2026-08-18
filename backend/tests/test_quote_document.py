"""v1.47 Lane D — the ICB quotation document's money, line grammar and paging.

These are the parts worth pinning independently of any PDF: if carry-over or the
VAT block is wrong, the document is wrong no matter how it draws. Asserting them
here means a failure names the arithmetic rather than "the PDF changed".

Reference figures are the sample quote's own
(`231034795 Atlantic Seafoods - Ridhwan - LT 15 FB GP.pdf`):
    Total before Discount  52 270,00
    Discount Subtotal           0,00  0.00%
    Total Before Tax       52 270,00
    Total Tax Amount        7 840,50   (15 %)
    Total Amount (Incl)    60 110,50
"""
import pytest

from app.services.quote_document import (
    LABEL_TOTAL_BEFORE_DISCOUNT, LABEL_DISCOUNT_SUBTOTAL, LABEL_TOTAL_BEFORE_TAX,
    LABEL_TOTAL_TAX, LABEL_TOTAL_INCL_VAT,
    carry_over_for, document_lines, lines_total, money, paginate_lines,
    totals_block,
)


# ── the sample's own arithmetic ──────────────────────────────────────────────

def test_the_totals_block_reproduces_the_sample_quote():
    rows = totals_block({"selling_price": 52270.00, "discount_amount": 0.0,
                         "net_total": 52270.00}, rate_pct=15.0)
    assert [r["label"] for r in rows] == [
        LABEL_TOTAL_BEFORE_DISCOUNT, LABEL_DISCOUNT_SUBTOTAL,
        LABEL_TOTAL_BEFORE_TAX, LABEL_TOTAL_TAX, LABEL_TOTAL_INCL_VAT,
    ], "the totals block must print in the sample's order"
    amounts = [r["amount"] for r in rows]
    assert amounts[0] == pytest.approx(52270.00)
    assert amounts[1] == pytest.approx(0.0)
    assert amounts[2] == pytest.approx(52270.00)
    assert amounts[3] == pytest.approx(7840.50), "15% VAT on 52 270,00"
    assert amounts[4] == pytest.approx(60110.50)
    assert money(amounts[4]) == "60,110.50", "the document's money format"


def test_vat_is_added_not_extracted_and_follows_the_configured_rate():
    """Prices are quoted EXCLUSIVE of VAT — the terms page says so."""
    at15 = totals_block({"selling_price": 1000.0, "net_total": 1000.0}, rate_pct=15.0)
    assert at15[3]["amount"] == pytest.approx(150.0)
    assert at15[4]["amount"] == pytest.approx(1150.0)
    # A changed rate flows straight through — the renderer never hardcodes it.
    at20 = totals_block({"selling_price": 1000.0, "net_total": 1000.0}, rate_pct=20.0)
    assert at20[3]["amount"] == pytest.approx(200.0)
    assert at20[4]["amount"] == pytest.approx(1200.0)


def test_a_discount_lands_between_gross_and_tax():
    rows = totals_block({"selling_price": 1000.0, "discount_amount": 100.0,
                         "net_total": 900.0, "discount_kind": "percent",
                         "discount_input": 10}, rate_pct=15.0)
    assert rows[0]["amount"] == pytest.approx(1000.0)
    assert rows[1]["amount"] == pytest.approx(100.0)
    assert rows[1]["note"] == "10.00%", "the sample prints the % beside the discount"
    assert rows[2]["amount"] == pytest.approx(900.0), "tax is charged on the NET"
    assert rows[3]["amount"] == pytest.approx(135.0)
    assert rows[4]["amount"] == pytest.approx(1035.0)


# ── D3 line grammar ──────────────────────────────────────────────────────────

def test_lump_sum_lines_print_blank_qty_and_price_cells():
    """Every line in the reference quote is a long description with a total and
    nothing else. Those cells must be EMPTY — never 0, never the carrier 1."""
    result = {"items": [
        {"material": "Remove nose cone and scrap.", "quantity": 1.0,
         "unit_price": 280.0, "line_cost": 280.0, "total_only": True},
        {"material": "Rubber seal kit", "quantity": 2.0,
         "unit_price": 450.0, "line_cost": 900.0},
    ]}
    lines = document_lines(result)
    assert lines[0]["qty"] is None and lines[0]["price"] is None
    assert lines[0]["total"] == pytest.approx(280.0)
    # A priced line still shows both.
    assert lines[1]["qty"] == pytest.approx(2.0)
    assert lines[1]["price"] == pytest.approx(450.0)
    assert lines[1]["total"] == pytest.approx(900.0)


def test_excluded_lines_never_reach_the_document():
    result = {"items": [
        {"material": "In", "line_cost": 100.0},
        {"material": "Out", "line_cost": 999.0, "excluded": True},
    ]}
    lines = document_lines(result)
    assert [l["description"] for l in lines] == ["In"]
    assert lines_total(lines) == pytest.approx(100.0)


# ── D5 pagination + carry over ───────────────────────────────────────────────

def _line(total, h=10.0):
    return {"description": "x", "total": total, "_h": h}


def test_carry_over_is_the_running_total_at_each_page_foot():
    """The sample prints "Carry Over: 52,270.00" at the foot of page 1 and again
    at the head of page 2, so entry i is the figure for the break after page i."""
    pages = [[_line(100.0), _line(200.0)], [_line(50.0)], [_line(25.0)]]
    assert carry_over_for(pages) == [300.0, 350.0, 375.0]


def test_a_long_quote_paginates_and_every_break_carries_the_right_total():
    """A 3+ page document — the addendum asks for exactly this shape."""
    lines = [_line(100.0) for _ in range(30)]
    # Page 1 is shorter: it carries the letterhead and the header block.
    pages = paginate_lines(lines,
                           capacity_for_page=lambda i: 100.0 if i == 0 else 150.0,
                           height_of=lambda l: l["_h"])
    assert len(pages) >= 3, f"expected 3+ pages, got {len(pages)}"
    assert [len(p) for p in pages][0] == 10, "page 1 fits ten 10-unit rows in 100"
    assert sum(len(p) for p in pages) == 30, "no line may be dropped or duplicated"
    carries = carry_over_for(pages)
    assert carries[-1] == pytest.approx(3000.0), "the last carry is the full total"
    # Every break continues from exactly where the previous page stopped.
    running = 0.0
    for page, carry in zip(pages, carries):
        running += sum(l["total"] for l in page)
        assert carry == pytest.approx(running)


def test_pagination_never_loops_on_a_line_taller_than_a_page():
    """An over-tall row is placed and allowed to overflow visibly — a hang would
    be far worse, and silently dropping it worse still."""
    lines = [_line(10.0, h=500.0), _line(20.0, h=10.0)]
    pages = paginate_lines(lines, capacity_for_page=lambda i: 100.0,
                           height_of=lambda l: l["_h"])
    assert sum(len(p) for p in pages) == 2
    assert carry_over_for(pages)[-1] == pytest.approx(30.0)


# ── the rendered artefact (D5 end to end) ────────────────────────────────────

def _long_ctx(n_lines: int, per_line: float = 1000.0):
    from app.services.quote_document import document_lines, lines_total, totals_block
    from app.services.quote_document_config import DEFAULT_CONFIG
    items = [{"material": f"{i:02d}. Remove and replace the damaged section, dress "
                          f"the edges, laminate the joints and make good to a "
                          f"matching finish throughout.",
              "quantity": 1.0, "unit_price": per_line, "line_cost": per_line,
              "total_only": True} for i in range(1, n_lines + 1)]
    gross = per_line * n_lines
    result = {"items": items, "grand_total": gross, "selling_price": gross,
              "discount_amount": 0.0, "net_total": gross}
    lines = document_lines(result)
    return {
        "config": DEFAULT_CONFIG, "document_number": "R-000123",
        "document_date": "18-08-2026", "title": "Repair Quotation",
        "original_label": "Original", "customer_name": "Long Quote Ltd",
        "customer_vat": "477 026 7526", "customer_tel": "011 000 0000",
        "customer_email": "a@b.co.za", "your_reference": "Veh reg nr:  ABC 123 GP",
        "delivery_address": "1 Road\nCity", "your_contact": "Nadie",
        "your_contact_phone": "082 000 0000", "payment_terms": "COD",
        "job_note": "", "lines": lines, "lines_total": lines_total(lines),
        "totals": totals_block(result, rate_pct=15.0), "vat_rate_pct": 15.0,
    }, gross


def _page_texts(pdf_bytes):
    from io import BytesIO
    from pypdf import PdfReader
    return [(p.extract_text() or "") for p in PdfReader(BytesIO(pdf_bytes)).pages]


def test_a_long_quote_renders_multi_page_with_carry_over_on_every_break():
    """The addendum asks for a 3+ page quote with Carry Over at the foot of each
    continuing page and again at the head of the next — the sample's own shape."""
    from app.services.quote_document_pdf import render_repair_quote_pdf
    ctx, gross = _long_ctx(45)
    texts = _page_texts(render_repair_quote_pdf(ctx))
    assert len(texts) >= 3, f"expected a multi-page quote, got {len(texts)}"

    line_pages = [t for t in texts if "Description" in t or "Carry Over" in t]
    assert len(line_pages) >= 2, "45 long lines should not fit on one page"
    # Every page except the last line-page carries the running total forward,
    # and the page after it repeats that same figure at its head.
    for i in range(len(line_pages) - 1):
        assert "Carry Over" in line_pages[i], f"page {i+1} does not carry over"
        assert "Carry Over" in line_pages[i + 1], f"page {i+2} does not continue"

    # The totals block appears ONCE, on the last page of lines, and ends on the
    # VAT-inclusive figure.
    assert sum("Total Amount" in t for t in texts) == 1
    body = [t for t in texts if "Total Amount" in t][0]
    assert "Total Before Tax" in body and "Total Tax Amount" in body
    assert f"{gross:,.2f}" in body, "the pre-tax total must be the sum of the lines"
    assert f"{gross * 1.15:,.2f}" in body, "the VAT-inclusive total must be printed"


def test_the_shell_puts_the_house_furniture_on_every_page():
    """Letterhead on page 1, the continuation header on later pages, and the
    banking footer plus n/m on all of them (D1/D5)."""
    from app.services.quote_document_pdf import render_repair_quote_pdf
    ctx, _ = _long_ctx(45)
    texts = _page_texts(render_repair_quote_pdf(ctx))
    total = len(texts)
    for i, t in enumerate(texts, start=1):
        assert "BANKING DETAILS" in t, f"page {i} lost the banking footer"
        assert "Capitec Business" in t, f"page {i} lost the banking details"
        assert f"Page {i}/{total}" in t, f"page {i} is not numbered n/m"
    for t in texts[1:]:
        assert "Repair Quotation" in t, "a continuation page lost its header"
        assert "R-000123" in t, "a continuation page lost the document number"


def test_the_terms_and_acceptance_pages_come_from_the_editable_config():
    """D7 — the renderer prints whatever the config holds, so an admin edit
    reaches the document without a code change."""
    from copy import deepcopy
    from app.services.quote_document_config import DEFAULT_CONFIG
    from app.services.quote_document_pdf import render_repair_quote_pdf
    ctx, _ = _long_ctx(3)
    texts = _page_texts(render_repair_quote_pdf(ctx))
    joined = "\n".join(texts)
    assert "VALIDITY:" in joined and "thirty (30) days" in joined
    assert "WARRANTY:" in joined and "six (6) months" in joined
    assert "Quote Acceptance form" in joined
    assert "R-000123" in joined, "the acceptance form must quote the document number"

    edited = deepcopy(DEFAULT_CONFIG)
    edited["terms"]["blocks"][0]["body"] = "The validity period on this quote is NINETY (90) days."
    ctx2, _ = _long_ctx(3)
    ctx2["config"] = edited
    joined2 = "\n".join(_page_texts(render_repair_quote_pdf(ctx2)))
    assert "NINETY (90) days" in joined2, "an edited term did not reach the document"
    assert "thirty (30) days" not in joined2
