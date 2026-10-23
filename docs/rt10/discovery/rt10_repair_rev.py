"""RT10 §3.0 — what "Save as new Revision" does to a REPAIR today (icb_test, marker RT10J, purged after): a repair
saved, then a new revision of it with reuse_quote_number + next_version 2 (what the edit modal sends)."""
import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8012"
assert os.environ.get("DATABASE_URL", "").endswith("/icb_test")
sys.path.insert(0, os.getcwd())
from app.database import CalculationRecord, Customer, SessionLocal, UserSession  # noqa: E402
from sqlalchemy import text  # noqa: E402


def purge():
    with SessionLocal() as db:
        db.execute(text("DELETE FROM icb_costings.calculations c USING icb_costings.customers cu "
                        "WHERE c.customer_id = cu.id AND cu.name LIKE 'RT10J%'"))
        db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'RT10J%'"))
        db.commit()


def main():
    purge()
    with SessionLocal() as db:
        c = Customer(name="RT10J REPAIR CUSTOMER")
        db.add(c)
        db.commit()
        cust = c.id
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_context(base_url=BASE).new_page()
        assert page.request.post(f"{BASE}/api/mes/autologin", headers={"Origin": BASE}).ok
        sid = next(x["value"] for x in page.context.cookies() if x["name"] == "session_id")
        with SessionLocal() as db:
            tok = db.get(UserSession, sid).csrf_token

        def post(body):
            r = page.request.post(f"{BASE}/api/approve", data=json.dumps(body),
                                  headers={"Origin": BASE, "X-CSRF-Token": tok, "Content-Type": "application/json"})
            assert r.ok, r.text()
            return r.json()
        rep = {"is_repair": True, "trailer_type_id": None, "repair_type": "RT10J door repair", "repair_scope": None,
               "repair_lines": [{"kind": "free_hand", "key": "f1", "description": "Labour", "qty": 1, "unit": "each",
                                 "unit_price": 500, "excluded": False}],
               "profit_margin": 5, "ratio_value": 0.55, "ratio_label": "55%", "repair_vehicle": None, "dimensions": {},
               "customer_id": cust}
        a = post(rep)
        r2 = post({**rep, "version_action": "new_version", "next_version": 2, "reuse_quote_number": True,
                   "edit_record_id": a["record_id"]})
        b.close()
    with SessionLocal() as db:
        for rid in (a["record_id"], r2["record_id"]):
            rec = db.query(CalculationRecord).filter_by(id=rid).first()
            d = json.loads(rec.result_json)
            print(f"id {rid} quote {rec.quote_number} version {d.get('version')} doc {d.get('repair_document_number')}")
    purge()
    print("purged")


main()
