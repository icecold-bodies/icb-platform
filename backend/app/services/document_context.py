"""Shared costing-document context (v1.44 preview/export formats — R2/R4).

One builder produces the layout-neutral ``doc_ctx`` that ALL three renderers
(xlsx / docx / pdf, in routers/exports.py) draw from, for BOTH the live
preview and the approved export. Layout parity across formats is therefore a
property of this module, and the renderers stay dumb.

Document order (ratified R2):
  1. heading            — "Testing — {body} ({len} m)"  /  "{quote} — {body} ({len} m)"
  2. client_name        — selected customer, or "— no client selected —" on previews
  2b. end_user_lines    — WO v1.47 lane B: when the costing snapshotted an END USER
                          (ICB's customer is often a reseller and the body is FOR
                          someone else), "End user: {company}" and, when present,
                          "End user contact: {name}", directly under the client.
                          Empty list when there is none — the renderers then emit
                          NOTHING, so unaffected documents keep their exact layout.
  3. spec_pairs + spec_options — dimensions block then body-options block
  4. category_totals    — moved ABOVE the price summary and line items
  5. price_rows         — Materials Cost · Margin ({n}%) · Ratio ({r}) · TOTAL COST,
                          one "TOTAL COST @ {r}" line per ratio when several are
                          selected. NO cost per m². A total never combines ratios.
  6. items              — only when detail == "items".

The ratio/margin FORMULA is never reimplemented here: every total is produced
by calling routers.calculator._apply_chassis_and_margin on the record's grand
total (late import — house idiom, cf. exports.py's _derive_body_options_display
usage), so a document total equals the on-screen total for that ratio by
construction.
"""

# Canonical ratio dropdown (calculator.html / calculator2.html #f-ratio).
# The templates render this list as <option> markup; test_preview_formats.py
# asserts template ↔ constant parity so the two sources cannot drift.
RATIO_OPTIONS: list[tuple[float, str]] = [
    (0.3, "30%"), (0.325, "32.5%"), (0.35, "35%"), (0.375, "37.5%"),
    (0.4, "40%"), (0.425, "42.5%"), (0.45, "45%"), (0.475, "47.5%"),
    (0.5, "50%"), (0.525, "52.5%"), (0.55, "55%"), (0.575, "57.5%"),
    (0.6, "60%"), (0.625, "62.5%"), (0.65, "65%"), (0.675, "67.5%"),
    (0.7, "70%"),
]

from . import zero_rule_note

VALID_DETAILS = ("totals", "items")
VALID_FORMATS = ("excel", "word", "pdf")

NO_CLIENT_PLACEHOLDER = "— no client selected —"


def ratio_label(value: float) -> str:
    """"55%" / "32.5%" — matches the dropdown's option text (never "55.0%")."""
    return f"{round(float(value) * 1000) / 10:g}%"


def format_length(value) -> str | None:
    """Body length for display: one decimal where needed — "7.5", "13.6", "8"."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return f"{round(v * 10) / 10:g}"


def body_type_with_length(name: str, length) -> str:
    """"{body type} ({length} m)" — the R6 display concat; plain name when no length."""
    s = format_length(length)
    return f"{name} ({s} m)" if s else name


def parse_ratios(raw) -> list[float]:
    """Normalize a client ratio selection (list of numbers, or "0.35,0.5" string)
    into a sorted, deduped list of divisors in (0, 1]. Unknown/invalid entries
    are dropped — an empty result means "no ratio" (totals stop at margin)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [p for p in raw.split(",") if p.strip()]
    out = set()
    for item in raw:
        try:
            v = float(item)
        except (TypeError, ValueError):
            continue
        if 0 < v <= 1:
            out.add(round(v, 4))
    return sorted(out)


