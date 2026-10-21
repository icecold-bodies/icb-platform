"""READ ONLY: which saved-line formulas reference formula-LIBRARY names (vs body/global variables), and which
pending repairs carry STOCK lines priced from the catalogue (and whether today's catalogue price differs)."""
import collections, json, re, sys
import psycopg
conn = psycopg.connect(f"postgresql://icb_app:icb_app_dev@localhost:5432/{sys.argv[1]}", options="-c default_transaction_read_only=on")
cur = conn.cursor()
cur.execute("select lower(name) from formulas where is_active"); lib = {r[0] for r in cur.fetchall()}
cur.execute("select id, price_per_unit from materials"); mat_price = dict(cur.fetchall())
cur.execute("select quote_number, coalesce(status,'pending'), trailer_type_id, deleted_at is not null, result_json from calculations order by id")
tok = re.compile(r"\{([^{}]+)\}")
libref = collections.Counter(); recs_with_lib = 0; n_body = 0
for qno, st, tid, dele, rj in cur.fetchall():
    r = json.loads(rj) if isinstance(rj, str) else (rj or {})
    if tid is None:
        if st == "pending" and not dele:
            lines = (r.get("input_state") or {}).get("repair_lines") or []
            stock = [l for l in lines if l.get("kind") == "stock"]
            moved = [l for l in stock if l.get("material_id") in mat_price and abs(float(mat_price[l["material_id"]] or 0) - float(l.get("unit_price") or 0)) > 1e-9]
            gone = [l for l in stock if l.get("material_id") not in mat_price]
            print(f"REPAIR {qno}: lines={len(lines)} stock={len(stock)} stock_price_moved={len(moved)} stock_material_gone={len(gone)}")
        continue
    n_body += 1
    hit = False
    for it in r.get("items") or []:
        for t in tok.findall(it.get("formula") or ""):
            k = t.strip()
            if k.lower() in lib and k.upper() not in {x.upper() for x in (r.get("body_variables") or {})} | {x.upper() for x in (r.get("global_variables") or {})}:
                libref[k.lower()] += 1; hit = True
    recs_with_lib += hit
print("body records", n_body, "with >=1 line referencing a library formula:", recs_with_lib)
print("library names referenced (line count):", dict(libref.most_common(12)))
