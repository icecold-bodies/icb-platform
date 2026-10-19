"""READ ONLY (RT8 §3.0): the shape of saved costings on the dev DB `icb`.

Connects with default_transaction_read_only=on. Prints NO customer data — quote numbers, body
names, dates, key sets and counts only (G4). DATABASE_URL is read from the main clone's
backend/.env and never printed.
Usage: python -I rt8_shapes.py <out.json>
"""
import collections
import json
import sys
from pathlib import Path

import psycopg as psycopg2

ENV = Path(r"C:\Users\micge\Documents\icb-platform\backend\.env")
url = None
for line in ENV.read_text(encoding="utf-8").splitlines():
    if line.startswith("DATABASE_URL="):
        url = line.split("=", 1)[1].strip().strip('"').strip("'")
url = url.replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")
conn = psycopg2.connect(url, options="-c default_transaction_read_only=on")
cur = conn.cursor()
cur.execute("select current_database(), current_setting('default_transaction_read_only')")
print("db", cur.fetchone())
cur.execute("""
  select c.id, c.quote_number, coalesce(c.status,'pending'), c.trailer_type_id, t.name, c.created_at,
         c.is_repair, c.deleted_at is not null, c.result_json
    from calculations c left join trailer_types t on t.id = c.trailer_type_id
   order by c.id""")
rows = cur.fetchall()
print("records", len(rows))

top_by_month = collections.defaultdict(collections.Counter)
item_by_month = collections.defaultdict(collections.Counter)
is_by_month = collections.defaultdict(collections.Counter)
ui_by_month = collections.defaultdict(collections.Counter)
n_by_month = collections.Counter()
pending = []
for rid, qno, st, tid, tname, created, is_rep, deleted, rj in rows:
    try:
        r = json.loads(rj) if isinstance(rj, str) else (rj or {})
    except Exception:
        r = {}
    m = created.strftime("%Y-%m") if created else "none"
    n_by_month[m] += 1
    for k in r.keys():
        top_by_month[m][k] += 1
    items = r.get("items") or []
    keys = set()
    for it in items:
        if isinstance(it, dict):
            keys |= set(it.keys())
    for k in keys:
        item_by_month[m][k] += 1
    ins = r.get("input_state") or {}
    for k in ins.keys():
        is_by_month[m][k] += 1
    ui = ins.get("ui_snapshot") or {}
    if isinstance(ui, dict):
        for k in ui.keys():
            ui_by_month[m][k] += 1
    if st == "pending" and not deleted:
        has_snap = bool(isinstance(ui, dict) and ui.get("body_option_selections"))
        pending.append({"id": rid, "qno": qno, "body": tname, "tid": tid, "month": m,
                        "repair": bool(is_rep), "trailerless": tid is None,
                        "snapshot": has_snap, "n_items": len(items),
                        "has_body_vars": bool(r.get("body_variables")),
                        "has_input_state": bool(ins)})

out = {"n_by_month": n_by_month, "top": top_by_month, "item": item_by_month, "input_state": is_by_month,
       "ui_snapshot": ui_by_month, "pending": pending}
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print("months", dict(sorted(n_by_month.items())))
print("pending (not deleted)", len(pending), "repairs", sum(p["repair"] for p in pending),
      "no snapshot", sum(1 for p in pending if not p["snapshot"] and not p["repair"]))
