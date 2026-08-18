"""The ICB quotation document — context, money and pagination (v1.47 Lane D).

Addendum D1: the ICB letterhead is becoming the house format for outgoing
quotes, and repairs are its first user. So this module holds the parts that are
NOT drawing: what the document says, what it adds up to, and where it breaks
across pages. `routers/quote_document_pdf.py` draws whatever this decides.

Keeping it split that way is what makes the hard part testable. Carry-over
across pages (D5) and the VAT totals block (D4) are pure functions over plain
data here, so a test can assert "page 2 continues from 52 270,00" without
rendering a PDF and reading it back.

Reference: `231034795 Atlantic Seafoods - Ridhwan - LT 15 FB GP.pdf`.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Sequence

from .quote_document_config import get_config, vat_amount, vat_rate_pct

# The sample's own wording, kept verbatim so the outgoing paperwork does not
# change when quoting moves off SAP.
LABEL_TOTAL_BEFORE_DISCOUNT = "Total before Discount:"
LABEL_DISCOUNT_SUBTOTAL     = "Discount Subtotal:"
LABEL_TOTAL_BEFORE_TAX      = "Total Before Tax:"
LABEL_TOTAL_TAX             = "Total Tax Amount:"
LABEL_TOTAL_INCL_VAT        = "Total Amount:\n(Including V.A.T)"
LABEL_CARRY_OVER            = "Carry Over:"


# ── who gets this document ───────────────────────────────────────────────────

def has_repair_quote_document(rec) -> bool:
    """True when this costing is a REPAIRS-mode costing, and so has a quotation.

    v1.48 — the single source of truth for that question. The download endpoint
    refuses anything else with 409, and the surfaces that offer a download
    button ask this too: a button that appears where the endpoint refuses is a
    broken link that ends in an official-looking error.

    Note this is NOT `is_repair` alone. Calculator 2's repair tick sets
    is_repair on a costing that still has a real body (trailer_type_id), and
    such a costing has no repair lines, no type of repair and no vehicle
    registration — the document would render as a page of blanks. REPAIRS mode
    is the pair: the repair flag AND no body.
    """
    return (bool(getattr(rec, "is_repair", False))
            and getattr(rec, "trailer_type_id", None) is None)


# ── money ────────────────────────────────────────────────────────────────────

def money(value: float) -> str:
    """"52,270.00" — the sample's format: thousands separated, always 2 dp.

    NB this is the DOCUMENT's format, which is the SAP-era format ICB's
    customers already receive. It deliberately differs from the costing page's
    SA style (R 52 270,00): changing what the customer sees is not this lane's
    job.
    """
    return f"{float(value or 0):,.2f}"


def totals_block(result: dict, db=None, *, rate_pct: float | None = None) -> list[dict]:
    """The five totals rows, in the sample's exact order (D4).

    Rows are {label, amount, note}; `note` carries the discount percentage the
    sample prints beside its own row. Prices are quoted EXCLUSIVE of VAT — the
    terms say so — so tax is ADDED here, never extracted.
    """
    result = result or {}
    gross = float(result.get("selling_price")
                  if result.get("selling_price") is not None
                  else result.get("grand_total") or 0)
    discount = float(result.get("discount_amount") or 0)
    net = float(result.get("net_total") if result.get("net_total") is not None
                else gross - discount)
    rate = rate_pct if rate_pct is not None else vat_rate_pct(db)
    tax = vat_amount(net, rate)

    disc_note = ""
    if result.get("discount_kind") == "percent" and result.get("discount_input"):
        disc_note = f"{float(result['discount_input']):.2f}%"
    elif discount:
        disc_note = ""

    return [
        {"label": LABEL_TOTAL_BEFORE_DISCOUNT, "amount": gross,      "note": ""},
        {"label": LABEL_DISCOUNT_SUBTOTAL,     "amount": discount,   "note": disc_note or "0.00%"},
        {"label": LABEL_TOTAL_BEFORE_TAX,      "amount": net,        "note": ""},
        {"label": LABEL_TOTAL_TAX,             "amount": tax,        "note": ""},
        {"label": LABEL_TOTAL_INCL_VAT,        "amount": net + tax,  "note": "", "emphasis": True},
    ]


# ── lines ────────────────────────────────────────────────────────────────────

def document_lines(result: dict) -> list[dict]:
    """The repair lines as the document prints them.

    D3: most real lines carry a long description and a LUMP-SUM total with NO
    quantity and NO unit price — every line in the reference quote is that
    shape. Those cells must come out EMPTY, never 0 and never 1, so `qty` and
    `price` are None rather than the carrier values the costing engine needed.
    """
    out: list[dict] = []
    for it in (result or {}).get("items") or []:
        if it.get("excluded"):
            continue
        total_only = bool(it.get("total_only"))
        out.append({
            "description": it.get("material") or "",
            "qty":   None if total_only else it.get("quantity"),
            "price": None if total_only else it.get("unit_price"),
            "total": float(it.get("line_cost") or 0),
            "notes": it.get("notes") or "",
        })
    return out


def lines_total(lines: Sequence[dict]) -> float:
    return round(sum(float(l.get("total") or 0) for l in lines), 2)


# ── pagination + carry over (D5) ─────────────────────────────────────────────

def paginate_lines(lines: Sequence[dict],
                   capacity_for_page: Callable[[int], float],
                   height_of: Callable[[dict], float]) -> list[list[dict]]:
    """Split lines into pages by measured height.

    `capacity_for_page(i)` is the usable height on page i (page 1 is shorter —
    it carries the letterhead and the header block); `height_of(line)` is the
    measured height of one rendered row, which the renderer supplies because
    only it knows how a long description wraps.

    A line taller than a whole empty page is placed on a page of its own rather
    than looping forever — it will overflow visibly, which is the honest
    outcome and vastly preferable to a hang.
    """
    pages: list[list[dict]] = []
    current: list[dict] = []
    used = 0.0
    page_index = 0
    cap = capacity_for_page(0)
    for line in lines:
        h = float(height_of(line) or 0)
        if current and used + h > cap:
            pages.append(current)
            current = []
            page_index += 1
            used = 0.0
            cap = capacity_for_page(page_index)
        current.append(line)
        used += h
    if current:
        pages.append(current)
    return pages


def carry_over_for(pages: Sequence[Sequence[dict]]) -> list[float]:
    """The running total AT THE END of each page.

    The sample prints "Carry Over: 52,270.00" at the foot of a page that
    continues and again at the top of the next, so entry i of this list is the
    figure printed at the foot of page i and at the head of page i+1. The last
    page's entry is the full lines total and is NOT printed as a carry over —
    the totals block takes over there.
    """
    running = 0.0
    out: list[float] = []
    for page in pages:
        running = round(running + sum(float(l.get("total") or 0) for l in page), 2)
        out.append(running)
    return out


# ── what the downloaded file is called ───────────────────────────────────────

# Characters Windows refuses in a filename, plus the ones that make a mess of a
# shell. Everything else — including the spaces the convention asks for — stays.
_FILENAME_BANNED = set('\\/:*?"<>|\r\n\t')


def repair_quote_filename(rec, ctx: dict[str, Any]) -> str:
    """`R20260818 360 DEGREES CARRIERS PETER SMITH LT15FB GP` — no extension.

    The naming convention is date + customer + contact + vehicle registration, so
    a repair quote can be found in a folder by any of the four things anyone
    actually remembers about it. Ratified by Michael, 18 Aug 2026.

    The contact is the CUSTOMER's contact person, not ICB's — the document's
    "Your Contact" block is ICB's person and deliberately plays no part here.

    Parts that are missing are simply left out rather than leaving a gap or an
    empty placeholder, so a quote captured without a registration still gets a
    sensible name.
    """
    date = rec.created_at.strftime("%Y%m%d") if getattr(rec, "created_at", None) else ""
    parts = [
        f"R{date}" if date else "R",
        ctx.get("customer_name") or "",
        ctx.get("customer_contact") or "",
        ctx.get("vehicle_registration") or "",
    ]
    cleaned = []
    for p in parts:
        # Collapse internal whitespace so a two-space entry cannot produce a
        # double gap that reads as a missing field.
        p = " ".join(str(p).split())
        p = "".join(ch for ch in p if ch not in _FILENAME_BANNED)
        if p:
            cleaned.append(p)
    name = " ".join(cleaned).strip(" .")          # a trailing dot breaks on Windows
    # The date alone identifies nothing — several repairs are quoted a day. When
    # every descriptive part is missing, fall back to the document number.
    if len(cleaned) <= 1:
        name = ctx.get("document_number") or getattr(rec, "quote_number", "") or f"repair-{rec.id}"
        name = "".join(ch for ch in str(name) if ch not in _FILENAME_BANNED).strip()
    return name[:180]                              # keep well inside path limits


# ── the whole context ────────────────────────────────────────────────────────

def build_repair_quote_context(rec, db, *, generated_at: str = "") -> dict[str, Any]:
    """Everything the renderer needs for one repair quotation, in plain data."""
    try:
        result = json.loads(rec.result_json) if rec.result_json else {}
    except (TypeError, ValueError):
        result = {}
    state = result.get("input_state") or {}
    cfg = get_config(db)
    customer = getattr(rec, "customer", None)

    lines = document_lines(result)
    return {
        "config": cfg,
        "document_number": (result.get("repair_document_number")
                            or state.get("repair_document_number") or ""),
        "document_date": rec.created_at.strftime("%d-%m-%Y") if rec.created_at else "",
        "quote_number": rec.quote_number or "",
        "title": "Repair Quotation",
        "original_label": "Original",
        # ── header block ──
        "customer_name": getattr(customer, "name", "") or "",
        "customer_vat": getattr(customer, "vat_number", "") or "",
        "customer_tel": getattr(rec, "contact_telephone", None) or getattr(customer, "telephone", "") or "",
        "customer_email": getattr(rec, "contact_email", None) or getattr(customer, "email", "") or "",
        # The CUSTOMER's own contact person — the attention-of snapshot taken when
        # the quote was saved (0035). Distinct from "Your Contact" below, which is
        # ICB's person, the one the customer rings. Both appear on the document;
        # only this one names the file.
        "customer_contact": getattr(rec, "contact_name", None) or "",
        # D8 — all captured per quote on the repair surface.
        "vehicle_registration": state.get("vehicle_registration") or "",
        "your_reference": (f"Veh reg nr:  {state['vehicle_registration']}"
                           if state.get("vehicle_registration") else ""),
        "delivery_address": state.get("delivery_address") or "",
        "your_contact": state.get("icb_contact_name") or "",
        "your_contact_phone": state.get("icb_contact_phone") or "",
        "payment_terms": state.get("payment_terms") or "COD",
        # The sample's "Job note" — mapped to the repair's work description.
        "job_note": state.get("repair_scope") or "",
        "repair_type": result.get("repair_type") or state.get("repair_type") or "",
        # ── body ──
        "lines": lines,
        "lines_total": lines_total(lines),
        "totals": totals_block(result, db),
        "vat_rate_pct": vat_rate_pct(db),
        "generated_at": generated_at,
    }
