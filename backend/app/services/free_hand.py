"""Free-hand costing lines + the REPAIRS costing mode (v1.47 Lane C).

ONE mechanism serves two needs from Nadie's 17 Aug session:

  1. OPTIONAL EXTRAS — type an extra that isn't in the list, on any body type.
  2. REPAIRS — quote repair work that has no body behind it at all, from
     stock-list lines and/or free-hand lines.

Both reduce to the same thing: a line carrying description · qty · unit ·
unit price · notes that costs exactly like a BOM line. This module turns such
lines into the synthetic ``bom_items`` dicts ``formula_engine.calculate_bom``
already consumes, so category totals, the materials cost, and every
margin/ratio/discount computation downstream need no special-casing at all.

Two invariants this module exists to hold:

  * NOTHING is ever written to the materials master. A free-hand line lives on
    the costing only — it rides ``result["input_state"]`` (the v1.39.9 snapshot
    pattern) and materialises in ``result["items"]``. No catalogue rows, ever.
  * A STOCK line's price is resolved SERVER-SIDE from the catalogue at
    calculate time. The client sends a material_id and a qty; it never gets to
    name the price of a catalogue material. Only genuinely free-hand lines
    carry a client-supplied unit price.

No migration: nothing here needs a column that doesn't already exist. The
REPAIRS mode reuses the existing repair identity (``is_repair``) so a repair
created here flows into the existing scheduling machinery
(``/api/calculations/{id}/schedule-repair``, RepairPhasePanel, the purple
Repair pill) untouched.
"""
from __future__ import annotations

from fastapi import HTTPException

from ..database import Material

# Length caps — generous enough for real descriptions, tight enough that a
# runaway paste can't bloat every result_json that carries the snapshot.
MAX_DESCRIPTION = 200
MAX_UNIT        = 32
MAX_NOTES       = 1000
MAX_REPAIR_TYPE = 120
MAX_REPAIR_SCOPE = 4000
# v1.47 Lane D — quotation-document header fields (addendum D8).
MAX_VEHICLE_REG = 40
MAX_DELIVERY_ADDRESS = 500      # multiline
MAX_CONTACT_NAME = 120
MAX_CONTACT_PHONE = 60
MAX_PAYMENT_TERMS = 60
DEFAULT_PAYMENT_TERMS = "COD"
# Per-costing line cap. A repair sheet is a handful of lines; anything near
# this is a malformed or hostile payload, not a quote.
MAX_LINES       = 200

# Ceilings on the numbers themselves. Without these a typo of 1e308 lands in
# the totals as inf and poisons every downstream document.
MAX_QTY         = 1_000_000.0
MAX_UNIT_PRICE  = 100_000_000.0

# The single category a REPAIRS costing's lines live under. WO §8: the category
# total IS the repair-lines total, so there is exactly one category.
REPAIR_SECTION = "REPAIR LINES"


def _fail(msg: str) -> None:
    """422 — the client sent a line it should not have been able to build."""
    raise HTTPException(status_code=422, detail=msg)


def _text(raw, *, field: str, cap: int, required: bool = False) -> str:
    if raw is None:
        raw = ""
    if not isinstance(raw, (str, int, float)):
        _fail(f"{field} must be text.")
    s = str(raw).strip()
    if required and not s:
        _fail(f"{field} is required on every line.")
    if len(s) > cap:
        _fail(f"{field} is too long (max {cap} characters).")
    return s


