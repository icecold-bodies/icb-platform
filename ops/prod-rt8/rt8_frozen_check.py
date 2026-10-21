"""RT8 — can every pending quote be edited at its saved prices? READ ONLY; allow-listed reads only (G4).

Runs under the DEPLOYED code's python (PYTHONPATH=/opt/icb-platform/backend) so the replay uses prod's own formula
engine. For every PENDING, not-deleted costing it reads ONLY the columns and result_json keys named below — never a
customer, contact, user, rep, address or description — and reports, by save month and body (quote numbers only):

  * pending, and how many can be frozen (lines complete, totals and variables present);
  * the REPLAY CHECK: every pending body quote replayed from its stored lines — each line's saved formula, price,
    waste and section multiplier at the saved size with the saved variables — must give the stored quantities,
    line costs, then the engine's own category totals and grand total to the cent; a fail names the number of differing lines and the
    largest difference (a quote that fails gets the read-only treatment, ratified default 10);
  * quotes whose saved formulas reference the formula LIBRARY (they cannot change size at saved prices until
    re-priced: the expressions were not stored before v1.62.0);
  * repairs: stock lines, how many have moved in price, how many name a material no longer in the list;
  * N10022/10/2026, named.

Usage (the shell wrapper sets everything): python rt8_frozen_check.py <out-dir>
Env: DATABASE_URL (read-only session forced by PGOPTIONS and asserted here), ICB_NAMED_QUOTES (optional, comma
separated quote numbers to name individually; default N10022/10/2026).
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
from pathlib import Path

# ── the allow-lists: everything this script reads, and nothing else ──────────
COLUMNS = ("id", "quote_number", "status", "trailer_type_id", "created_at", "deleted_at", "is_repair",
           "dimensions_json", "result_json")                     # calculations
JOIN_COLUMNS = ("name",)                                         # trailer_types (the body's name)
MATERIAL_COLUMNS = ("id", "price_per_unit", "is_active")         # materials, by the stock lines' ids
TOP_KEYS = ("items", "category_totals", "grand_total", "materials_total", "body_variables", "global_variables",
            "formula_library_resolved", "formula_library", "chassis", "profit_amount", "selling_price",
            "net_total", "version", "saved_at", "input_state")
ITEM_KEYS = ("bom_id", "category", "material", "formula", "quantity", "unit_price", "waste_pct",
             "section_multiplier", "line_cost", "excluded", "free_hand", "formula_unknown_vars")
CHASSIS_KEYS = ("subtotal",)
INPUT_STATE_KEYS = ("repair_lines", "ui_snapshot")
REPAIR_LINE_KEYS = ("kind", "key", "material_id", "unit_price", "qty")
UI_SNAPSHOT_KEYS = ()                                            # presence only, never its content

#: A key or column that would carry a person is refused at import, whatever list it is on.
_PERSONAL = re.compile(r"customer|contact|user|email|phone|tel|address|rep\b|sales|name$|description|notes|"
                       r"vehicle|registration|delivery|payment", re.I)
#: `material` is a catalogue item's name (a product, not a person); `name` on trailer_types is a body type.
_ALLOWED_NAME_KEYS = {"material", "name"}


def assert_allowlist_clean(*lists: tuple) -> None:
    """Refuse an allow-list that names anything personal-looking (G4). Runs at import and in its own test."""
    for lst in lists:
        for k in lst:
            if k in _ALLOWED_NAME_KEYS:
                continue
            if _PERSONAL.search(str(k)):
                raise RuntimeError(f"allow-list carries a personal-looking key: {k!r}")


assert_allowlist_clean(COLUMNS, JOIN_COLUMNS, MATERIAL_COLUMNS, TOP_KEYS, ITEM_KEYS, CHASSIS_KEYS,
                       INPUT_STATE_KEYS, REPAIR_LINE_KEYS, UI_SNAPSHOT_KEYS)


def pick(obj, allowed) -> dict:
    """Only the allowed keys of a dict; anything else is never read."""
    if not isinstance(obj, dict):
        return {}
    return {k: obj[k] for k in allowed if k in obj}


def read_record(dimensions_json, result_json) -> tuple[dict, dict]:
    """The allow-listed view of a record's two JSON columns."""
    try:
        dims = json.loads(dimensions_json) if dimensions_json else {}
    except Exception:
        dims = {}
    try:
        raw = json.loads(result_json) if result_json else {}
    except Exception:
        raw = {}
    dims = {k: dims.get(k) for k in ("length", "width", "height", "floor_thickness", "panel_thickness",
                                      "insulation_thickness", "num_doors", "num_axles") if isinstance(dims, dict)}
    data = pick(raw, TOP_KEYS)
    data["items"] = [pick(it, ITEM_KEYS) for it in (data.get("items") or []) if isinstance(it, dict)]
    data["chassis"] = pick(data.get("chassis"), CHASSIS_KEYS) if isinstance(data.get("chassis"), dict) else None
    st = pick(data.get("input_state"), INPUT_STATE_KEYS)
    st["repair_lines"] = [pick(ln, REPAIR_LINE_KEYS) for ln in (st.get("repair_lines") or []) if isinstance(ln, dict)]
    st["ui_snapshot"] = isinstance(st.get("ui_snapshot"), dict)      # presence only
    data["input_state"] = st
    return dims, data


