"""Summarise saved vs today's re-cost per quote (from rt8_diffcap.py output). Quote numbers + counts only."""
import json
import sys

rows = json.load(open(sys.argv[1], encoding="utf-8"))
for r in rows:
    s = {i["b"]: i for i in r["saved_items"] if not i["x"] and i["b"] is not None}
    l = {i["b"]: i for i in r["live_items"] if not i["x"] and i["b"] is not None}
    removed = [s[b] for b in s if b not in l]
    added = [l[b] for b in l if b not in s]
    both = [b for b in s if b in l]
    renamed = [b for b in both if s[b]["m"] != l[b]["m"]]
    moved = [b for b in both if s[b]["c"] != l[b]["c"]]
    price = [b for b in both if abs(float(s[b]["p"] or 0) - float(l[b]["p"] or 0)) > 1e-9]
    qty = [b for b in both if abs(float(s[b]["q"] or 0) - float(l[b]["q"] or 0)) > 1e-9]
    d_removed = sum(float(i["lc"] or 0) for i in removed)
    d_added = sum(float(i["lc"] or 0) for i in added)
    d_price = sum(float(l[b]["lc"] or 0) - float(s[b]["lc"] or 0) for b in price)
    dgt = sum(float(v) for v in (r["live_cats"] or {}).values()) - sum(float(v) for v in (r["saved_cats"] or {}).values())
    print(f"{r['qno']:<16} removed={len(removed):<3}(R{-d_removed:>10,.2f}) added={len(added):<3}(R{d_added:>10,.2f}) "
          f"price={len(price):<3}(R{d_price:>10,.2f}) qty={len(qty):<3} renamed={len(renamed):<2} moved={len(moved):<2} "
          f"mfg_delta=R{dgt:>11,.2f}")
    for i in removed[:4]:
        print(f"      - removed: [{i['c']}] {i['m']}  R{float(i['lc'] or 0):,.2f}")
    for i in added[:4]:
        print(f"      + added:   [{i['c']}] {i['m']}  R{float(i['lc'] or 0):,.2f}")
