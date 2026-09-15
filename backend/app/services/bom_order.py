"""The order a saved costing's BOM lines are shown in — the calculator's, in one place.

Michael (15 Sep): "when the user views the BOM in a costing the items must be in the same
order as in the costings" — the order the calculator lists them in, which follows the body
type's template (the sheet the BOM was imported from).

Why this is needed at all: /api/approve stores result["items"] sorted by section and then
by MATERIAL NAME A–Z. The calculator never shows that order — calculator.js re-sorts on
screen by each line's BOM row `sort_order` (its default "sheet" view) — so every surface
that rendered the STORED order disagreed with the calculator: the costing page's bill of
materials, the legacy results page and the Excel/Word/PDF exports of a saved costing. Only
the live export preview already matched, through its own inline copy of the rule.

This module is that rule, once, and every one of those surfaces calls it. It orders at READ
time and never rewrites a stored costing, so it applies to costings saved before it existed
and follows the template exactly as the calculator does when the costing is reopened.

The rule is a literal port of calculator.js `sortedGroupEntries` in "sheet" mode, fed the
way `renderBOMWithCosts` feeds it:

  * every line (excluded ones too) gets a key: its BOM row's `sort_order`, looked up by
    `bom_id`; a line with no BOM row behind it (a free-hand line, a repair line, a row since
    deleted) keys on its position in the stored list;
  * lines group by `category` ("Uncategorised" when blank), groups in first-seen order;
  * groups are ordered by the smallest key they contain — ties keep first-seen order;
  * lines inside a group are ordered by key — ties keep their stored order.

Both sorts are stable in JS and in Python, which is what makes the single composite key
below exactly equivalent to the calculator's two-step sort.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Optional

from sqlalchemy.orm import Session

from ..database import BillOfMaterial

UNCATEGORISED = "Uncategorised"


def sort_orders_for_trailer(db: Session, trailer_type_id: Optional[int]) -> dict[int, int]:
    """{bom_id: sort_order} for every BOM row of a body type (rows with no sort_order are
    left out, exactly as calculator.js treats `sort_order == null`)."""
    if trailer_type_id is None:
        return {}
    rows = (db.query(BillOfMaterial.id, BillOfMaterial.sort_order)
              .filter(BillOfMaterial.trailer_type_id == trailer_type_id)
              .all())
    return {r.id: r.sort_order for r in rows if r.sort_order is not None}


def _bom_id(item) -> Optional[int]:
    raw = item.get("bom_id") if isinstance(item, Mapping) else None
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)            # calculator.js compares ids as strings; ints here
    except (TypeError, ValueError):
        return None


def calculator_order(items: Iterable, sort_order_by_bom: Mapping[int, int]) -> list:
    """`items` in the calculator's default ("sheet") BOM order. Returns a new list; the
    items themselves are not copied or modified."""
    items = list(items)
    keys: list = []
    cats: list[str] = []
    first_key: dict[str, object] = {}
    seen_rank: dict[str, int] = {}
    for idx, it in enumerate(items):
        bid = _bom_id(it)
        so = sort_order_by_bom.get(bid) if bid is not None else None
        key = so if so is not None else idx
        cat = (it.get("category") if isinstance(it, Mapping) else None) or UNCATEGORISED
        keys.append(key)
        cats.append(cat)
        if cat not in seen_rank:
            seen_rank[cat] = len(seen_rank)
            first_key[cat] = key
        elif key < first_key[cat]:
            first_key[cat] = key
    order = sorted(range(len(items)),
                   key=lambda i: (first_key[cats[i]], seen_rank[cats[i]], keys[i]))
    return [items[i] for i in order]


def order_result_items(db: Session, result: dict, trailer_type_id: Optional[int]) -> dict:
    """A shallow copy of a saved result with its items in calculator order. The stored
    result is never touched. A result with no items, or a costing with no body type (a
    REPAIRS costing), comes back with its items exactly as stored."""
    if not isinstance(result, dict):
        return result
    items = result.get("items")
    if not isinstance(items, list) or not items or trailer_type_id is None:
        return result
    ordered = dict(result)
    ordered["items"] = calculator_order(items, sort_orders_for_trailer(db, trailer_type_id))
    return ordered
