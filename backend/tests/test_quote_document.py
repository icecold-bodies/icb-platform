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
    PRINT_MODE_BREAKDOWN, PRINT_MODE_ITEMIZED, PRINT_MODE_SUMMARY,
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
    nothing else. Those cells must be EMPTY — never 0, never the carrier 1.

    v1.51 — this is ITEMIZED's grammar, asked for by name. BREAKDOWN (now the
    default) blanks all three money columns on every line, which its own tests
    below pin; the rule here is about the lines that are lump sums even when the
    document IS printing money.
    """
    result = {"items": [
        {"material": "Remove nose cone and scrap.", "quantity": 1.0,
         "unit_price": 280.0, "line_cost": 280.0, "total_only": True},
        {"material": "Rubber seal kit", "quantity": 2.0,
         "unit_price": 450.0, "line_cost": 900.0},
    ]}
    lines = document_lines(result, PRINT_MODE_ITEMIZED)
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
    lines = document_lines(result, PRINT_MODE_ITEMIZED)
    assert [l["description"] for l in lines] == ["In"]
    assert lines_total(lines) == pytest.approx(100.0)
    # ...and in every other mode too: an excluded line is not a formatting
    # choice, it is a line the customer must never see.
    for mode in (PRINT_MODE_BREAKDOWN, PRINT_MODE_SUMMARY):
        assert all("Out" not in l["description"]
                   for l in document_lines(result, mode)), mode


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
    # v1.51 — ITEMIZED by name. These tests pin the SHELL (pagination, the
    # Carry Over bar, the terms and acceptance pages), and a Carry Over bar
    # exists only where the line column carries money — so the shell has to be
    # exercised in the mode that prints it.
    lines = document_lines(result, PRINT_MODE_ITEMIZED)
    return {
        "config": DEFAULT_CONFIG, "print_mode": PRINT_MODE_ITEMIZED,
        "document_number": "R-000123",
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
        # v1.49 — "Page" and "n/m" are drawn as two runs now the number sits
        # top-right in the sample's style, so extraction separates them. What
        # matters is that the page is NUMBERED, not how it is typeset.
        assert "Page" in t, f"page {i} lost its page label"
        assert f"{i}/{total}" in t, f"page {i} is not numbered n/m"
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


# ── v1.50: the customer's Purchase Order line (Lezette, 22 Aug) ──────────────

def test_the_purchase_order_line_sits_with_the_signature_block_on_a_long_quote():
    """The line is for the CUSTOMER to complete by hand when signing — so it
    must ride the CONDITIONS OF SALES / signature block, which the renderer
    draws AFTER every page of line items, never at the foot of whatever page
    the items happen to end on. Proven on a quote long enough for 3+ pages."""
    from app.services.quote_document_pdf import render_repair_quote_pdf
    ctx, _ = _long_ctx(45)
    texts = _page_texts(render_repair_quote_pdf(ctx))
    assert len(texts) >= 3, f"expected a multi-page quote, got {len(texts)}"

    po_pages = [i for i, t in enumerate(texts) if "Purchase Order No" in t]
    terms_pages = [i for i, t in enumerate(texts) if "CONDITIONS OF SALES" in t]
    assert len(po_pages) == 1, f"the PO line must appear exactly once, got pages {po_pages}"
    assert po_pages == terms_pages, "the PO line must sit in the signature block"
    # ...which lies BEYOND the last page of line items, whatever their number.
    line_pages = [i for i, t in enumerate(texts) if "Carry Over" in t
                  or "Total Amount" in t]
    assert po_pages[0] > max(line_pages), \
        "the PO line floated onto a line-items page instead of the terms page"
    # Beside Signature / Date — all three share the signature area.
    assert "Signature" in texts[po_pages[0]] and "Date" in texts[po_pages[0]]


def test_the_purchase_order_label_is_admin_editable_and_blank_omits_it():
    """D7 — the wording changes in admin without a work order; blanking the
    label removes the line outright."""
    from copy import deepcopy
    from app.services.quote_document_config import DEFAULT_CONFIG
    from app.services.quote_document_pdf import render_repair_quote_pdf

    edited = deepcopy(DEFAULT_CONFIG)
    edited["terms"]["blocks"][4]["po_line"] = "Client Order Ref:"
    ctx, _ = _long_ctx(3)
    ctx["config"] = edited
    joined = "\n".join(_page_texts(render_repair_quote_pdf(ctx)))
    assert "Client Order Ref:" in joined
    assert "Purchase Order No" not in joined

    blanked = deepcopy(DEFAULT_CONFIG)
    blanked["terms"]["blocks"][4]["po_line"] = ""
    ctx2, _ = _long_ctx(3)
    ctx2["config"] = blanked
    joined2 = "\n".join(_page_texts(render_repair_quote_pdf(ctx2)))
    assert "Purchase Order" not in joined2, "a blanked label must omit the line"


def test_a_stored_config_from_before_the_po_line_still_prints_it(app_mod):
    """get_config's top-level merge is WHOLESALE: a terms blob an admin saved
    before v1.50 simply lacks po_line. The config layer must heal it (any block
    flagged signature_block gets the default), and the admin field list must
    read the missing key as blank rather than KeyError-ing the whole screen."""
    from copy import deepcopy
    from app.database import SessionLocal
    from app.services.quote_document_config import (DEFAULT_CONFIG, _row,
                                                    get_config, read_field,
                                                    save_config)
    legacy = deepcopy(DEFAULT_CONFIG)
    del legacy["terms"]["blocks"][4]["po_line"]

    # The pure half: a config dict without the key reads blank, never raises.
    assert read_field(legacy, "terms.blocks[4].po_line") == ""

    with SessionLocal() as db:
        prev = _row(db)
        prev_data = prev.template_data if prev is not None else None
        try:
            save_config(db, legacy)
            healed = get_config(db)
            sig_blocks = [b for b in healed["terms"]["blocks"]
                          if b.get("signature_block")]
            assert sig_blocks, "the CONDITIONS OF SALES block went missing"
            assert all(b.get("po_line") == "Purchase Order No:" for b in sig_blocks), \
                "a pre-v1.50 stored config must be healed to print the PO line"
        finally:
            row = _row(db)
            if prev_data is not None:
                row.template_data = prev_data
                db.commit()
            elif row is not None:
                db.delete(row)
                db.commit()


# ── the download endpoint ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as _c:
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(app_mod):
    import uuid
    from app.database import SessionLocal, User, UserSession
    sid = f"qd-{uuid.uuid4().hex[:12]}"
    csrf = f"csrf-{sid}"
    with SessionLocal() as db:
        u = db.query(User).filter_by(username="admin").first()
        db.merge(UserSession(id=sid, user_id=u.id, role=u.role, expires_at=None,
                             csrf_token=csrf))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": csrf}


@pytest.fixture()
def saved_repair(app_mod):
    """A saved REPAIRS costing, shaped as the surface saves one."""
    import json
    from app.database import SessionLocal, CalculationRecord, Customer
    with SessionLocal() as db:
        cust = Customer(name="QD Sample Customer", is_active=True,
                        telephone="011 000 0000", email="qd@example.co.za",
                        vat_number="477 026 7526")
        db.add(cust)
        db.flush()
        result = {
            "items": [{"material": "Remove nose cone and scrap.", "quantity": 1.0,
                       "unit_price": 280.0, "line_cost": 280.0, "total_only": True,
                       "free_hand": True}],
            # v1.48 — the display-only keys results.html reads. The document
            # itself needs none of them, but a test that renders the results
            # page does, and a repair's real result_json carries them.
            "category_totals": {"REPAIR LINES": 280.0},
            "category_multipliers": {}, "materials_total": 280.0,
            "cost_per_sqm": 0.0, "geometry": {}, "chassis": None,
            "profit_amount": 0.0, "profit_margin": 0.0,
            "ratio_value": 1.0, "ratio_label": "100%", "ratio_amount": 0.0,
            "grand_total": 280.0, "selling_price": 280.0,
            "discount_amount": 0.0, "net_total": 280.0,
            "repair_type": "Front panel replacement",
            "repair_document_number": "R-000777",
            "input_state": {"is_repair": True, "repair_type": "Front panel replacement",
                            "repair_scope": "Strip and refit the front panel.",
                            "vehicle_registration": "LT 15 FB GP",
                            "delivery_address": "83 Heidelberg Road\nCity Deep",
                            "icb_contact_name": "Suzette Cocklin",
                            "icb_contact_phone": "+27 82 563 4864",
                            "payment_terms": "COD",
                            "repair_document_number": "R-000777"},
        }
        rec = CalculationRecord(trailer_type_id=None, customer_id=cust.id,
                                is_repair=True, quote_number="A1/08/2026",
                                dimensions_json="{}", result_json=json.dumps(result))
        db.add(rec)
        db.commit()
        ids = (rec.id, cust.id)
    yield ids
    with SessionLocal() as db:
        db.query(CalculationRecord).filter_by(id=ids[0]).delete()
        db.query(Customer).filter_by(id=ids[1]).delete()
        db.commit()


def test_the_repair_quote_downloads_as_a_pdf(
        client, admin_headers, saved_repair):
    rec_id, _ = saved_repair
    r = client.get(f"/api/calculations/{rec_id}/repair-quote.pdf", headers=admin_headers)
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"].startswith("application/pdf")
    # v1.50 (Lezette, 22 Aug) — {R-number} - {Customer} - {Vehicle reg}: the
    # document number LEADS the name now; the 18 Aug date form is superseded.
    disp = r.headers.get("content-disposition", "")
    assert disp == ('attachment; filename='
                    '"R-000777 - QD Sample Customer - LT 15 FB GP.pdf"'), disp
    assert r.content[:4] == b"%PDF"

    texts = _page_texts(r.content)
    joined = "\n".join(texts)
    # The header block carries the customer, its VAT number and the D8 fields.
    assert "QD Sample Customer" in joined
    assert "477 026 7526" in joined
    assert "LT 15 FB GP" in joined, "the vehicle registration must print"
    assert "Suzette Cocklin" in joined, "Your Contact must print"
    assert "R-000777" in joined, "the document number must print"
    assert "Remove nose cone and scrap." in joined, "the repair line must print"


def test_a_body_costing_is_refused_rather_than_rendered_blank(
        client, admin_headers, app_mod):
    """A body costing has no repair lines, no repair type and no vehicle — an
    official-looking document full of blanks is worse than a clear refusal."""
    from app.database import SessionLocal, CalculationRecord
    with SessionLocal() as db:
        rec = CalculationRecord(trailer_type_id=None, is_repair=False,
                                dimensions_json="{}", result_json="{}")
        db.add(rec)
        db.commit()
        rid = rec.id
    try:
        r = client.get(f"/api/calculations/{rid}/repair-quote.pdf", headers=admin_headers)
        assert r.status_code == 409, r.text[:200]
        assert "only for repair costings" in r.json()["detail"]
    finally:
        with SessionLocal() as db:
            db.query(CalculationRecord).filter_by(id=rid).delete()
            db.commit()


def test_the_document_endpoint_requires_a_session(client, saved_repair):
    rec_id, _ = saved_repair
    r = client.get(f"/api/calculations/{rec_id}/repair-quote.pdf")
    assert r.status_code == 401


# ── admin round-trip (D7) ────────────────────────────────────────────────────

def test_an_admin_edit_reaches_the_next_document(client, admin_headers, saved_repair):
    """D7's actual promise: change the wording in admin, and the NEXT quotation
    prints it — no code change, no redeploy. Asserted end to end, from the API
    through the store to text extracted from the rendered PDF."""
    rec_id, _ = saved_repair

    before = client.get(f"/api/calculations/{rec_id}/repair-quote.pdf", headers=admin_headers)
    assert before.status_code == 200
    assert "thirty (30) days" in "\n".join(_page_texts(before.content))

    r = client.put("/api/quote-document-config", headers=admin_headers, json={
        "terms.blocks[0].body": "The validity period on this quote is NINETY (90) days.",
        "vat_rate_pct": "20",
    })
    assert r.status_code == 200, r.text[:300]

    after = client.get(f"/api/calculations/{rec_id}/repair-quote.pdf", headers=admin_headers)
    joined = "\n".join(_page_texts(after.content))
    assert "NINETY (90) days" in joined, "the edited term did not reach the document"
    assert "thirty (30) days" not in joined
    # The VAT rate is a setting too: 280.00 at 20% is 56.00 tax, 336.00 incl.
    assert "56.00" in joined and "336.00" in joined, "the edited VAT rate did not apply"

    # Put it back so the rest of the suite sees the seeded wording.
    client.put("/api/quote-document-config", headers=admin_headers, json={
        "terms.blocks[0].body": "The validity period on this quote is thirty (30) days "
                                "from date hereof. After this period, we reserve the "
                                "right to re-quote.",
        "vat_rate_pct": "15",
    })


def test_the_config_api_is_admin_only(client, saved_repair):
    r = client.get("/api/quote-document-config")
    assert r.status_code in (401, 403)
    r2 = client.put("/api/quote-document-config", json={"vat_rate_pct": "0"})
    assert r2.status_code in (401, 403)


# ── v1.48: who may download it, and where the button appears ─────────────────

def test_a_non_admin_quoting_user_can_download_the_quotation():
    """The gate is quote.generate — the same one the body Generate Quote uses.

    Negative control for a real defect: through v1.47 the gate string was
    "exports.pdf", which matches no catalogue row, so `user_can` could only ever
    return True via the admin short-circuit. Every test of this endpoint ran as
    admin, so nothing caught it — Nadie on the 'full' role would have been
    refused her own customer's quotation.
    """
    from app.database import PERMISSION_CATALOGUE
    from app.routers.quote_document import _GATE

    keys = {row[0] for row in PERMISSION_CATALOGUE}
    assert _GATE in keys, (
        f"the download gate {_GATE!r} is not a permission key — it can never be "
        f"granted, so only admins could ever download")

    roles = next(row[3] for row in PERMISSION_CATALOGUE if row[0] == _GATE)
    assert "full" in roles and "user" in roles, (
        "a quoting user must be able to download the quote they just made")


def test_the_document_predicate_is_the_pair_not_the_repair_flag_alone():
    """Calculator 2's repair tick keeps a body — that costing has no quotation."""
    from app.services.quote_document import has_repair_quote_document

    class _Rec:
        def __init__(self, is_repair, trailer_type_id):
            self.is_repair, self.trailer_type_id = is_repair, trailer_type_id

    assert has_repair_quote_document(_Rec(True, None)) is True, "REPAIRS mode"
    assert has_repair_quote_document(_Rec(True, 7)) is False, \
        "Calculator 2 repair tick on a real body — the document would be blanks"
    assert has_repair_quote_document(_Rec(False, 7)) is False, "ordinary body"
    assert has_repair_quote_document(_Rec(False, None)) is False


