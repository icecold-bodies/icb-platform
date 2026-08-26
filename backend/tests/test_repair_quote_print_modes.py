"""v1.51 — the repair quotation's three print modes, and what each one shows.

Lezette test-drove R-2001/R-2002 on prod against the old system's R-231037388
(Karan Beef, 17-06-2026) and the gap was not the numbers. The old document
prints the WORK — every line described, the three money columns EMPTY, the price
stated once in the totals block. The MES document printed the full costing
breakdown. So the amount of detail became a choice made at download time, and
these tests pin what each choice produces.

The arithmetic lives in test_quote_document.py; what is pinned here is which
CELLS carry a figure, which is the whole of Lezette's complaint.
"""
import json

import pytest

from app.services.quote_document import (
    DEFAULT_PRINT_MODE, DEFAULT_REFERENCE_LABEL, PRINT_MODES,
    PRINT_MODE_BREAKDOWN, PRINT_MODE_ITEMIZED, PRINT_MODE_SUMMARY,
    document_lines, normalize_print_mode, stored_print_mode,
    totals_block, vehicle_reference_label,
)

# Two sections and a lump sum — enough for SUMMARY to have something to group,
# and for BREAKDOWN to have a priced line whose price must still be hidden.
RESULT = {
    "repair_type": "Body repair",
    "selling_price": 31088.00, "discount_amount": 0.0, "net_total": 31088.00,
    "items": [
        {"material": "Remove double rear doors and scrap", "category": "REAR DOORS",
         "quantity": 1.0, "unit_price": 680.0, "line_cost": 680.0},
        {"material": "Manufacture and fit new double rear doors", "category": "REAR DOORS",
         "quantity": 1.0, "unit_price": 30408.0, "line_cost": 30408.0},
        {"material": "Touch up paint on worked areas.", "category": "REPAIR LINES",
         "total_only": True, "quantity": 1.0, "unit_price": 0.0, "line_cost": 0.0},
    ],
}


# ── the default is the old system's shape ────────────────────────────────────

def test_the_default_mode_is_breakdown():
    """Ratified 25 Aug: the document most quotes go out as is the one that
    reproduces what ICB's customers already receive."""
    assert DEFAULT_PRINT_MODE == PRINT_MODE_BREAKDOWN
    assert document_lines(RESULT) == document_lines(RESULT, PRINT_MODE_BREAKDOWN)


def test_breakdown_describes_every_line_and_prices_none_of_them():
    lines = document_lines(RESULT, PRINT_MODE_BREAKDOWN)
    assert [l["description"] for l in lines] == [
        "Remove double rear doors and scrap",
        "Manufacture and fit new double rear doors",
        "Touch up paint on worked areas.",
    ], "every line is still described — this is not the summary"
    for l in lines:
        # All THREE money columns, not just qty/price: a line total in a document
        # whose other columns are blank is exactly the pricing detail the mode
        # exists to withhold.
        assert l["qty"] is None and l["price"] is None and l["total"] is None


def test_itemized_is_the_pre_v1_51_document_unchanged():
    lines = document_lines(RESULT, PRINT_MODE_ITEMIZED)
    assert lines[0]["qty"] == pytest.approx(1.0)
    assert lines[0]["price"] == pytest.approx(680.0)
    assert lines[0]["total"] == pytest.approx(680.0)
    # A lump-sum line keeps its D3 grammar even here.
    assert lines[2]["qty"] is None and lines[2]["price"] is None
    assert lines[2]["total"] == pytest.approx(0.0)


# ── summary ──────────────────────────────────────────────────────────────────

def test_summary_is_one_line_per_section_in_first_appearance_order():
    lines = document_lines(RESULT, PRINT_MODE_SUMMARY)
    assert [l["description"] for l in lines] == ["REAR DOORS", "Body repair"]
    for l in lines:
        assert l["qty"] is None and l["price"] is None and l["total"] is None


def test_summary_never_prints_the_internal_section_name_to_a_customer():
    """"REPAIR LINES" is the repair surface's own default section. It means
    "typed by hand", which is not a thing to tell a customer — so a group under
    it takes the TYPE OF REPAIR instead."""
    lines = document_lines(
        {"repair_type": "Insulation repair",
         "items": [{"material": "x", "category": "REPAIR LINES", "line_cost": 1.0}]},
        PRINT_MODE_SUMMARY)
    assert [l["description"] for l in lines] == ["Insulation repair"]


