"""RT10 §3.0 — READ ONLY revision counts on a local database (default: dev `icb`). The session is opened read-only
(default_transaction_read_only=on), so nothing can be written. Prints quote numbers, ids, versions, dates and flags
only: no customer, contact or user names (G4).
Usage: python -I rt10_dev_counts.py [dbname]"""
import json
import sys
from collections import defaultdict

import psycopg

db = sys.argv[1] if len(sys.argv) > 1 else "icb"
conn = psycopg.connect(f"host=localhost port=5432 dbname={db} user=icb_app password=icb_app_dev",
                       options="-c default_transaction_read_only=on")
cur = conn.cursor()
cur.execute("SHOW default_transaction_read_only")
print("db", db, "read_only", cur.fetchone()[0])
cur.execute("""SELECT id, quote_number, created_at, deleted_at IS NOT NULL, coalesce(is_repair, false),
                      coalesce(status, ''), trailer_type_id IS NULL, result_json
               FROM calculations ORDER BY created_at, id""")
rows = []
for rid, qn, created, deleted, repair, status, no_body, rj in cur.fetchall():
    try:
        d = json.loads(rj) if rj else {}
    except Exception:
        d = {}
    rp = d.get("repriced") if isinstance(d.get("repriced"), dict) else None
    rows.append({"id": rid, "qn": qn, "created": created.strftime("%Y-%m-%d %H:%M:%S") if created else None,
                 "deleted": deleted, "repair": repair, "status": status, "version": d.get("version"),
                 "has_version_key": "version" in d,
                 "repriced_from": (rp or {}).get("from_record_id"), "repriced_from_version": (rp or {}).get("from_version"),
                 "repriced_from_qn": (rp or {}).get("from_quote_number")})
live = [r for r in rows if not r["deleted"]]
print(f"rows {len(rows)}  live {len(live)}  deleted {len(rows) - len(live)}  repairs {sum(r['repair'] for r in rows)}")
print("version key missing:", sum(not r["has_version_key"] for r in rows),
      " version values:", dict(sorted(defaultdict(int, {str(v): sum(1 for r in rows if r['version'] == v)
                                                       for v in {r['version'] for r in rows}}).items())))
print("no quote number:", [r["id"] for r in rows if not r["qn"]])

groups = defaultdict(list)
for r in rows:
    if r["qn"]:
        groups[r["qn"]].append(r)
multi = {q: g for q, g in groups.items() if len(g) > 1}
multi_live = {q: [r for r in g if not r["deleted"]] for q, g in groups.items()}
multi_live = {q: g for q, g in multi_live.items() if len(g) > 1}
print(f"\nquote numbers with >1 row (all rows): {len(multi)}   with >1 LIVE row: {len(multi_live)}")
for q, g in sorted(multi.items()):
    print(f"  {q}: " + ", ".join(f"id {r['id']} v{r['version']}{' DEL' if r['deleted'] else ''}"
                               f"{' R' if r['repair'] else ''} {r['created']} {r['status']}"
                               + (f" repriced<-{r['repriced_from']}" if r['repriced_from'] else "") for r in g))
dups = {}
for q, g in multi_live.items():
    seen = defaultdict(list)
    for r in g:
        seen[r["version"]].append(r["id"])
    d = {v: ids for v, ids in seen.items() if len(ids) > 1}
    if d:
        dups[q] = d
print(f"\nLIVE duplicate version numbers within one quote number: {len(dups)}")
for q, d in sorted(dups.items()):
    print(f"  {q}: " + "; ".join(f"version {v} x{len(ids)} (ids {ids})" for v, ids in d.items()))
lone_rev = [r for r in rows if (r["version"] or 1) > 1 and len(groups.get(r["qn"], [])) == 1]
print(f"\nrows with version > 1 whose quote number is unique (a revision saved under a NEW number): {len(lone_rev)}")
for r in lone_rev:
    print(f"  id {r['id']} {r['qn']} v{r['version']}{' DEL' if r['deleted'] else ''}{' R' if r['repair'] else ''} {r['created']}")
rp = [r for r in rows if r["repriced_from"]]
print(f"\nrows carrying an RT8 repriced block: {len(rp)}")
for r in rp:
    print(f"  id {r['id']} {r['qn']} v{r['version']} <- id {r['repriced_from']} {r['repriced_from_qn']} v{r['repriced_from_version']}")
order = [r for r in live]
order.sort(key=lambda r: (r["created"] or ""), reverse=True)
print("\nnewest 12 live rows (created desc, the list API's order):")
for r in order[:12]:
    print(f"  id {r['id']} {r['qn']} v{r['version']} {r['created']}{' R' if r['repair'] else ''} {r['status']}")
conn.close()