def test_the_endpoint_and_the_buttons_share_one_predicate():
    """The button must never appear where the endpoint refuses.

    Both surfaces (results.html's Generate Quote, the React detail page's
    has_repair_quote) are fed from has_repair_quote_document, so a change to
    who gets the document moves them together.
    """
    import inspect
    from app.routers import quote_document, calculator

    src = inspect.getsource(quote_document.repair_quote_pdf)
    assert "has_repair_quote_document" in src, \
        "the endpoint must ask the shared predicate, not re-derive the rule"
    assert "is_repair" not in src.replace("has_repair_quote_document", ""), \
        "no second copy of the rule in the endpoint"

    list_src = inspect.getsource(calculator.api_list_calculations)
    assert '"has_repair_quote": has_repair_quote_document(r)' in list_src, \
        "the React detail button reads this field off the list row"


def test_the_repair_results_page_offers_the_quotation_not_a_dead_button(
        client, admin_headers, saved_repair):
    """The reported symptom: Generate Quote greyed out on a repair.

    resolve_report_template needs a trailer type and a REPAIRS costing has none,
    so before v1.48 this page fell to the disabled branch.
    """
    rec_id, _ = saved_repair
    r = client.get(f"/results/{rec_id}", headers=admin_headers)
    assert r.status_code == 200, r.text[:200]
    html = r.text

    assert f"/api/calculations/{rec_id}/repair-quote.pdf" in html, \
        "Generate Quote must point at the repair quotation"
    assert "No PDF quote template has been configured" not in html, \
        "the disabled branch must not be what a repair gets"