def _number(raw, *, field: str, ceiling: float) -> float:
    """Non-negative finite number. Accepts a comma decimal ("450,50") because
    that is how SA money is typed — the same courtesy the unit-price inputs
    extend on the costing page."""
    if raw is None or raw == "":
        _fail(f"{field} is required on every line.")
    if isinstance(raw, bool):
        _fail(f"{field} must be a number.")
    if isinstance(raw, str):
        raw = raw.strip().replace(" ", "")
        # Only treat a comma as the decimal separator when there is no dot to
        # disambiguate — "1.234,50" and "450,50" both mean what a SA typist means.
        if "," in raw and "." not in raw:
            raw = raw.replace(",", ".")
        else:
            raw = raw.replace(",", "")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        _fail(f"{field} must be a number.")
    if v != v or v in (float("inf"), float("-inf")):
        _fail(f"{field} must be a number.")
    if v < 0:
        _fail(f"{field} cannot be negative.")
    if v > ceiling:
        _fail(f"{field} is unrealistically large — check the value.")
    return v


def parse_lines(raw, *, allow_stock: bool = False, allow_total_only: bool = False,
                db=None) -> list[dict]:
    """Validate + normalise a client ``free_hand_lines`` / ``repair_lines`` list.

    Returns one normalised dict per line:
        {kind, key, description, qty, unit, unit_price, line_total, total_only,
         notes, material_id, bom_section_id, category, excluded}

    ``kind`` is "stock" (price resolved from the materials master) or
    "free_hand" (price typed by the user). Stock lines are only accepted when
    ``allow_stock`` is set — the OPTIONAL EXTRAS surface has the real BOM for
    catalogue items and has no business minting stock lines.

    ``allow_total_only`` (v1.47 Lane D, addendum D3) permits the line grammar the
    ICB repair quotation actually uses: a long description and a LUMP-SUM TOTAL,
    with no quantity and no unit price. In the reference quote every one of the
    14 lines is of this shape. Rules, as ratified:
      * both qty and unit price given  -> total = qty x unit price
      * neither given, line_total given -> that total is used VERBATIM
      * qty/unit price left out are None, NOT 0 or 1, so the document can print
        empty cells rather than a misleading "1".

    Raises 422 with a message fit to show the user on any malformed line.
    """
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        _fail("Lines must be sent as a list.")
    if len(raw) > MAX_LINES:
        _fail(f"Too many lines (max {MAX_LINES}).")

    out: list[dict] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            _fail("Each line must be an object.")
        kind = str(item.get("kind") or "free_hand").strip().lower()
        if kind not in ("free_hand", "stock"):
            _fail("Unknown line type.")
        if kind == "stock" and not allow_stock:
            _fail("Stock-list lines are not valid here.")

        notes = _text(item.get("notes"), field="Notes", cap=MAX_NOTES)
        # A stable per-line key so the client can tick / edit / remove a line and
        # have the reply's items map back to its own rows.
        key = _text(item.get("key"), field="Line key", cap=64) or f"fh{idx}"

        if kind == "stock":
            mat_id = item.get("material_id")
            try:
                mat_id = int(mat_id)
            except (TypeError, ValueError):
                _fail("A stock line must name a material from the list.")
            mat = db.query(Material).filter_by(id=mat_id).first() if db is not None else None
            if mat is None or not mat.is_active:
                _fail("That material is no longer in the list — remove the line and pick again.")
            description = mat.name
            unit        = mat.unit_of_measure or "each"
            # Current catalogue price, resolved here and never taken from the client.
            unit_price  = float(mat.price_per_unit or 0)
            qty = _number(item.get("qty"), field="Quantity", ceiling=MAX_QTY)
            line_total = round(qty * unit_price, 2)
            total_only = False
        else:
            mat_id      = None
            description = _text(item.get("description"), field="Description",
                                cap=MAX_DESCRIPTION, required=True)
            unit        = _text(item.get("unit"), field="Unit", cap=MAX_UNIT) or "each"
            _raw_qty   = item.get("qty")
            _raw_price = item.get("unit_price")
            _blank = lambda v: v is None or (isinstance(v, str) and not v.strip())
            if allow_total_only and _blank(_raw_qty) and _blank(_raw_price):
                # Lump-sum line: the total is the only figure there is.
                qty        = None
                unit_price = None
                unit       = _text(item.get("unit"), field="Unit", cap=MAX_UNIT) or None
                line_total = _number(item.get("line_total"), field="Line total",
                                     ceiling=MAX_UNIT_PRICE)
                total_only = True
            else:
                if allow_total_only and (_blank(_raw_qty) != _blank(_raw_price)):
                    _fail("Give BOTH a quantity and a unit price, or neither and a "
                          "line total on its own.")
                qty        = _number(_raw_qty, field="Quantity", ceiling=MAX_QTY)
                unit_price = _number(_raw_price, field="Unit price",
                                     ceiling=MAX_UNIT_PRICE)
                line_total = round(qty * unit_price, 2)
                total_only = False

        section_id = item.get("bom_section_id")
        try:
            section_id = int(section_id) if section_id not in (None, "") else None
        except (TypeError, ValueError):
            section_id = None

        out.append({
            "kind":           kind,
            "key":            key,
            "description":    description,
            "qty":            qty,
            "unit":           unit,
            "unit_price":     unit_price,
            "line_total":     line_total,
            "total_only":     total_only,
            "notes":          notes or None,
            "material_id":    mat_id,
            "bom_section_id": section_id,
            "category":       _text(item.get("category"), field="Section", cap=200) or None,
            "excluded":       bool(item.get("excluded")),
        })
    return out


