"""RT10 §3.0 — does "Generate Quote" render here? (icb_test, marker RT10J, purged after)"""
import json, os, sys
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:8012"
assert os.environ.get("DATABASE_URL", "").endswith("/icb_test")
sys.path.insert(0, os.getcwd())
from app.database import Customer, SessionLocal, TrailerType, UserSession
from sqlalchemy import text
def purge():
    with SessionLocal() as db:
        db.execute(text("DELETE FROM icb_costings.calculations c USING icb_costings.customers cu WHERE c.customer_id = cu.id AND cu.name LIKE 'RT10J%'"))
        db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'RT10J%'"))
        db.commit()
purge()
with SessionLocal() as db:
    c = Customer(name="RT10J GENQUOTE"); db.add(c); db.commit(); cust = c.id
    tt = db.query(TrailerType).filter_by(name="FREEZER MEDIUM").first(); tid = tt.id
with sync_playwright() as p:
    b = p.chromium.launch(); page = b.new_context(base_url=BASE).new_page()
    assert page.request.post(f"{BASE}/api/mes/autologin", headers={"Origin": BASE}).ok
    sid = next(x["value"] for x in page.context.cookies() if x["name"] == "session_id")
    with SessionLocal() as db:
        tok = db.get(UserSession, sid).csrf_token
    r = page.request.post(f"{BASE}/api/approve", data=json.dumps({"trailer_type_id": tid, "dimensions": {"length": 5.6, "width": 2.5, "height": 2.4}, "profit_margin": 5, "customer_id": cust, "version_action": "save_as_new"}), headers={"Origin": BASE, "X-CSRF-Token": tok, "Content-Type": "application/json"})
    rid = r.json()["record_id"]
    g = page.request.get(f"{BASE}/results/{rid}/report")
    print("Generate Quote:", g.status, g.headers.get("content-type"), g.text()[:160] if g.status != 200 else "")
    e = page.request.get(f"{BASE}/results/{rid}/export/pdf")
    print("Export PDF:", e.status, e.headers.get("content-type"))
    b.close()
purge(); print("purged")