def build_price_rows(result: dict, ratios: list[float], db=None) -> list[dict]:
    """The PRICE SUMMARY rows (R2.5), replicating the costings page minus per-m².

    ``result`` is a calculate/approve result dict (grand_total already includes
    chassis when enabled; profit_margin/profit_amount as saved). ``ratios`` is
    the user's selection from the options dialog.

    Every total is computed by _apply_chassis_and_margin — one call per ratio —
    so each "TOTAL COST @ r" equals (Materials Cost + Margin) ÷ r exactly as the
    page computes it, and never combines two ratios.

    Row shape: {"label", "amount", "kind"} with kind ∈ "row" (plain),
    "add" (green + line), "total" (emphasised band).
    """
    from ..routers.calculator import _apply_chassis_and_margin  # late: routers→services one-way otherwise


    rows: list[dict] = []
    grand = float(result.get("grand_total") or 0)
    mats = result.get("materials_total")
    chassis = result.get("chassis") or {}

    rows.append({"label": "Materials Cost",
                 "amount": float(mats) if mats is not None else grand,
                 "kind": "row"})
    if chassis.get("items"):
        rows.append({"label": (f"Chassis ({chassis.get('axle_count')}-axle · "
                               f"{chassis.get('tyre_count')} tyres)"),
                     "amount": float(chassis.get("subtotal") or 0), "kind": "row"})
        rows.append({"label": "Body + Chassis", "amount": grand, "kind": "row"})

    margin_pct = float(result.get("profit_margin") or 0)

    # One canonical-function call per selected ratio (chassis is already inside
    # grand_total, and the body passed here has no "chassis" key, so nothing is
    # double-added). Margin amount is identical across calls by construction.
    calcs = [
        _apply_chassis_and_margin(
            {"grand_total": grand},
            {"profit_margin": margin_pct, "ratio_value": r, "ratio_label": ratio_label(r)},
            db,
        )
        for r in ratios
    ]
    base = calcs[0] if calcs else _apply_chassis_and_margin(
        {"grand_total": grand}, {"profit_margin": margin_pct}, db)
    profit_amount = float(base.get("profit_amount") or 0)
    with_margin = grand + profit_amount

    if profit_amount > 0:
        rows.append({"label": f"Margin ({margin_pct:g}%)",
                     "amount": profit_amount, "kind": "add"})

    if len(calcs) == 1:
        calc = calcs[0]
        if calc.get("ratio_amount"):
            rows.append({"label": f"Ratio ({calc.get('ratio_label')})",
                         "amount": float(calc["ratio_amount"]), "kind": "add"})
        rows.append({"label": "TOTAL COST",
                     "amount": float(calc.get("selling_price") or with_margin),
                     "kind": "total"})
        # Discount rows replicate the page only when the selected ratio IS the
        # saved one (the saved discount/net were computed against that total).
        saved_ratio = result.get("ratio_value")
        disc = float(result.get("discount_amount") or 0)
        if disc > 0 and saved_ratio is not None and abs(float(saved_ratio) - ratios[0]) < 1e-9:
            label = (f"Discount ({result.get('discount_input'):g}%)"
                     if result.get("discount_kind") == "percent" else "Discount")
            rows.append({"label": label, "amount": -disc, "kind": "add"})
            rows.append({"label": "NET TOTAL",
                         "amount": float(result.get("net_total") or 0), "kind": "total"})
    elif calcs:
        for r, calc in zip(ratios, calcs):
            rows.append({"label": f"TOTAL COST @ {calc.get('ratio_label') or ratio_label(r)}",
                         "amount": float(calc.get("selling_price") or with_margin),
                         "kind": "total"})
    else:
        # No ratio ticked: the total is materials + margin, exactly the page
        # with "— None —" selected.
        rows.append({"label": "TOTAL COST", "amount": with_margin, "kind": "total"})

    return rows


def build_end_user_lines(company, contact_name) -> list[str]:
    """The end-user document lines (WO v1.47 lane B, Default 5). ONE definition, shared by
    xlsx / docx / pdf so the wording cannot drift between formats.

    No company → an empty list, and every renderer emits nothing at all: no blank line, no
    empty label, layout byte-identical to pre-WO documents. A contact person without a
    company is not renderable on its own (the end user IS the company), so it is dropped."""
    company = str(company or "").strip()
    if not company:
        return []
    lines = [f"End user: {company}"]
    contact_name = str(contact_name or "").strip()
    if contact_name:
        lines.append(f"End user contact: {contact_name}")
    return lines


def build_doc_ctx(*, mode: str, heading: str, sub: str, client_name: str,
                  spec_pairs: list, spec_options: list, result: dict,
                  ratios: list[float], detail: str, db=None,
                  end_user_company=None, end_user_contact_name=None,
                  heading_color: str = "58A6FF", is_repair: bool = False,
                  section_totals: dict | None = None,
                  highlight: bool = False,
                  override_materials: set | None = None,
                  recently_updated_mats: set | None = None,
                  generated_at: str = "") -> dict:
    """Assemble the renderer-neutral document context. ``result`` must already
    be exclusion-stripped (and, for previews, screen-ordered) by the caller."""
    items = list(result.get("items") or [])
    optional_cats = {it["category"] for it in items if it.get("section_is_optional")}
    include_items = detail == "items"

    cat_totals = [
        (cat, float(total or 0), cat in optional_cats)
        for cat, total in (result.get("category_totals") or {}).items()
    ]

    if section_totals is None:
        # Literal per-section totals summed from the (stripped) items — =SUM
        # formulas carry no cached value in openpyxl output (Michael 4 Aug).
        section_totals = {}
        for it in items:
            try:
                section_totals[it["category"]] = (
                    section_totals.get(it["category"], 0.0) + float(it.get("line_cost") or 0))
            except (KeyError, TypeError, ValueError):
                continue

    return {
        "mode": mode,
        "heading": heading,
        "heading_color": heading_color,
        "sub": sub,
        "client_name": client_name or NO_CLIENT_PLACEHOLDER,
        "end_user_lines": build_end_user_lines(end_user_company, end_user_contact_name),
        "spec_pairs": spec_pairs,
        "spec_options": spec_options,
        "category_totals": cat_totals,
        "price_rows": build_price_rows(result, ratios, db),
        # Length-pinned zero rule (e.g. 3.2 m plywood+glue): one bold red line
        # under the price summary in every format. None when no guarded row
        # matches this result's length — the renderers then emit nothing, so
        # unaffected documents stay byte-identical.
        "zero_rule_note": zero_rule_note(result),
        "include_items": include_items,
        "items": items if include_items else [],
        "optional_cats": optional_cats,
        "chassis": result.get("chassis") or None,
        "section_totals": section_totals,
        "is_repair": is_repair,
        "highlight": bool(highlight and include_items),
        "override_materials": override_materials or set(),
        "recently_updated_mats": recently_updated_mats or set(),
        "generated_at": generated_at,
    }