def test_a_body_costing_keeps_its_own_generate_quote(client, admin_headers, app_mod):
    """Negative control: the repair branch must not capture body costings."""
    import json
    from app.database import SessionLocal, CalculationRecord, TrailerType
    made_tt = None
    with SessionLocal() as db:
        tt = db.query(TrailerType).first()
        if tt is None:            # a bare test DB has no body templates seeded
            tt = TrailerType(name="QD Control Body", is_active=True)
            db.add(tt)
            db.flush()
            made_tt = tt.id
        rec = CalculationRecord(
            trailer_type_id=tt.id, is_repair=False, dimensions_json="{}",
            result_json=json.dumps({
                "items": [], "category_totals": {}, "category_multipliers": {},
                "materials_total": 0.0, "cost_per_sqm": 0.0, "geometry": {},
                "chassis": None, "profit_amount": 0.0, "profit_margin": 0.0,
                "ratio_value": 1.0, "ratio_label": "100%", "ratio_amount": 0.0,
                "grand_total": 0.0, "selling_price": 0.0,
            }))
        db.add(rec)
        db.commit()
        rid = rec.id
    try:
        r = client.get(f"/results/{rid}", headers=admin_headers)
        assert r.status_code == 200, r.text[:200]
        assert "repair-quote.pdf" not in r.text, \
            "a body costing must not be offered the repair quotation"
    finally:
        with SessionLocal() as db:
            db.query(CalculationRecord).filter_by(id=rid).delete()
            if made_tt:
                db.query(TrailerType).filter_by(id=made_tt).delete()
            db.commit()


