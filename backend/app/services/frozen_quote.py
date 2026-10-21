"""RT8 (v1.62.0) — a re-opened quote is the saved quote.

Michael's rule (19 Oct 2026): when a quote is saved, an exact copy is saved, and anyone editing that quote gets that
exact copy back. Today's template and prices enter a saved quote only when a user asks for them ("Update to today's
prices"), after seeing line by line what would change.

The mechanism (RT8_RULING_1, option c): **the saved lines are the quote's basis.** A frozen calculation replays the
lines stored in the record's ``result_json`` — each line's saved formula, saved unit price, saved waste and section
multiplier — at the user's new size, margin, ratio and discount, with the quote's own saved variables. No template
row and no current price is read. Body options and the chassis are therefore locked while a quote is frozen (the
options that were NOT quoted were never stored); changing them goes through re-pricing, which saves as a new
revision only.

One function serves the screen (``/api/calculate``) and the save (``/api/approve``): the server loads the stored
record itself and never trusts a client figure. The save refuses when its result differs from what the screen shows.

Discovery (RT8_RETURN_1 §2): every pending body costing on dev replays from its own result_json to the cent, and the
check was proven to catch a 1 mm size change and a 0.1 % price change.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..database import Formula, GlobalVariable, Material
from ..formula_engine import _VAR_TOKEN_RE, calculate_bom

#: What a stored line must carry to be replayed (present on every record since the 2 Jun 2026 import).
LINE_KEYS = ("formula", "unit_price", "waste_pct", "section_multiplier", "quantity", "line_cost")
#: What the stored result must carry at the top level.
TOP_KEYS = ("items", "category_totals", "grand_total", "body_variables", "global_variables")
#: The geometry inputs a size change is judged on (build_geometry reads exactly these).
DIM_KEYS = ("length", "width", "height", "floor_thickness", "panel_thickness", "insulation_thickness",
            "num_doors", "num_axles")
#: Saves refuse when the server's figure and the screen's differ by more than this (one cent, with room for the
#: screen's unrounded intermediate).
CENT = 0.015


class FrozenError(Exception):
    """A frozen calculation that cannot be done at saved prices. ``code`` is machine-readable; ``message`` is for the
    user and always names the way out (re-pricing)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stored(rec) -> dict:
    """The record's result_json as a dict ({} when missing or unreadable)."""
    try:
        data = json.loads(rec.result_json) if rec.result_json else {}
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def dims_of(rec) -> dict:
    try:
        d = json.loads(rec.dimensions_json) if rec.dimensions_json else {}
    except Exception:
        d = {}
    return d if isinstance(d, dict) else {}


def capability(rec, data: dict) -> tuple[bool, str | None]:
    """Can this record be edited at saved prices? (ok, reason-when-not). A REPAIR needs its stored lines; a body
    costing needs its lines with their formula, price, waste, multiplier and money, plus its totals and variables
    (ratified default 10: a record that cannot be frozen opens read-only, with re-pricing as the way to edit it)."""
    if rec.trailer_type_id is None:
        lines = (data.get("input_state") or {}).get("repair_lines")
        if not isinstance(lines, list) or not lines:
            return False, "its repair lines were not stored"
        return True, None
    for k in TOP_KEYS:
        if k not in data:
            return False, f"the saved copy has no '{k}'"
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return False, "the saved copy has no lines"
    for it in items:
        if not isinstance(it, dict):
            return False, "a saved line is unreadable"
        if it.get("free_hand"):
            continue
        for k in LINE_KEYS:
            if k not in it:
                return False, f"a saved line has no '{k}'"
    return True, None


# ── replaying a BODY costing ─────────────────────────────────────────────────

def _excluded_by(it: dict) -> str | None:
    """Why a stored line was out: 'condition' | 'user' | 'optional_section' | None. Records saved before v1.59.1
    carry only the reason text, so it is read back the way calculate_bom wrote it."""
    if not it.get("excluded"):
        return None
    by = it.get("excluded_by")
    if by:
        return str(by)
    reason = str(it.get("excluded_reason") or "")
    if reason == "Excluded by user":
        return "user"
    if reason.startswith("Optional section"):
        return "optional_section"
    return "condition"


