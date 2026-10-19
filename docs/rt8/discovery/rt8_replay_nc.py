"""READ ONLY (RT8 §3.0): can a saved costing be recomputed from its own result_json alone?

For every costing on the given DB (read-only transaction) the saved lines are replayed through the app's own
formula engine (worktree code) — NO template rows, NO current prices:

    qty  = evaluate(item.formula, geometry(saved dims), saved body_variables + saved global_variables, LIB)
           * item.section_multiplier * (1 + item.waste_pct/100)
    cost = qty * item.unit_price            (excluded lines cost 0)

LIB has two variants:
    expr  — the formula library EXPRESSIONS as they are in the DB today
    saved — the library VALUES the record stored at save time (formula_library_resolved), fed as variables

A line "reproduces" when round(cost, 2) == stored line_cost and round(qty, 4) == stored quantity. Category totals,
grand_total and the selling chain (margin, ratio, discount, net) are re-derived from the replayed lines and compared
to the stored figures to the cent. Prints quote numbers, body names, months and counts only (G4).

Usage: python -I rt8_replay.py <db_name> <out.json>
"""
import collections
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\micge\Documents\icb-platform-rt8\backend")
from app.formula_engine import build_geometry, evaluate_formula  # noqa: E402

import psycopg  # noqa: E402

DB = sys.argv[1]
conn = psycopg.connect(f"postgresql://icb_app:icb_app_dev@localhost:5432/{DB}",
                       options="-c default_transaction_read_only=on")
cur = conn.cursor()
cur.execute("select lower(name), expression from formulas where is_active")
LIB_EXPR = {n: e for n, e in cur.fetchall()}
cur.execute("""
  select c.id, c.quote_number, coalesce(c.status,'pending'), t.name, c.created_at, c.is_repair,
         c.trailer_type_id, c.deleted_at is not null, c.dimensions_json, c.result_json,
         c.discount_kind, c.discount_input, c.net_total
    from calculations c left join trailer_types t on t.id = c.trailer_type_id order by c.id""")


def r2(x):
    return round(x + 0.0, 2)


def replay(res, dims, lib_mode):
    import os
    dims = dict(dims); dims["length"] = float(dims.get("length") or 0) + (0.001 if os.environ.get("RT8_NC") == "len" else 0)
    geo = build_geometry(dims)
    vars_ = {**(res.get("global_variables") or {}), **(res.get("body_variables") or {})}
    lib = LIB_EXPR
    if lib_mode == "saved":
        vars_ = {**{k: v for k, v in (res.get("formula_library_resolved") or {}).items()}, **vars_}
        lib = {}
    bad_lines, cats, n = [], collections.defaultdict(float), 0
    for it in res.get("items") or []:
        n += 1
        if it.get("free_hand"):
            qty = float(it.get("quantity") or 0)
        else:
            qty_raw = evaluate_formula(it.get("formula") or "1", geo, vars_, lib)
            qty = qty_raw * float(it.get("section_multiplier") or 1.0) * (1 + float(it.get("waste_pct") or 0) / 100)
        cost = 0.0 if it.get("excluded") else qty * float(it.get("unit_price") or 0) * (1.001 if os.environ.get("RT8_NC") == "price" else 1)
        if it.get("free_hand") and not it.get("excluded"):
            cost = float(it.get("line_cost") or 0)   # free-hand money is the stored line (typed, lump sums)
        if not it.get("excluded"):
            cats[it.get("category") or "Uncategorised"] += cost
        ok_q = round(qty, 4) == round(float(it.get("quantity") or 0), 4)
        ok_c = r2(cost) == r2(float(it.get("line_cost") or 0))
        if not (ok_q and ok_c):
            bad_lines.append({"bom_id": it.get("bom_id"), "category": it.get("category"),
                              "q_saved": it.get("quantity"), "q_replay": round(qty, 4),
                              "c_saved": it.get("line_cost"), "c_replay": r2(cost)})
    cat_ok = all(r2(cats.get(k, 0.0)) == r2(float(v)) for k, v in (res.get("category_totals") or {}).items())
    mats = sum(cats.values())
    ch = res.get("chassis") or {}
    gt = mats + float(ch.get("subtotal") or 0) if ch else mats
    gt_ok = r2(gt) == r2(float(res.get("grand_total") or 0))
    return {"lines": n, "bad": bad_lines, "cat_ok": cat_ok, "gt_ok": gt_ok, "gt_replay": r2(gt)}


