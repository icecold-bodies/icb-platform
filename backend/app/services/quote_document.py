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


# ── how much of itself the document shows (v1.51) ────────────────────────────
#
# Lezette test-drove R-2001/R-2002 against the old system's R-231037388 and the
# gap was not the numbers — it was how much of the costing the CUSTOMER sees.
# The old system printed the work, not the pricing of the work: every line
# carries its description and the three money columns are EMPTY, with the money
# appearing once, in the totals block. That is the ratified default here.
#
# Three modes rather than a flag because all three are real outgoing documents:
#   * SUMMARY   — one line per repair section, no item detail at all. For the
#                 customer who wants a price, not a method statement.
#   * BREAKDOWN — every line's description, money columns empty (DEFAULT; this
#                 is the old system's shape, reproduced).
#   * ITEMIZED  — quantity, unit price and line total on every row. What the
#                 document did through v1.50; kept because a customer who asks
#                 "what am I paying for each part" must still be answerable.
PRINT_MODE_SUMMARY   = "summary"
PRINT_MODE_BREAKDOWN = "breakdown"
PRINT_MODE_ITEMIZED  = "itemized"
PRINT_MODES = (PRINT_MODE_SUMMARY, PRINT_MODE_BREAKDOWN, PRINT_MODE_ITEMIZED)
DEFAULT_PRINT_MODE = PRINT_MODE_BREAKDOWN

# Where the last-used mode is remembered. It rides `result_json` beside the
# document number rather than a column of its own: a re-download must reproduce
# the document that was sent, and that is a property of THIS quote, not of the
# user or the browser that fetched it. (No migration — see also the
# carry-forward in routers/calculator.py, which keeps it across an edit-save.)
PRINT_MODE_KEY = "repair_quote_print_mode"


def normalize_print_mode(value) -> str:
    """Any input to one of PRINT_MODES, defaulting rather than raising.

    A mode arrives from a query string, from stored JSON written by an older
    build, or from nothing at all. None of those is an error the user can act
    on, and refusing the download over an unreadable preference would take the
    quotation away for the sake of a formatting choice — so an unknown value
    simply falls back to the ratified default.
    """
    v = str(value or "").strip().lower()
    return v if v in PRINT_MODES else DEFAULT_PRINT_MODE


def stored_print_mode(result: dict) -> str:
    """The mode this costing was last downloaded in (default when never)."""
    result = result or {}
    return normalize_print_mode(
        result.get(PRINT_MODE_KEY)
        or (result.get("input_state") or {}).get(PRINT_MODE_KEY))


# The repair surface's own default section name (free_hand.REPAIR_SECTION),
# matched by VALUE rather than imported so this module keeps no dependency on
# the calculator's input validation — it only ever needs to recognise it.
_INTERNAL_REPAIR_SECTION = "REPAIR LINES"


# ── lines ────────────────────────────────────────────────────────────────────

def document_lines(result: dict, mode: str = DEFAULT_PRINT_MODE) -> list[dict]:
    """The repair lines as the document prints them, in the requested mode.

    D3: most real lines carry a long description and a LUMP-SUM total with NO
    quantity and NO unit price — every line in the reference quote is that
    shape. Those cells must come out EMPTY, never 0 and never 1, so `qty` and
    `price` are None rather than the carrier values the costing engine needed.

    v1.51 — `mode` decides how much of each line is printed. SUMMARY and
    BREAKDOWN blank the money columns by returning None in every one of them,
    including `total`: None is the renderer's "print nothing here", where 0.0
    would print a real and wrong "0.00". The totals block is computed from the
    costing, not from these rows, so the document still adds up in every mode.
    """
    mode = normalize_print_mode(mode)
    items = [it for it in (result or {}).get("items") or [] if not it.get("excluded")]

    if mode == PRINT_MODE_SUMMARY:
        return _summary_lines(items, result or {})

    money_cols = (mode == PRINT_MODE_ITEMIZED)
    out: list[dict] = []
    for it in items:
        total_only = bool(it.get("total_only"))
        out.append({
            "description": it.get("material") or "",
            "qty":   (None if total_only else it.get("quantity")) if money_cols else None,
            "price": (None if total_only else it.get("unit_price")) if money_cols else None,
            "total": float(it.get("line_cost") or 0) if money_cols else None,
            "notes": it.get("notes") or "",
        })
    return out


def _summary_lines(items: list[dict], result: dict) -> list[dict]:
    """One line per repair SECTION, in the order the sections first appear.

    The grouping key is the item's category, which is what the repair surface
    already writes: a line pulled from a body category carries that category's
    name ("REAR DOORS"), and a plain typed line carries free_hand.REPAIR_SECTION.
    That default is an INTERNAL name — printing "REPAIR LINES" to a customer
    says nothing — so a group under it falls back to the type of repair, then to
    a plain descriptive phrase. Money columns are empty here for the same reason
    as BREAKDOWN: the totals block is the one place the price is stated.
    """
    fallback = (str(result.get("repair_type") or "").strip()
                or str((result.get("input_state") or {}).get("repair_type") or "").strip()
                or "Repair work")
    order: list[str] = []
    seen: set[str] = set()
    for it in items:
        cat = str(it.get("category") or "").strip()
        label = fallback if (not cat or cat == _INTERNAL_REPAIR_SECTION) else cat
        if label not in seen:
            seen.add(label)
            order.append(label)
    return [{"description": label, "qty": None, "price": None,
             "total": None, "notes": ""} for label in order]



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