def test_summary_falls_back_to_a_phrase_when_there_is_no_type_either():
    lines = document_lines(
        {"items": [{"material": "x", "category": "", "line_cost": 1.0}]},
        PRINT_MODE_SUMMARY)
    assert [l["description"] for l in lines] == ["Repair work"]


def test_the_totals_block_is_identical_in_all_three_modes():
    """The mode changes how much of the WORK is shown, never what is owed. The
    totals come off the costing, not off the printed rows, so blanking the line
    column cannot quietly blank the invoice."""
    ref = totals_block(RESULT, rate_pct=15.0)
    assert ref[-1]["amount"] == pytest.approx(35751.20)
    for mode in PRINT_MODES:
        # document_lines is the only thing the mode touches; totals_block does
        # not take one, and this asserts it stays that way.
        assert totals_block(RESULT, rate_pct=15.0) == ref, mode


# ── the mode is remembered on the quote ──────────────────────────────────────

@pytest.mark.parametrize("raw", ["", None, "nonsense", "SUMMARY ", 7, [], "  "])
def test_an_unreadable_mode_defaults_rather_than_raising(raw):
    """A formatting preference must never be able to take the quotation away."""
    out = normalize_print_mode(raw)
    assert out in PRINT_MODES
    if str(raw).strip().lower() in PRINT_MODES:
        assert out == str(raw).strip().lower()
    else:
        assert out == DEFAULT_PRINT_MODE


def test_a_mode_is_read_back_from_either_place_it_may_be_stored():
    assert stored_print_mode({"repair_quote_print_mode": "itemized"}) == "itemized"
    assert stored_print_mode(
        {"input_state": {"repair_quote_print_mode": "summary"}}) == "summary"
    assert stored_print_mode({}) == DEFAULT_PRINT_MODE


# ── the Your Reference caption ───────────────────────────────────────────────

def test_the_reference_label_defaults_for_every_quote_written_before_it_existed():
    assert vehicle_reference_label({}) == DEFAULT_REFERENCE_LABEL == "Veh reg nr:"
    assert vehicle_reference_label({"vehicle_reference_label": None}) == "Veh reg nr:"
    assert vehicle_reference_label({"vehicle_reference_label": "   "}) == "Veh reg nr:"


@pytest.mark.parametrize("typed", ["Store Sale", "Parts Supply", "Serial nr:"])
def test_the_reference_label_is_whatever_lezette_types(typed):
    assert vehicle_reference_label({"vehicle_reference_label": typed}) == typed


def test_the_reference_label_cannot_grow_past_its_column():
    out = vehicle_reference_label({"vehicle_reference_label": "L" * 500})
    assert len(out) == 40


# ── what actually reaches the page ───────────────────────────────────────────
#
# The mode decides the DATA above; these render it, because "the cell is empty"
# is a claim about the document, and document_lines returning None only proves
# the renderer was told to print nothing — not that it did.

from app.services.quote_document_config import DEFAULT_CONFIG   # noqa: E402


def _ctx(mode, **over):
    from app.services.quote_document import lines_total
    lines = document_lines(RESULT, mode)
    ctx = {
        "config": DEFAULT_CONFIG, "print_mode": mode,
        "document_number": "R-2002", "document_date": "25-08-2026",
        "title": "Repair Quotation", "original_label": "Original",
        "customer_name": "Karan Beef Farming (Pty) Ltd",
        "customer_vat": "494 030 8523", "customer_tel": "011 995 5000",
        "customer_email": "marius@example.co.za",
        "your_reference_label": DEFAULT_REFERENCE_LABEL,
        "your_reference": f"{DEFAULT_REFERENCE_LABEL}  KK 12 LT GP",
        "delivery_address": "Farm Elandsfontein\nHeidelberg",
        "your_contact": "Lezette", "your_contact_phone": "073 916 5891",
        "payment_terms": "COD", "job_note": "", "repair_type": "Body repair",
        "lines": lines, "lines_total": lines_total(lines),
        "totals": totals_block(RESULT, rate_pct=15.0), "vat_rate_pct": 15.0,
    }
    ctx.update(over)
    return ctx