def money_chain(res, rec_disc_kind, rec_disc_input, rec_net):
    """margin / ratio / discount re-derived from the stored grand_total — the arithmetic the server uses."""
    gt = float(res.get("grand_total") or 0)
    pm = float(res.get("profit_margin") or 0)
    pa = r2(gt * pm / 100) if pm > 0 else 0.0
    wm = gt + pa
    rv = res.get("ratio_value")
    sp = r2(wm / float(rv)) if rv and 0 < float(rv) <= 1 else wm
    kind = res.get("discount_kind")
    raw = float(res.get("discount_input") or 0)
    base = float(res.get("selling_price") or res.get("grand_total") or 0)
    da = r2(base * min(max(raw, 0), 100) / 100) if kind == "percent" and raw > 0 else (
        r2(min(raw, base)) if kind == "amount" and raw > 0 else 0.0)
    net = r2(base - da)
    ok = (r2(pa) == r2(float(res.get("profit_amount") or 0)) and
          (res.get("selling_price") is None or r2(sp) == r2(float(res["selling_price"]))) and
          (res.get("net_total") is None or net == r2(float(res["net_total"]))))
    return ok


rows = cur.fetchall()
out, summary = [], collections.Counter()
for rid, qno, st, body, created, is_rep, tid, deleted, dj, rj, dk, di, net in rows:
    res = json.loads(rj) if isinstance(rj, str) else (rj or {})
    dims = json.loads(dj) if dj else {}
    month = created.strftime("%Y-%m") if created else "none"
    rec = {"id": rid, "qno": qno, "status": st, "deleted": deleted, "body": body, "month": month,
           "repair": bool(is_rep), "trailerless": tid is None}
    missing = [k for k in ("items", "category_totals", "grand_total", "body_variables", "global_variables",
                           "formula_library_resolved") if k not in res]
    item_missing = sorted({k for it in res.get("items") or [] for k in
                           ("formula", "quantity", "unit_price", "waste_pct", "section_multiplier", "line_cost",
                            "category", "excluded") if k not in it})
    rec["missing_top"], rec["missing_item"] = missing, item_missing
    if tid is not None:
        for mode in ("expr", "saved"):
            rp = replay(res, dims, mode)
            rec[mode] = {"lines": rp["lines"], "bad_lines": len(rp["bad"]), "cat_ok": rp["cat_ok"],
                         "gt_ok": rp["gt_ok"], "sample_bad": rp["bad"][:3]}
    rec["money_chain_ok"] = money_chain(res, dk, di, net)
    out.append(rec)
    if not deleted and st == "pending" and tid is not None:
        exact = rec["saved"]["bad_lines"] == 0 and rec["saved"]["cat_ok"] and rec["saved"]["gt_ok"]
        summary["pending_body"] += 1
        summary["pending_body_exact_saved_lib"] += exact
        summary["pending_body_exact_expr_lib"] += (rec["expr"]["bad_lines"] == 0 and rec["expr"]["gt_ok"])
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print(dict(summary))
for r in out:
    if r["trailerless"]:
        print(f"{r['qno']:<16} {r['status']:<9} {'DEL' if r['deleted'] else '   '} REPAIR  money_ok={r['money_chain_ok']} miss={r['missing_top']}")
        continue
    print(f"{r['qno']:<16} {r['status']:<9} {'DEL' if r['deleted'] else '   '} {r['body'] or '':<16} {r['month']}  "
          f"lines={r['saved']['lines']:<4} saved-lib bad={r['saved']['bad_lines']:<3} cat={r['saved']['cat_ok']!s:<5} "
          f"gt={r['saved']['gt_ok']!s:<5} | expr-lib bad={r['expr']['bad_lines']:<3} gt={r['expr']['gt_ok']!s:<5} "
          f"money={r['money_chain_ok']} miss={r['missing_top']}{r['missing_item']}")