def _ids(raw) -> set[int]:
    out = set()
    for x in raw or []:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _same_dims(a: dict, b: dict) -> bool:
    for k in DIM_KEYS:
        try:
            if abs(float(a.get(k) or 0) - float(b.get(k) or 0)) > 1e-9:
                return False
        except (TypeError, ValueError):
            return False
    return True


def library_tokens(items: list, body_vars: dict, global_vars: dict) -> set[str]:
    """The {TOKEN}s the saved formulas reference that are NOT the quote's variables — i.e. formula-library names
    (lower-cased, as get_formula_lib keys them). Tokens the engine flagged unknown at save time are not library
    names either: they resolved to 0 then and resolve to 0 now."""
    known = {str(k).strip().upper() for k in (body_vars or {})} | {str(k).strip().upper() for k in (global_vars or {})}
    out: set[str] = set()
    for it in items:
        if not isinstance(it, dict) or it.get("free_hand"):
            continue
        unknown = {str(u).strip().upper() for u in (it.get("formula_unknown_vars") or [])}
        for tok in _VAR_TOKEN_RE.findall(str(it.get("formula") or "")):
            t = tok.strip()
            if t.upper() in known or t.upper() in unknown:
                continue
            out.add(t.lower())
    return out


def resolve_library(data: dict, dims: dict, dims_saved: dict, tokens: set[str]) -> tuple[dict, dict, str]:
    """(library expressions, extra variables, source) for a frozen replay.

    * no library token in any saved formula → nothing needed ('none');
    * the record stores the EXPRESSIONS used (``formula_library``, every save from v1.62.0) → use them ('stored');
    * the record only stores the VALUES at the saved size (``formula_library_resolved``) and the size is unchanged →
      feed the values as variables ('values');
    * otherwise the size cannot change at saved prices → FrozenError (RT8_RULING_1: never today's expression)."""
    if not tokens:
        return {}, {}, "none"
    lib = data.get("formula_library")
    if isinstance(lib, dict) and all(t in {str(k).lower() for k in lib} for t in tokens):
        return {str(k).lower(): v for k, v in lib.items()}, {}, "stored"
    resolved = data.get("formula_library_resolved")
    if isinstance(resolved, dict) and _same_dims(dims, dims_saved):
        return {}, {str(k): v for k, v in resolved.items() if str(k).lower() in tokens}, "values"
    raise FrozenError(
        "frozen_library_missing",
        "This quote was saved before its formula library was stored, so its size cannot be changed at saved "
        "prices. Click Update to today's prices to edit it (it saves as a new revision).")