def test_the_list_row_carries_the_flag_for_the_react_button(
        client, admin_headers, saved_repair):
    rec_id, _ = saved_repair
    r = client.get("/api/calculations?limit=200", headers=admin_headers)
    assert r.status_code == 200, r.text[:200]
    row = next((x for x in r.json() if x["id"] == rec_id), None)
    assert row is not None, "the saved repair must be in the list"
    assert row["has_repair_quote"] is True
    assert row["is_repair"] is True


# ── v1.50: the filename convention — {R-number} - {Customer} - {Vehicle reg} ──

class _FakeRec:
    """Just the attributes repair_quote_filename reads."""
    def __init__(self, d=None, quote_number="A1/08/2026", rec_id=1695):
        from datetime import datetime
        self.created_at = d if d is not None else datetime(2026, 8, 18)
        self.quote_number = quote_number
        self.id = rec_id


def test_the_filename_is_number_customer_registration():
    """Lezette's worked example, 22 Aug 2026, reproduced exactly."""
    from app.services.quote_document import repair_quote_filename
    name = repair_quote_filename(_FakeRec(), {
        "document_number": "R-1042",
        "customer_name": "Atlantic Seafoods",
        "customer_contact": "RIDHWAN MUSSA",        # dropped from the name (v1.50)
        "vehicle_registration": "LT 15 FB GP",
    })
    assert name == "R-1042 - Atlantic Seafoods - LT 15 FB GP"