SQL = (
    "select c.id, c.quote_number, coalesce(c.status, 'pending'), t.name, to_char(c.created_at, 'YYYY-MM'), "
    "c.is_repair, c.trailer_type_id, c.dimensions_json, c.result_json "
    "from calculations c left join trailer_types t on t.id = c.trailer_type_id "
    "where coalesce(c.status, 'pending') = 'pending' and c.deleted_at is null order by c.id"
)
SQL_MATERIALS = "select id, price_per_unit, is_active from materials where id = any(%s)"
SQL_RO = "select current_setting('transaction_read_only')"
SQL_LIB = "select count(*) from formulas where is_active"


# ── the replay (the core of services/frozen_quote.replay_body, with no DB) ───
LINE_KEYS = ("formula", "unit_price", "waste_pct", "section_multiplier", "quantity", "line_cost")
TOP_NEEDED = ("items", "category_totals", "grand_total", "body_variables", "global_variables")
_TOK = re.compile(r"\{([^{}]+)\}")


def capability(repair: bool, data: dict) -> tuple[bool, str | None]:
    if repair:
        lines = (data.get("input_state") or {}).get("repair_lines")
        return (True, None) if lines else (False, "no repair lines stored")
    for k in TOP_NEEDED:
        if k not in data:
            return False, f"no '{k}'"
    items = data.get("items") or []
    if not items:
        return False, "no lines"
    for it in items:
        if it.get("free_hand"):
            continue
        for k in LINE_KEYS:
            if k not in it:
                return False, f"a line has no '{k}'"
    return True, None