def replay_body(db, rec, data: dict, body: dict) -> dict:
    """The frozen calculation for a BODY costing: the stored lines at the payload's size / margin / ratio / discount
    / price overrides / optional-extras choices / free-hand lines. Same result shape as /api/calculate."""
    from ..routers.calculator import (_append_free_hand_lines, _apply_chassis_and_margin, _apply_discount,
                                      _attach_formula_debug)   # late: routers -> services is the one-way import

    dims_saved = dims_of(rec)
    dims = body.get("dimensions") if isinstance(body.get("dimensions"), dict) and body.get("dimensions") else dims_saved
    overrides = {str(k): float(v) for k, v in (body.get("overrides") or {}).items()}
    user_excluded = _ids(body.get("user_excluded_bom_ids"))
    enabled = _ids(body.get("optional_sections_enabled"))
    saved_over = {str(k): v for k, v in (data.get("overrides_by_bom") or {}).items()}
    snap = ((data.get("input_state") or {}).get("ui_snapshot") or {})
    snap_over = snap.get("price_overrides") if isinstance(snap.get("price_overrides"), dict) else {}

    def price_for(it: dict) -> float:
        bid = str(it.get("bom_id"))
        if bid in overrides:
            return overrides[bid]
        if bid in saved_over:
            # the saved quote carried an override the client no longer sends: the user reverted it, so the line
            # goes back to the price the override had replaced (kept in the UI snapshot), else stays as saved
            orig = (snap_over.get(bid) or {}).get("originalPrice") if isinstance(snap_over.get(bid), dict) else None
            if orig is not None:
                try:
                    return float(orig)
                except (TypeError, ValueError):
                    pass
        return float(it.get("unit_price") or 0)

    bom_items = []
    for it in data.get("items") or []:
        if not isinstance(it, dict) or it.get("free_hand"):
            continue       # free-hand lines ride the payload (typed, never re-priced) and are appended below
        by = _excluded_by(it)
        bid = it.get("bom_id")
        if by == "condition":
            excluded, reason = True, it.get("excluded_reason")        # options are locked: a condition stays as saved
        elif bid is not None and int(bid) in user_excluded:
            excluded, reason, by = True, "Excluded by user", "user"
        elif it.get("section_is_optional") and (it.get("bom_section_id") is None
                                                or int(it["bom_section_id"]) not in enabled):
            excluded, reason, by = True, "Optional section not enabled", "optional_section"
        else:
            excluded, reason, by = False, None, None
        bom_items.append({
            "bom_id":              bid,
            "material_name":       it.get("material") or "",
            "category_name":       it.get("category") or "Uncategorised",
            "bom_section_id":      it.get("bom_section_id"),
            "section_is_optional": bool(it.get("section_is_optional")),
            "formula_expression":  it.get("formula") or "1",
            "waste_percentage":    it.get("waste_pct") or 0,
            "price_per_unit":      price_for(it),
            "unit_of_measure":     it.get("unit") or "each",
            "material_code":       it.get("material_code") or "",
            "section_multiplier":  it.get("section_multiplier") or 1.0,
            "excluded":            excluded,
            "excluded_reason":     reason,
            "excluded_by":         by,
        })
    free_hand_lines = _append_free_hand_lines(bom_items, body, body.get("optional_sections_enabled") or [])

    body_vars = {str(k): v for k, v in (data.get("body_variables") or {}).items()}
    global_vars = {str(k): v for k, v in (data.get("global_variables") or {}).items()}
    tokens = library_tokens(data.get("items") or [], body_vars, global_vars)
    lib, extra_vars, source = resolve_library(data, dims, dims_saved, tokens)
    result = calculate_bom(bom_items, dims, {**body_vars, **extra_vars}, lib, global_vars)

    ch = data.get("chassis")
    if isinstance(ch, dict) and ch.get("subtotal") is not None:
        result["chassis"] = ch                                  # frozen: the chassis as it was priced
        result["materials_total"] = result["grand_total"]
        result["grand_total"] = round(result["grand_total"] + float(ch.get("subtotal") or 0), 2)
    result = _apply_chassis_and_margin(result, {**body, "chassis": None}, db)
    result = _apply_discount(result, body)
    _attach_formula_debug(result, body_vars, lib, global_vars)
    if source == "values":
        result["formula_library_resolved"] = dict(data.get("formula_library_resolved") or {})
    result["frozen"] = {
        "record_id": rec.id, "quote_number": rec.quote_number,
        "version": int(data.get("version", 1) or 1), "saved_at": data.get("saved_at"), "library": source,
    }
    result["_free_hand_lines"] = free_hand_lines      # for the save's input_state; stripped before storing
    result["rule_breaches"] = []
    result["rule_unclassified"] = []
    return result


def frozen_input_state(data: dict, body: dict, result: dict, overrides: dict, override_reasons: dict) -> dict:
    """A frozen save's input_state: the saved one, with what the user may change in frozen mode updated."""
    from ..services import free_hand as fh
    st = dict(data.get("input_state") or {})
    saved_over = {str(k): v for k, v in (data.get("overrides_by_bom") or {}).items()}
    st["overrides"] = {**saved_over, **overrides} if overrides else dict(overrides)
    st["override_reasons"] = {**(st.get("override_reasons") or {}), **override_reasons}
    st["user_excluded_bom_ids"] = body.get("user_excluded_bom_ids") or []
    st["optional_sections_enabled"] = body.get("optional_sections_enabled") or []
    st["free_hand_lines"] = fh.snapshot(result.pop("_free_hand_lines", []) or [])
    st["profit_margin"] = float(body.get("profit_margin", 0) or 0)
    st["ratio_value"] = body.get("ratio_value")
    st["ratio_label"] = body.get("ratio_label")
    if isinstance(body.get("ui_snapshot"), dict):
        st["ui_snapshot"] = body.get("ui_snapshot")
    return st