def to_bom_items(lines: list[dict], *, default_category: str,
                 optional_section_ids: set[int] | None = None,
                 section_optional_by_id: dict | None = None) -> list[dict]:
    """Turn normalised lines into synthetic ``bom_items`` for calculate_bom.

    ``optional_section_ids`` is the user's opted-in set (the calculator's
    ``optional_sections_enabled``). A free-hand line attached to an OPTIONAL
    section whose id is not in that set rides through soft-excluded — exactly
    the treatment ``_build_bom_items`` gives the real rows in that section, so
    the free-hand extra follows the section's include/exclude semantics rather
    than inventing its own.
    """
    optional_section_ids   = optional_section_ids or set()
    section_optional_by_id = section_optional_by_id or {}

    items: list[dict] = []
    for ln in lines:
        excluded_reason = None
        if ln["excluded"]:
            excluded_reason = "Excluded by user"
        else:
            sid = ln.get("bom_section_id")
            if (sid is not None and section_optional_by_id.get(sid)
                    and sid not in optional_section_ids):
                excluded_reason = "Optional section not included"

        items.append({
            # No bom_id: a free-hand line has no BOM row and must never look
            # like one to the exclusion stores, which are keyed by integer id.
            "bom_id":              None,
            "bom_section_id":      ln.get("bom_section_id"),
            "free_hand":           True,
            "free_hand_key":       ln["key"],
            "free_hand_kind":      ln["kind"],
            "material_name":       ln["description"],
            "material_code":       "",
            "category_name":       ln.get("category") or default_category,
            "section_is_optional": bool(section_optional_by_id.get(ln.get("bom_section_id"))),
            # The typed quantity — calculate_bom bypasses the formula engine for
            # free-hand lines, so there is no expression to mis-evaluate.
            #
            # A LUMP-SUM line (v1.47 Lane D) has no qty and no unit price, so it
            # rides as quantity 1 x the line total: the money is identical and
            # every downstream total keeps working untouched. `total_only` tells
            # the renderers to print EMPTY qty/unit-price cells rather than the
            # "1" that is sitting here — never show the carrier values.
            "quantity":            1.0 if ln.get("total_only") else ln["qty"],
            "price_per_unit":      (ln.get("line_total") if ln.get("total_only")
                                    else ln["unit_price"]),
            "total_only":          bool(ln.get("total_only")),
            "unit_of_measure":     ln["unit"] or "",
            "waste_percentage":    0,
            "section_multiplier":  1.0,
            "notes":               ln.get("notes"),
            "excluded":            excluded_reason is not None,
            "excluded_reason":     excluded_reason,
        })
    return items