def _pages(ctx):
    from io import BytesIO
    from pypdf import PdfReader
    from app.services.quote_document_pdf import render_repair_quote_pdf
    return [(p.extract_text() or "")
            for p in PdfReader(BytesIO(render_repair_quote_pdf(ctx))).pages]


@pytest.mark.parametrize("mode", [PRINT_MODE_BREAKDOWN, PRINT_MODE_SUMMARY])
def test_the_money_columns_are_empty_on_the_page_not_just_in_the_data(mode):
    """The old system's own quote: Description | Quantity | Price | Total, with
    the three price columns blank on the client copy and the money stated once,
    in the totals block. The HEADINGS stay — they are part of the shape ICB's
    customers recognise — so this asserts the heading is present and the figures
    are not."""
    page1 = _pages(_ctx(mode))[0]
    assert "Quantity" in page1 and "Price" in page1, "the column headings stay"
    for figure in ("680.00", "30,408.00"):
        assert figure not in page1, f"{figure} reached a {mode} document"
    # ...while the totals block still states what is owed, once.
    assert "35,751.20" in page1
    assert page1.count("31,088.00") == 2, "gross and net, in the totals block only"


def test_itemized_still_prints_every_figure():
    page1 = _pages(_ctx(PRINT_MODE_ITEMIZED))[0]
    for figure in ("680.00", "30,408.00", "35,751.20"):
        assert figure in page1


@pytest.mark.parametrize("mode", [PRINT_MODE_BREAKDOWN, PRINT_MODE_SUMMARY])
def test_a_long_quote_carries_no_carry_over_bar_when_it_prints_no_money(mode):
    """A Carry Over bar states a running total OF THE LINE COLUMN. Where that
    column is deliberately blank the bar would announce a figure the page does
    not show — so it belongs to ITEMIZED alone."""
    long_result = dict(RESULT, items=[
        {"material": f"Repair item number {i} with a description long enough to "
                     f"wrap onto a second line and push the page along", 
         "category": "REAR DOORS", "quantity": 1.0, "unit_price": 100.0,
         "line_cost": 100.0}
        for i in range(60)])
    from app.services.quote_document import lines_total
    lines = document_lines(long_result, mode)
    ctx = _ctx(mode, lines=lines, lines_total=lines_total(lines))
    texts = _pages(ctx)
    assert not any("Carry Over" in t for t in texts), f"{mode} printed a carry over"


def test_itemized_still_carries_over_across_pages():
    long_result = dict(RESULT, items=[
        {"material": f"Repair item number {i} with a description long enough to "
                     f"wrap onto a second line and push the page along",
         "category": "REAR DOORS", "quantity": 1.0, "unit_price": 100.0,
         "line_cost": 100.0}
        for i in range(60)])
    from app.services.quote_document import lines_total
    lines = document_lines(long_result, PRINT_MODE_ITEMIZED)
    texts = _pages(_ctx(PRINT_MODE_ITEMIZED, lines=lines,
                        lines_total=lines_total(lines)))
    assert sum("Carry Over" in t for t in texts) >= 2


# ── default 6: the header can never collide, whatever the value ──────────────

def test_a_60_character_document_number_never_reaches_the_document_date():
    """R-2002 shipped with the number and the date overprinting each other,
    because a templated number was three times its column wide and nothing
    measured it. The value now wraps or ellipsises inside its own column."""
    long_no = "R-2002 Karan Beef Farming (Pty) Ltd KK 12 LT GP EXTRA LONG 60"
    assert len(long_no) >= 60
    page1 = _pages(_ctx(PRINT_MODE_ITEMIZED, document_number=long_no))[0]
    # The date survives intact and is not glued to the number, which is exactly
    # what "R-2002 ...KK 12 LT GP25-08-2026" was.
    assert "25-08-2026" in page1
    assert "GP25-08-2026" not in page1
    for token in ("Document Number", "Document Date"):
        assert token in page1