def test_the_date_and_both_contacts_are_dropped_from_the_filename():
    """v1.50 — the number identifies the quote, so the 18 Aug date form is
    superseded: nothing in the name may derive from created_at, and neither
    contact (the customer's buyer OR ICB's person) names the file any more."""
    from datetime import datetime
    from app.services.quote_document import repair_quote_filename
    ctx = {
        "document_number": "R-1042",
        "customer_name": "ATLANTIC SEAFOODS",
        "customer_contact": "RIDHWAN MUSSA",
        "your_contact": "Suzette Cocklin",
        "vehicle_registration": "LT 15 FB GP",
    }
    a = repair_quote_filename(_FakeRec(datetime(2026, 8, 18)), ctx)
    b = repair_quote_filename(_FakeRec(datetime(2001, 1, 1)), ctx)
    assert a == b, "the record's date must play no part in the name"
    assert "2026" not in a and "20260818" not in a
    assert "RIDHWAN" not in a and "MUSSA" not in a
    assert "Suzette" not in a and "Cocklin" not in a


def test_the_filename_omits_missing_parts_and_their_separators():
    """Never "R-1042 -  - .pdf": a missing part takes its ' - ' with it."""
    from app.services.quote_document import repair_quote_filename
    f = repair_quote_filename
    base = {"document_number": "R-1042", "customer_name": "ACME",
            "vehicle_registration": "CA 1"}
    assert f(_FakeRec(), base) == "R-1042 - ACME - CA 1"
    assert f(_FakeRec(), {**base, "vehicle_registration": ""}) == "R-1042 - ACME"
    assert f(_FakeRec(), {**base, "customer_name": ""}) == "R-1042 - CA 1"
    assert f(_FakeRec(), {"document_number": "R-1042"}) == "R-1042"
    # A pre-R-series repair (no number yet) leads with the customer instead.
    assert f(_FakeRec(), {**base, "document_number": ""}) == "ACME - CA 1"
    for ctx in ({**base, "customer_name": "", "vehicle_registration": ""},
                {**base, "customer_name": "  ", "vehicle_registration": "\t"}):
        n = f(_FakeRec(), ctx)
        assert "  " not in n, "a missing part must not leave a double space"
        assert not n.endswith("-") and not n.endswith(" "), \
            "a missing part must take its separator with it"