# ── the reference caption (v1.51) ────────────────────────────────────────────

# The caption printed above the reference value. "Veh reg nr:" for the repairs
# that ARE vehicle work — which is most of them, so it stays the default and no
# existing quote changes — but Lezette also quotes store sales, parts supply and
# serial-numbered units, where a registration caption is simply wrong.
DEFAULT_REFERENCE_LABEL = "Veh reg nr:"

# Long enough for a real caption, short enough that it cannot push the value out
# of its header column.
MAX_REFERENCE_LABEL = 40


def vehicle_reference_label(state: dict) -> str:
    """The caption for Your Reference, defaulting for every quote written before
    the field existed (and for one saved with the box cleared)."""
    label = str((state or {}).get("vehicle_reference_label") or "").strip()
    return label[:MAX_REFERENCE_LABEL] if label else DEFAULT_REFERENCE_LABEL


# ── what the downloaded file is called ───────────────────────────────────────

# Characters Windows refuses in a filename, plus the ones that make a mess of a
# shell. Everything else — including the spaces the convention asks for — stays.
_FILENAME_BANNED = set('\\/:*?"<>|\r\n\t')


def repair_quote_filename(rec, ctx: dict[str, Any]) -> str:
    """`R-1042 - ATLANTIC SEAFOODS - LT 15 FB GP` — no extension.

    The naming convention is {R-number} - {Customer} - {Vehicle reg}, ratified
    22 Aug 2026 (Lezette, via BA): the document number identifies the quote, so
    the 18 Aug date+customer+contact+reg form is superseded — the date is
    dropped (the number carries identity) and the contact with it.

    Parts that are missing are simply left out WITH their separator — never
    "R-1042 -  - .pdf" — so a quote captured without a registration still gets
    a sensible name. A pre-R-series repair (no document number yet) leads with
    the customer instead.
    """
    parts = [
        ctx.get("document_number") or "",
        ctx.get("customer_name") or "",
        ctx.get("vehicle_registration") or "",
    ]
    cleaned = []
    for p in parts:
        # Collapse internal whitespace so a two-space entry cannot produce a
        # double gap that reads as a missing field.
        p = " ".join(str(p).split())
        p = "".join(ch for ch in p if ch not in _FILENAME_BANNED)
        p = p.strip(" .")
        if not p:
            continue
        # v1.50 — the document NUMBER may now itself embed the customer and the
        # registration, because the admin template can include {customer} and
        # {vehicle_registration}. Appending them again would produce
        # "R-100 ATLANTIC SEAFOODS CA 123-456 - ATLANTIC SEAFOODS - CA 123-456".
        # The number is always parts[0], so anything already inside it is
        # dropped rather than repeated; the convention is unchanged for the
        # default template, where the number carries neither.
        if cleaned and p.casefold() in cleaned[0].casefold():
            continue
        cleaned.append(p)
    name = " - ".join(cleaned).strip(" .")        # a trailing dot breaks on Windows
    # Nothing descriptive at all — fall back to the body-series quote number,
    # and as a last resort the record id, so the download is never "-.pdf".
    if not name:
        name = getattr(rec, "quote_number", "") or f"repair-{rec.id}"
        name = "".join(ch for ch in str(name) if ch not in _FILENAME_BANNED).strip(" .")
    return name[:180]                              # keep well inside path limits


# ── the whole context ────────────────────────────────────────────────────────

def build_repair_quote_context(rec, db, *, generated_at: str = "",
                               mode: str | None = None) -> dict[str, Any]:
    """Everything the renderer needs for one repair quotation, in plain data.

    `mode` is the print mode this download asked for; None means "whatever this
    costing was last downloaded as", which is what makes a re-download reproduce
    the document that was sent.
    """
    try:
        result = json.loads(rec.result_json) if rec.result_json else {}
    except (TypeError, ValueError):
        result = {}
    state = result.get("input_state") or {}
    cfg = get_config(db)
    customer = getattr(rec, "customer", None)
    mode = normalize_print_mode(mode) if mode is not None else stored_print_mode(result)

    lines = document_lines(result, mode)
    return {
        "config": cfg,
        "print_mode": mode,
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
        # v1.51 (Lezette, 25 Aug) — "Veh reg nr:" is now a LABEL the quote owns,
        # not a fixed string, because the same field carries "Store Sale",
        # "Parts Supply" or "Serial nr:" on the repairs that are not vehicle
        # work at all. Label and value both print under Your Reference; the
        # label alone prints nothing, since a caption with no value is furniture.
        "your_reference_label": vehicle_reference_label(state),
        "your_reference": (f"{vehicle_reference_label(state)}  {state['vehicle_registration']}".strip()
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