def test_a_60_character_number_is_truncated_rather_than_overprinted_on_page_two():
    long_no = "R-" + "9" * 120        # no spaces at all: nothing to wrap on
    texts = _pages(_ctx(PRINT_MODE_ITEMIZED, document_number=long_no))
    page1 = texts[0]
    assert "9" * 120 not in page1, "an unwrappable value must be cut, not run on"
    assert "Document Date" in page1 and "25-08-2026" in page1


# ── default 7: the acceptance form's Order Number line ───────────────────────

def test_the_acceptance_form_offers_an_order_number_line():
    """Lezette, 25 Aug: Signature / PRINT NAME / Date each had a ruled line and
    Order Number had none, which read as an oversight on the page."""
    texts = _pages(_ctx(PRINT_MODE_BREAKDOWN))
    acceptance = [t for t in texts if "Quote Acceptance form" in t]
    assert acceptance, "the acceptance form is missing"
    for field in ("Signature:", "PRINT NAME:", "Date:", "Order Number:"):
        assert field in acceptance[0], field


def test_every_acceptance_field_gets_a_rule_of_its_own():
    """Four fields, four rules. Counted in the page's own drawing operators,
    because "there is a line after the label" is not visible in extracted text."""
    import re
    from io import BytesIO
    from pypdf import PdfReader
    from app.services.quote_document_pdf import render_repair_quote_pdf
    reader = PdfReader(BytesIO(render_repair_quote_pdf(_ctx(PRINT_MODE_BREAKDOWN))))
    page = [p for p in reader.pages
            if "Quote Acceptance form" in (p.extract_text() or "")][0]
    ops = page.get_contents().get_data().decode("latin-1")
    # 4 field rules + the footer's own divider.
    assert len(re.findall(r"\d[\d.]* [\d.]+ l", ops)) == 5


# ── the footer is not a place to print line items (v1.51, Lezette 26 Aug) ────
#
# Lezette photographed a quote whose last two lines were drawn straight through
# the remittance block, and the very first R-2001 did the same thing with its
# TOTALS. Three separate heights were never budgeted:
#
#   * the "Description | Quantity | Price | Total" row, repeated on EVERY page;
#   * the "Carry Over" row a continuation page opens with;
#   * the totals block itself, on the last page.
#
# Detected through the extracted TEXT rather than coordinates: when two strings
# are painted over each other reportlab still emits both, and the extractor
# interleaves them - "FORWARD" over "GALV" comes out as "FORWGAARLDV". So the
# footer's own headings surviving INTACT on every page is a precise test for
# "nothing was drawn on top of them", and it needs no geometry.

# The footer's own text, by the y it is drawn at. Anything ELSE drawn into that
# band is painted on top of it.
#
# Checked by COORDINATE, not by string. pypdf's extract_text() rebuilds text in
# content-stream order and never interleaves two strings that are drawn over
# each other, so the footer reads back perfectly intact even when it has been
# obliterated - the first version of this test was green against the unfixed
# renderer for exactly that reason. pypdf's visitor_text hands us the text
# matrix, so the y each string is actually painted at is available without
# adding a dependency.
_FOOTER_OWN = (
    "FORWARD REMITTANCE TO :", "Martie Snyman", "E-mail: martie@icecoldgrp.co.za",
    "BANKING DETAILS :", "Capitec Business", "Current Account",
    "Acc No: 105 068 2114", "Branch Code: 450 105", "SWIFT Code :  CABLZAJJ",
)


def _footer_intruders(pdf_bytes):
    """Every string painted into the footer band that does not belong to it."""
    from io import BytesIO
    from pypdf import PdfReader
    from app.services.quote_document_pdf import _MARGIN_MM, _FOOTER_H_MM
    floor = (_MARGIN_MM + _FOOTER_H_MM) * 72.0 / 25.4      # mm -> points
    out = []
    for page_no, page in enumerate(PdfReader(BytesIO(pdf_bytes)).pages, start=1):
        hits = []

        def visit(text, cm, tm, font_dict, font_size, _hits=hits):
            t = (text or "").strip()
            if not t:
                return
            # drawOn() translates the canvas before painting a table, so the
            # text matrix alone is RELATIVE to that translate - reading tm[5] by
            # itself puts every table row near y=0 and flags the whole document.
            y = tm[5] + cm[5]
            if y < floor and t not in _FOOTER_OWN:
                _hits.append((t, round(y, 1)))

        page.extract_text(visitor_text=visit)
        out.extend((page_no, t, y) for t, y in hits)
    return out