# ── replaying a REPAIR ───────────────────────────────────────────────────────

def frozen_repair_lines(data: dict) -> dict[str, dict]:
    """{line key: saved line} for the STOCK lines of a saved repair — the prices they were quoted at."""
    out = {}
    for ln in (data.get("input_state") or {}).get("repair_lines") or []:
        if isinstance(ln, dict) and ln.get("kind") == "stock" and ln.get("key"):
            out[str(ln["key"])] = ln
    return out


def gone_material_lines(db, frozen: dict[str, dict]) -> dict[str, dict]:
    """The subset whose material is no longer in the list (or inactive): re-pricing keeps these at the saved price,
    because today has no price for them."""
    out = {}
    for key, ln in frozen.items():
        mid = ln.get("material_id")
        mat = db.query(Material).filter_by(id=int(mid)).first() if mid not in (None, "") else None
        if mat is None or not mat.is_active:
            out[key] = ln
    return out


# ── the live reads a re-price and its save share ─────────────────────────────

def active_library(db) -> dict[str, str]:
    return {f.name.lower(): f.expression for f in db.query(Formula).filter_by(is_active=True).all()}


def active_globals(db) -> dict[str, float]:
    return {gv.name: gv.value for gv in db.query(GlobalVariable).all()}


# ── the comparison ("View changes") ──────────────────────────────────────────

def _r2(x) -> float:
    return round(float(x or 0) + 0.0, 2)


def selling_chain(result: dict) -> dict:
    """Cost → + margin → ÷ ratio = total → − discount = net, read off a result (stored or fresh)."""
    gt = float(result.get("grand_total") or 0)
    pa = float(result.get("profit_amount") or 0)
    with_margin = gt + pa
    selling = float(result.get("selling_price")) if result.get("selling_price") is not None else with_margin
    net = float(result.get("net_total")) if result.get("net_total") is not None else selling
    return {"materials_total": _r2(result.get("materials_total") if result.get("materials_total") is not None else gt),
            "grand_total": _r2(gt), "profit_amount": _r2(pa), "selling_price": _r2(selling),
            "discount_amount": _r2(result.get("discount_amount")), "net_total": _r2(net)}


def _line_key(it: dict):
    if it.get("free_hand"):
        return ("fh", str(it.get("free_hand_key") or it.get("material") or ""))
    bid = it.get("bom_id")
    return ("bom", int(bid)) if bid is not None else ("name", str(it.get("category") or ""), str(it.get("material") or ""))


def _line_view(it: dict) -> dict:
    return {"quantity": round(float(it.get("quantity") or 0), 4), "unit_price": _r2(it.get("unit_price")),
            "line_cost": _r2(it.get("line_cost")), "material": it.get("material"), "category": it.get("category"),
            "unit": it.get("unit")}