def snapshot(lines: list[dict]) -> list[dict]:
    """The form stored in ``result["input_state"]`` so an edit re-hydrates the
    lines exactly. Stock lines keep their material_id but ALSO keep the price
    that was used, so reopening a saved costing shows what was quoted rather
    than silently re-pricing off a since-changed catalogue."""
    return [
        {
            "kind":           ln["kind"],
            "key":            ln["key"],
            "description":    ln["description"],
            "qty":            ln["qty"],
            "unit":           ln["unit"],
            "unit_price":     ln["unit_price"],
            "line_total":     ln.get("line_total"),
            "total_only":     bool(ln.get("total_only")),
            "notes":          ln.get("notes"),
            "material_id":    ln.get("material_id"),
            "bom_section_id": ln.get("bom_section_id"),
            "category":       ln.get("category"),
            "excluded":       ln["excluded"],
        }
        for ln in lines
    ]


# ── REPAIRS mode ─────────────────────────────────────────────────────────────

def is_repair_mode(body: dict) -> bool:
    """True for the v1.47 REPAIRS surface: a repair quote with NO body behind it.

    Discriminated on the ABSENCE of a trailer_type_id, not on is_repair alone —
    Calculator 2's existing `repair-quote-tick` sets is_repair on an otherwise
    normal body costing, and that path keeps its trailer and must stay on the
    ordinary code path exactly as before.
    """
    return bool(body.get("is_repair")) and not body.get("trailer_type_id")


def repair_fields(body: dict) -> dict:
    """Validate + normalise the repair surface's own inputs.

    TYPE OF REPAIR is required (WO §6). There is no repair-type catalogue in the
    schema yet — verified in §3.0 — so it is free text for now; an admin-managed
    list is a later change that can populate the same field.

    WORK DESCRIPTION is optional. It is stored on the costing's input_state as
    ``repair_scope``, which is the name the downstream React surfaces already
    read (RepairPhasePanel's Scope block, CostingDetail's repair block). It is
    deliberately NOT written to ``repair_phases_json`` — that column is owned by
    the scheduler and holds a LIST of phase entries.
    """
    repair_type = _text(body.get("repair_type"), field="Type of repair",
                        cap=MAX_REPAIR_TYPE, required=True)
    scope = _text(body.get("repair_scope"), field="Work description",
                  cap=MAX_REPAIR_SCOPE)
    return {
        "repair_type": repair_type,
        "repair_scope": scope or None,
        # ── v1.47 Lane D (addendum D8) — the quotation document's header fields.
        # All four live ON THE COSTING (input_state), not on the customer:
        #   * vehicle_registration prints as "Your Reference: Veh reg nr: {v}" and
        #     is per-JOB by nature — the same customer's next repair is another
        #     vehicle.
        #   * delivery_address is captured per quote with NO default: the customer
        #     record carries no address at all (§3.0), and per-quote capture was
        #     ratified over a third migration.
        #   * icb_contact_* prints as "Your Contact" and is ICB's salesperson, not
        #     the customer's contact. The client defaults the NAME from the logged-in
        #     user; `User` has no phone column, so the phone is typed.
        #   * payment_terms prints beside the totals; default "COD".
        "vehicle_registration": _text(body.get("vehicle_registration"),
                                      field="Vehicle registration",
                                      cap=MAX_VEHICLE_REG) or None,
        "delivery_address": _text(body.get("delivery_address"),
                                  field="Delivery address",
                                  cap=MAX_DELIVERY_ADDRESS) or None,
        "icb_contact_name": _text(body.get("icb_contact_name"),
                                  field="Your contact", cap=MAX_CONTACT_NAME) or None,
        "icb_contact_phone": _text(body.get("icb_contact_phone"),
                                   field="Contact telephone",
                                   cap=MAX_CONTACT_PHONE) or None,
        "payment_terms": _text(body.get("payment_terms"), field="Payment terms",
                               cap=MAX_PAYMENT_TERMS) or DEFAULT_PAYMENT_TERMS,
    }