_PART_NAMES = [
    "130*62MM TAPPING BLOCKS_200MM", "CSLB HINGES", "SB 51111 DOOR SET",
    "34*3 LOCKING POLE", "28779 DOOR CAPPING", "2316 DOOR RUBBER",
    "M10*40 GALV. BOLTS", "M10 SPRING WASHERS", "0661-0631 LONG RIVETS",
    "SILPLUS X WHITE SILICONE", "3MM ALU BUFFER PLATE",
]


def _many_line_result(n):
    items = [{"material": _PART_NAMES[i % len(_PART_NAMES)],
              "category": "REPAIR LINES", "quantity": 1.0,
              "unit_price": 100.0, "line_cost": 100.0} for i in range(n)]
    gross = 100.0 * n
    return {"repair_type": "Rear door replacement", "selling_price": gross,
            "discount_amount": 0.0, "net_total": gross, "items": items}


def _many_ctx(n, mode):
    from app.services.quote_document import lines_total
    r = _many_line_result(n)
    lines = document_lines(r, mode)
    return _ctx(mode, lines=lines, lines_total=lines_total(lines),
                totals=totals_block(r, rate_pct=15.0))


def _render_many_bytes(n, mode):
    from app.services.quote_document_pdf import render_repair_quote_pdf
    return render_repair_quote_pdf(_many_ctx(n, mode))


def _render_many(n, mode):
    return _pages(_many_ctx(n, mode))


@pytest.mark.parametrize("mode", list(PRINT_MODES))
@pytest.mark.parametrize("n", [14, 20, 26, 41, 46, 55])
def test_nothing_is_ever_drawn_over_the_remittance_footer(mode, n):
    """The real R-2001 was 26 lines. The other counts are the boundaries each
    unbudgeted height used to break at: 14 (totals over the footer on a
    one-pager), 20 and 26 (items over it), 41 (totals on page 2), 46 and 55
    (items on a continuation page, which also carries a Carry Over row)."""
    intruders = _footer_intruders(_render_many_bytes(n, mode))
    assert not intruders, (
        f"{mode} n={n}: {len(intruders)} string(s) painted over the remittance "
        f"footer, e.g. {intruders[:3]}")


@pytest.mark.parametrize("mode", list(PRINT_MODES))
def test_the_totals_block_survives_a_quote_that_fills_its_last_page(mode):
    """When the lines end too low for the totals, the totals take a page of
    their own rather than being painted over the footer - which is how the old
    system's own quote reads (R-231037388 puts its totals alone on page 2/4)."""
    for n in (13, 14, 15, 40, 41, 42):
        texts = _render_many(n, mode)
        joined = "\n".join(texts)
        assert "Total Amount:" in joined, f"{mode} n={n}: the totals vanished"
        # ...and exactly once: a spill must MOVE the block, never duplicate it.
        assert joined.count("Total Amount:") == 1, \
            f"{mode} n={n}: the totals block was drawn {joined.count('Total Amount:')} times"


@pytest.mark.parametrize("mode", list(PRINT_MODES))
def test_page_numbers_stay_contiguous_when_the_totals_spill(mode):
    """A spill page is a real page: it must be counted in "n/m" and must not
    re-use the number the terms page then claims."""
    import re
    for n in (14, 26, 41):
        texts = _render_many(n, mode)
        stamped = []
        for t in texts:
            # Anchored on the "Page" label: an unanchored n/m also matches the
            # letterhead's Co. Reg. Nr ("2000/025936/07"), which is how the
            # first version of this test read page 1 as page 2000.
            m = re.search(r"Page\s*(\d+)\s*/\s*(\d+)", t)
            if m:
                stamped.append((int(m.group(1)), int(m.group(2))))
        assert stamped, f"{mode} n={n}: no page numbers stamped"
        assert [a for a, _ in stamped] == list(range(1, len(texts) + 1)), \
            f"{mode} n={n}: page numbers are {stamped} across {len(texts)} pages"
        assert {b for _, b in stamped} == {len(texts)}, \
            f"{mode} n={n}: stamped total disagrees with the real page count"