def replay(data: dict, dims: dict, calculate_bom) -> dict:
    body_vars = {str(k): v for k, v in (data.get("body_variables") or {}).items()}
    global_vars = {str(k): v for k, v in (data.get("global_variables") or {}).items()}
    known = {k.strip().upper() for k in body_vars} | {k.strip().upper() for k in global_vars}
    lib_tokens = set()
    bom_items, saved_seq = [], []
    for it in data.get("items") or []:
        if it.get("free_hand"):
            # typed money: the engine takes a free-hand line's quantity and price as they are (no expression), so the
            # stored line replays to its unrounded cost exactly as at save time — and so counts in the totals below
            bom_items.append({
                "bom_id": None, "free_hand": True, "free_hand_key": it.get("free_hand_key"),
                "material_name": "", "category_name": it.get("category") or "Uncategorised",
                "quantity": float(it.get("quantity") or 0), "price_per_unit": float(it.get("unit_price") or 0),
                "waste_percentage": it.get("waste_pct") or 0, "section_multiplier": it.get("section_multiplier") or 1.0,
                "total_only": bool(it.get("total_only")), "unit_of_measure": "", "material_code": "",
                "excluded": bool(it.get("excluded")), "excluded_reason": None,
            })
            saved_seq.append(it)
            continue
        unknown = {str(u).strip().upper() for u in (it.get("formula_unknown_vars") or [])}
        for tok in _TOK.findall(str(it.get("formula") or "")):
            t = tok.strip()
            if t.upper() not in known and t.upper() not in unknown:
                lib_tokens.add(t.lower())
        bom_items.append({
            "bom_id": it.get("bom_id"), "material_name": it.get("material") or "",
            "category_name": it.get("category") or "Uncategorised",
            "formula_expression": it.get("formula") or "1", "waste_percentage": it.get("waste_pct") or 0,
            "price_per_unit": float(it.get("unit_price") or 0), "unit_of_measure": "",
            "material_code": "", "section_multiplier": it.get("section_multiplier") or 1.0,
            "excluded": bool(it.get("excluded")), "excluded_reason": None,
        })
        saved_seq.append(it)
    extra = {}
    lib = data.get("formula_library") if isinstance(data.get("formula_library"), dict) else {}
    source = "none"
    if lib_tokens:
        if lib and all(t in {str(k).lower() for k in lib} for t in lib_tokens):
            source = "stored"
        else:
            # the VALUES at the saved size (exact at that size; a size change needs the expressions)
            extra = {str(k): v for k, v in (data.get("formula_library_resolved") or {}).items()}
            lib = {}
            source = "values"
    res = calculate_bom(bom_items, dims, {**body_vars, **extra}, {str(k).lower(): v for k, v in lib.items()}, global_vars)
    # line by line, in order: the engine keeps its input order, so the n-th result is the n-th stored line
    got = res["items"]
    bad, max_diff = abs(len(got) - len(saved_seq)), 0.0
    for it, s in zip(got, saved_seq):
        dq = abs(float(it["quantity"]) - float(s.get("quantity") or 0))
        dc = abs(float(it["line_cost"]) - float(s.get("line_cost") or 0))
        if dq > 0.00005 or dc > 0.005:
            bad += 1
            max_diff = max(max_diff, dc)
    # the totals the engine's way (formula_engine.calculate_bom): category_totals sum the UNROUNDED line costs and
    # round once, so re-summing the rounded lines drifts by cents on a long quote (prod, 21 Oct: 69 of 69 read
    # FAIL with every line exact). The saved grand_total is that materials total plus the chassis subtotal, rounded
    # once (routers/calculator.py, _apply_chassis_and_margin); materials_total, when stored, is the engine's total.
    cats = {str(k): float(v) for k, v in (res.get("category_totals") or {}).items()}
    saved_cats = {str(k): round(float(v or 0), 2) for k, v in (data.get("category_totals") or {}).items()}
    cat_ok = all(abs(cats.get(k, 0.0) - saved_cats.get(k, 0.0)) <= 0.005 for k in set(cats) | set(saved_cats))
    ch = data.get("chassis") if isinstance(data.get("chassis"), dict) else {}
    mats = float(res.get("grand_total") or 0)
    gt = round(mats + float(ch.get("subtotal") or 0), 2)
    gt_ok = abs(gt - round(float(data.get("grand_total") or 0), 2)) <= 0.005
    if data.get("materials_total") is not None:
        gt_ok = gt_ok and abs(mats - round(float(data.get("materials_total") or 0), 2)) <= 0.005
    return {"pass": bad == 0 and cat_ok and gt_ok, "bad_lines": bad, "max_diff": round(max_diff, 2),
            "cat_ok": cat_ok, "gt_ok": gt_ok, "library": source, "library_tokens": sorted(lib_tokens)}


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    named = [q.strip() for q in os.environ.get("ICB_NAMED_QUOTES", "N10022/10/2026").split(",") if q.strip()]
    from app.formula_engine import calculate_bom     # the DEPLOYED engine
    import psycopg
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg.connect(url, options="-c default_transaction_read_only=on")
    cur = conn.cursor()
    cur.execute(SQL_RO)
    assert cur.fetchone()[0] == "on", "the session is not read-only"
    cur.execute(SQL_LIB)
    n_lib = cur.fetchone()[0]
    cur.execute(SQL)
    rows = cur.fetchall()
    details, mat_ids = [], set()
    for rid, qno, st, body, month, is_repair, tid, dj, rj in rows:
        repair = tid is None
        dims, data = read_record(dj, rj)
        ok, why = capability(repair, data)
        d = {"quote_number": qno, "body": body or ("REPAIR" if repair else "?"), "month": month, "repair": repair,
             "freezable": ok, "reason": why, "snapshot": bool((data.get("input_state") or {}).get("ui_snapshot")),
             "saved_at": data.get("saved_at")}
        if repair:
            stock = [ln for ln in (data.get("input_state") or {}).get("repair_lines") or [] if ln.get("kind") == "stock"]
            d["stock_lines"] = [(ln.get("material_id"), ln.get("unit_price")) for ln in stock]
            mat_ids.update(int(m) for m, _p in d["stock_lines"] if m is not None)
        elif ok:
            try:
                d.update(replay(data, dims, calculate_bom))
            except Exception as e:            # a replay that crashes is a fail, named
                d.update({"pass": False, "bad_lines": -1, "max_diff": None, "error": type(e).__name__})
        details.append(d)
    mats = {}
    if mat_ids:
        cur.execute(SQL_MATERIALS, (sorted(mat_ids),))
        mats = {mid: (price, active) for mid, price, active in cur.fetchall()}
    for d in details:
        if d["repair"]:
            moved = gone = 0
            for mid, price in d.pop("stock_lines"):
                m = mats.get(mid) if mid is not None else None
                if m is None or not m[1]:
                    gone += 1
                elif abs(float(m[0] or 0) - float(price or 0)) > 1e-9:
                    moved += 1
            d.update({"stock_lines": len(d.get("stock_lines", [])) if "stock_lines" in d else 0, "stock_moved": moved, "stock_gone": gone})
    conn.close()

    # ── the summary: counts by month and body, quote numbers only ──────────
    lines = [f"RT8 frozen-quote check (read only) · pending costings {len(rows)} · library formulas {n_lib}", ""]
    groups = collections.OrderedDict()
    for d in details:
        groups.setdefault((d["month"], d["body"]), []).append(d)
    lines.append(f"{'month':<8} {'body':<28} {'pending':>7} {'freezable':>9} {'replay ok':>9} {'fail':>4} {'library':>7} {'snapshot':>8}  not exact (quote numbers)")
    for (month, body), ds in sorted(groups.items()):
        bodies = [d for d in ds if not d["repair"]]
        fails = [d["quote_number"] for d in ds if d["freezable"] and not d["repair"] and not d.get("pass")]
        notfz = [d["quote_number"] for d in ds if not d["freezable"]]
        lib = sum(1 for d in bodies if d.get("library_tokens"))
        lines.append(f"{month:<8} {body[:28]:<28} {len(ds):>7} {sum(1 for d in ds if d['freezable']):>9} "
                     f"{sum(1 for d in bodies if d.get('pass')):>9} {len(fails):>4} {lib:>7} {sum(1 for d in ds if d['snapshot']):>8}  "
                     f"{' '.join(fails + ['(not freezable) ' + q for q in notfz])}")
    reps = [d for d in details if d["repair"]]
    lines += ["", f"repairs: {len(reps)} pending · stock lines {sum(d.get('stock_lines', 0) for d in reps)} · "
                  f"moved in price {sum(d.get('stock_moved', 0) for d in reps)} · material gone {sum(d.get('stock_gone', 0) for d in reps)}"]
    for q in named:
        d = next((x for x in details if x["quote_number"] == q), None)
        if d is None:
            lines.append(f"{q}: not found among pending costings")
        elif d["repair"]:
            lines.append(f"{q}: repair · freezable={d['freezable']} · stock lines {d.get('stock_lines', 0)} moved {d.get('stock_moved', 0)} gone {d.get('stock_gone', 0)}")
        else:
            lines.append(f"{q}: {d['body']} · freezable={d['freezable']} ({d.get('reason') or 'ok'}) · replay "
                         f"{'PASS' if d.get('pass') else 'FAIL'} · differing lines {d.get('bad_lines')} · largest difference "
                         f"{d.get('max_diff')} · library {d.get('library')} {d.get('library_tokens') or ''} · saved_at {d.get('saved_at')}")
    (out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "details.json").write_text(json.dumps(details, indent=1, default=str), encoding="utf-8")
    (out / "inventory.txt").write_text(
        "columns read: calculations(" + ", ".join(COLUMNS) + ") trailer_types(" + ", ".join(JOIN_COLUMNS) + ") "
        "materials(" + ", ".join(MATERIAL_COLUMNS) + ")\nresult_json keys read: " + ", ".join(TOP_KEYS)
        + "\nitem keys read: " + ", ".join(ITEM_KEYS) + "\ninput_state keys read: " + ", ".join(INPUT_STATE_KEYS)
        + " (ui_snapshot: presence only)\nrepair line keys read: " + ", ".join(REPAIR_LINE_KEYS)
        + "\nnever read: customer, contact, user, rep, end-user, address, descriptions, notes\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