def compare(saved: dict, today: dict, *, today_bom_ids: set[int] | None = None,
            new_options: list | None = None) -> dict:
    """Line by line, section by section and in total: what re-pricing would change. Removed lines whose BOM row no
    longer exists are told apart ('removed from template') from lines today's options leave out ('removed')."""
    s_items = [it for it in (saved.get("items") or []) if isinstance(it, dict) and not it.get("excluded")]
    t_items = [it for it in (today.get("items") or []) if isinstance(it, dict) and not it.get("excluded")]
    s_by = {_line_key(it): it for it in s_items}
    t_by = {_line_key(it): it for it in t_items}
    lines = []
    for k, it in s_by.items():
        if k in t_by:
            continue
        kind = "removed"
        if k[0] == "bom" and today_bom_ids is not None and k[1] not in today_bom_ids:
            kind = "removed_from_template"
        lines.append({"kind": kind, "bom_id": it.get("bom_id"), "category": it.get("category"),
                      "material": it.get("material"), "saved": _line_view(it), "today": None,
                      "delta_cost": -_r2(it.get("line_cost"))})
    for k, it in t_by.items():
        if k in s_by:
            continue
        lines.append({"kind": "added", "bom_id": it.get("bom_id"), "category": it.get("category"),
                      "material": it.get("material"), "saved": None, "today": _line_view(it),
                      "delta_cost": _r2(it.get("line_cost"))})
    unchanged = 0
    for k, s in s_by.items():
        t = t_by.get(k)
        if t is None:
            continue
        sv, tv = _line_view(s), _line_view(t)
        q = abs(sv["quantity"] - tv["quantity"]) > 1e-9
        p = abs(sv["unit_price"] - tv["unit_price"]) > 1e-9
        renamed = (s.get("material") or "") != (t.get("material") or "")
        moved = (s.get("category") or "") != (t.get("category") or "")
        if not (q or p or renamed or moved):
            unchanged += 1
            continue
        kind = "qty_price" if (q and p) else "qty" if q else "price" if p else "renamed" if renamed else "moved"
        lines.append({"kind": kind, "bom_id": s.get("bom_id"), "category": s.get("category"),
                      "material": s.get("material"), "today_material": t.get("material") if renamed else None,
                      "today_category": t.get("category") if moved else None,
                      "saved": sv, "today": tv, "delta_cost": _r2(tv["line_cost"] - sv["line_cost"])})
    order = {"removed_from_template": 0, "removed": 1, "added": 2, "qty_price": 3, "price": 4, "qty": 5,
             "renamed": 6, "moved": 7}
    lines.sort(key=lambda ln: (str(ln.get("category") or ""), order.get(ln["kind"], 9), str(ln.get("material") or "")))

    s_tot = {str(k): _r2(v) for k, v in (saved.get("category_totals") or {}).items()}
    t_tot = {str(k): _r2(v) for k, v in (today.get("category_totals") or {}).items()}
    seen, sections = set(), []
    for cat in list(s_tot) + [c for c in t_tot if c not in s_tot]:
        if cat in seen:
            continue
        seen.add(cat)
        a, b = s_tot.get(cat, 0.0), t_tot.get(cat, 0.0)
        if abs(a - b) > 1e-9:
            sections.append({"category": cat, "saved_total": a, "today_total": b, "delta": _r2(b - a)})

    sc, tc = selling_chain(saved), selling_chain(today)
    totals = {"saved": sc, "today": tc,
              "delta_cost": _r2(tc["grand_total"] - sc["grand_total"]),
              "delta_selling": _r2(tc["selling_price"] - sc["selling_price"]),
              "delta_net": _r2(tc["net_total"] - sc["net_total"])}
    counts = {"removed": sum(1 for ln in lines if ln["kind"] in ("removed", "removed_from_template")),
              "removed_from_template": sum(1 for ln in lines if ln["kind"] == "removed_from_template"),
              "added": sum(1 for ln in lines if ln["kind"] == "added"),
              "qty": sum(1 for ln in lines if ln["kind"] in ("qty", "qty_price")),
              "price": sum(1 for ln in lines if ln["kind"] in ("price", "qty_price")),
              "renamed": sum(1 for ln in lines if ln.get("today_material") is not None),
              "unchanged": unchanged}
    opts = [o for o in (new_options or []) if isinstance(o, dict)]
    blocked = [str(o.get("label") or "a new option") + ": pick one before Apply"
               for o in opts if o.get("chosen") in (None, "")]
    return {"lines": lines, "sections": sections, "totals": totals, "counts": counts,
            "new_options": opts, "blocked": blocked}


def strip_working_keys(result: dict) -> None:
    """Keys a replay carries for the save path only — never stored, never sent."""
    result.pop("_free_hand_lines", None)