def test_the_filename_is_safe_to_write_to_disk():
    """Real customer names carry slashes and quotes; real registrations do not
    survive a naive join. A quote that cannot be saved is a quote that is lost."""
    from app.services.quote_document import repair_quote_filename
    name = repair_quote_filename(_FakeRec(), {
        "document_number": "R-1042",
        "customer_name": 'A/B  Transport: Ltd',
        "vehicle_registration": "CA 123-456",
    })
    for ch in '\/:*?"<>|\r\n\t':
        assert ch not in name, f"{ch!r} is not legal in a Windows filename"
    assert not name.endswith("."), "a trailing dot is silently dropped by Windows"
    assert "  " not in name
    assert len(name) <= 180


def test_the_filename_falls_back_when_nothing_identifies_the_quote():
    """All three parts missing (a pre-R-series repair with nothing captured):
    the body quote number steps in, sanitised; last of all the record id."""
    from app.services.quote_document import repair_quote_filename
    empty = {"document_number": "", "customer_name": "", "vehicle_registration": ""}
    name = repair_quote_filename(_FakeRec(), dict(empty))
    assert name == "A1082026", "the body quote number, with its slashes stripped"
    name2 = repair_quote_filename(_FakeRec(quote_number=""), dict(empty))
    assert name2 == "repair-1695", "the record id is the very last resort"


def test_the_download_is_named_by_the_convention(client, admin_headers, saved_repair):
    """End to end: the Content-Disposition the browser actually sees."""
    rec_id, _ = saved_repair
    r = client.get(f"/api/calculations/{rec_id}/repair-quote.pdf", headers=admin_headers)
    assert r.status_code == 200, r.text[:200]
    disp = r.headers.get("content-disposition", "")
    assert disp == ('attachment; filename='
                    '"R-000777 - QD Sample Customer - LT 15 FB GP.pdf"'), disp


def test_the_header_height_follows_its_content():
    """The block is measured, not assumed.

    A fixed height either overflowed page 1 or left the void the first version
    had between the header and the table — visible in the very first render.
    """
    from app.services.quote_document_pdf import render_repair_quote_pdf
    base = {"config": {}, "title": "Repair Quotation", "customer_name": "ACME",
            "document_number": "R-9", "document_date": "18-08-2026",
            "lines": [{"description": "x", "qty": None, "price": None, "total": 1.0}],
            "totals": [{"label": "Total Amount:", "amount": 1.0, "note": ""}]}
    short = dict(base)
    tall = dict(base, delivery_address="1 A Road\n2 B Street\n3 C Avenue\n4 D Close",
                your_reference="Veh reg nr:  CA 1")
    a, b = render_repair_quote_pdf(short), render_repair_quote_pdf(tall)
    assert a and b
    # Both render; the tall one carries strictly more header text.
    import re
    assert len(b) > len(a), "a four-line delivery address must occupy more document"


def test_the_line_marker_is_drawn_not_typed():
    """Helvetica has no arrow glyph — a typed one renders as a tofu box, which is
    exactly what happened to the Carry Over bar on the first proof."""
    import inspect
    from app.services import quote_document_pdf as m
    src = inspect.getsource(m.render_repair_quote_pdf)
    assert "class _Arrow" in src and "beginPath" in src
    for glyph in ("▶", "►", "➤", "→"):
        assert glyph not in src, f"{glyph} will not render in Helvetica"
