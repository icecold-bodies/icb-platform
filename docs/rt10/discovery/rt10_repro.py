"""RT10 §3.0 — reproduce on the rt10 side server (:8012, icb_test, today's code = dce981e + the v1.62.0 SPA):

  A. numbering: Save as Rev. three times from the same first save → versions 2, 2, 2 (the modal's number is the
     client's editingVersion + 1, and the server stores it as sent);
  B. the list: after the board re-fetches with a new costing on top, rows that share a quote number leave ghost
     rows behind (React key = quote number) — the DOM shows more rows than the API returned;
  C. Accept / Decline on a revision's row post to the OLDEST row with that quote number (liveIdByQuote);
  D. a row click opens /costings/<quote number>, which resolves to the NEWEST row with that number.

Marker rows RT10J* only — created here, purged at the end (and at the start). Writes go to icb_test only; C is
intercepted in the browser (nothing is accepted or declined). Prints ids, versions and quote numbers only.
Usage (from the rt10 backend dir): DATABASE_URL=...icb_test python rt10_repro.py [--keep]"""
from __future__ import annotations

import json
import os
import sys
import time

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("MES_BASE", "http://127.0.0.1:8012").rstrip("/")
assert ":8000" not in BASE, "never :8000"
assert os.environ.get("DATABASE_URL", "").endswith("/icb_test"), "icb_test only"
sys.path.insert(0, os.getcwd())
from app.database import (BillOfMaterial, CalculationRecord, Customer, Material, SessionLocal,  # noqa: E402
                          TrailerType, UserSession)
from sqlalchemy import text  # noqa: E402

MARK = "RT10J"
T = 20_000
DIMS = {"length": 6.0, "width": 2.4, "height": 2.4, "floor_thickness": 0.1, "panel_thickness": 0.06,
        "insulation_thickness": 0.06, "num_axles": 2, "num_doors": 2}
SNAP = {"body_option_selections": {}, "drd_srd": {}, "draft_flag_state": {}, "draft_flag_vars": {},
        "draft_category_radio": {}, "draft_masterless_cat": {}, "draft_folder": {}, "optional_sections_enabled": [],
        "optional_row_excl": [], "price_overrides": {}, "ratio": "0.55", "chassis": {"enabled": False},
        "body_variables": {}}


def purge() -> None:
    with SessionLocal() as db:
        db.execute(text("DELETE FROM icb_costings.calculations c USING icb_costings.customers cu "
                        "WHERE c.customer_id = cu.id AND cu.name LIKE 'RT10J%'"))
        db.execute(text("DELETE FROM icb_costings.calculations WHERE trailer_type_id IN "
                        "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'RT10J%')"))
        db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                        "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'RT10J%')"))
        db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE 'RT10J%'"))
        db.execute(text("DELETE FROM icb_costings.materials WHERE material_code = 'RT10J'"))
        db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'RT10J%'"))
        db.commit()


def seed() -> dict:
    with SessionLocal() as db:
        cust = Customer(name=f"{MARK} CUSTOMER")
        cust2 = Customer(name=f"{MARK} OTHER CUSTOMER")
        tt = TrailerType(name=f"{MARK} BODY", is_active=True, default_length=6.0, default_width=2.4, default_height=2.4)
        db.add_all([cust, cust2, tt])
        db.flush()
        rows = []
        for i, (name, price, formula) in enumerate([("PANEL", 250.0, "length*width"), ("FLOOR", 300.0, "length*width"),
                                                    ("RAIL", 40.0, "length*2")]):
            m = Material(name=f"{MARK} {name}", unit_of_measure="m²", price_per_unit=price, material_code=MARK,
                         is_active=True)
            db.add(m)
            db.flush()
            r = BillOfMaterial(trailer_type_id=tt.id, material_id=m.id, formula_expression=formula,
                               waste_percentage=0.0, bom_section=name, sort_order=10 * (i + 1))
            db.add(r)
            rows.append(r)
        db.commit()
        return {"customer": cust.id, "customer2": cust2.id, "tt": tt.id}


def csrf(page) -> str:
    sid = next((c["value"] for c in page.context.cookies() if c["name"] == "session_id"), None)
    with SessionLocal() as db:
        row = db.get(UserSession, sid)
        return (row.csrf_token or "") if row else ""


def post(page, path: str, body: dict):
    return page.request.post(f"{BASE}{path}", data=json.dumps(body),
                             headers={"Origin": BASE, "X-CSRF-Token": csrf(page), "Content-Type": "application/json"})


def save_fresh(page, ids, customer_key="customer") -> dict:
    r = post(page, "/api/approve", {
        "trailer_type_id": ids["tt"], "dimensions": dict(DIMS), "profit_margin": 5, "overrides": {},
        "override_reasons": {}, "chassis": {"enabled": False}, "user_excluded_bom_ids": [],
        "optional_sections_enabled": [], "customer_id": ids[customer_key], "ratio_value": 0.55, "ratio_label": "55%",
        "ui_snapshot": SNAP, "version_action": "save_as_new"})
    assert r.ok, r.text()
    return r.json()


def stored_version(rec_id: int):
    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=rec_id).first()
        return json.loads(rec.result_json).get("version"), rec.quote_number


def save_as_rev_ui(page, rec_id: int) -> dict:
    """The calculator, exactly as a user: open the first save for Edit, Approve & Save, Save as new Revision."""
    page.goto(f"{BASE}/mes/calculator?edit={rec_id}&stay=1")
    expect(page.locator("[data-testid='frozen-saved-line'], [data-testid='frozen-readonly']").first).to_be_visible(timeout=T)
    expect(page.locator("#grand-total")).not_to_have_text("—", timeout=T)
    page.wait_for_timeout(1500)
    banner = page.locator("#edit-banner-text").inner_text()
    page.click("#approve-btn")
    expect(page.locator("#modal-edit-save")).to_be_visible(timeout=T)
    offered = page.locator("#edit-newver-ver").inner_text()
    summary = page.locator("#edit-save-summary").inner_text()
    if "--nc" in sys.argv:   # negative control: the revision takes a NEW quote number (reuse unticked)
        page.uncheck("#edit-reuse-qno")
    page.click("#modal-edit-save button:has-text('new Revision')")
    new_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        new_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if new_id and new_id != rec_id:
            break
    assert new_id and new_id != rec_id, "no new revision was saved"
    v, qn = stored_version(new_id)
    return {"id": new_id, "stored_version": v, "quote_number": qn, "modal_offered": offered,
            "banner": banner.split("—")[0].strip(), "summary": summary.strip()}


def board_ids(page) -> list:
    """Every row the board's table shows, in DOM order, as the record id its View link points at."""
    return page.evaluate("""() => [...document.querySelectorAll("[data-testid='costing-row']")].map(tr => {
        const a = tr.querySelector("a[href*='/costings/results/']");
        const q = tr.querySelector('td:nth-child(2)');
        return {id: a ? +a.getAttribute('href').split('/').pop() : null, qn: q ? q.innerText.trim().split(' · ')[0].trim() : null};
    })""")


def main() -> None:
    keep = "--keep" in sys.argv
    purge()
    ids = seed()
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(base_url=BASE)
        page = ctx.new_page()
        page.set_default_timeout(T)
        warnings = []
        page.on("console", lambda m: warnings.append(m.text) if "same key" in m.text else None)
        r = page.request.post(f"{BASE}/api/mes/autologin", headers={"Origin": BASE})
        assert r.ok, f"autologin HTTP {r.status}"

        # ── A. numbering ────────────────────────────────────────────────────
        first = save_fresh(page, ids)
        rec, qn = first["record_id"], first["quote_number"]
        v0, _ = stored_version(rec)
        out["A_first_save"] = {"id": rec, "quote_number": qn, "stored_version": v0}
        revs = []
        for i in range(2):
            revs.append(save_as_rev_ui(page, rec))
        out["A_saves_1_2"] = revs

        # ── B. the board, mounted with two revisions; a third revision and an unrelated new costing arrive while
        #       the user is on another screen; back to the board ─────────────────────────────────────────────
        page.goto(f"{BASE}/mes-app/costings")
        page.wait_for_selector("[data-testid='costings-table']")
        expect(page.locator("[data-testid='costing-row']").first).to_be_visible(timeout=T)
        page.wait_for_timeout(1500)
        before = board_ids(page)
        # leave the board inside the SPA (client-side): click a row of an unrelated costing → its detail page
        other = next(r_ for r_ in before if r_["qn"] != qn)
        page.locator("[data-testid='costing-row']", has_text=other["qn"]).first.click()
        page.wait_for_url("**/costings/**")
        page.wait_for_timeout(1500)                       # the detail page's own refresh has landed
        # the world moves on: a third Save as Rev. (another tab) and a new costing for another customer
        tab2 = ctx.new_page()
        revs.append(save_as_rev_ui(tab2, rec))
        tab2.close()
        newest = save_fresh(page, ids, customer_key="customer2")
        out["A_save_3"] = revs[2]
        out["B_new_costing_on_top"] = {"id": newest["record_id"], "quote_number": newest["quote_number"]}
        # back to the board the way a user does (the "Back to Costings" link — client-side, no reload)
        page.click("a:has-text('Back to Costings')")
        page.wait_for_url("**/mes-app/costings")
        page.wait_for_timeout(2500)                       # the board's mount refresh has landed
        api = page.request.get(f"{BASE}/api/calculations?limit=100").json()
        dom = board_ids(page)
        api_q = [c["id"] for c in api if c["quote_number"] == qn]
        dom_q = [r_["id"] for r_ in dom if r_["qn"] == qn]
        newest_pos = next((i for i, r_ in enumerate(dom) if r_["id"] == newest["record_id"]), None)
        out["B_board"] = {
            "api_rows": len(api), "dom_rows": len(dom),
            "api_rows_with_quote": api_q, "dom_rows_with_quote": dom_q,
            "dom_top_8": dom[:8], "position_of_new_costing_in_dom": newest_pos,
            "rows_above_new_costing_with_quote": [r_["id"] for r_ in dom[:newest_pos or 0] if r_["qn"] == qn],
            "react_duplicate_key_warnings": len(warnings),
        }
        # a full reload clears the ghosts (fresh tbody)
        page.reload()
        page.wait_for_selector("[data-testid='costings-table']")
        page.wait_for_timeout(2500)
        dom2 = board_ids(page)
        out["B_after_reload"] = {"dom_rows": len(dom2), "dom_rows_with_quote": [r_["id"] for r_ in dom2 if r_["qn"] == qn]}

        # ── C. Accept / Decline on the NEWEST revision's row: which record does the browser post to? ───────
        hits = []

        def capture(route):
            hits.append(route.request.url.replace(BASE, ""))
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))
        page.route("**/api/calculations/*/accept", capture)
        page.route("**/api/calculations/*/decline", capture)
        page.route("**/api/production-jobs/from-calculation/*", capture)
        newest_rev = revs[2]["id"]
        row = page.locator("[data-testid='costing-row']").filter(
            has=page.locator(f"a[href$='/costings/results/{newest_rev}']")).first
        row.locator("button:has-text('Accept')").click()
        page.locator("button:has-text('Confirm acceptance')").click()
        page.wait_for_timeout(1500)
        out["C_accept_clicked_on_row"] = newest_rev
        out["C_requests"] = list(hits)
        page.unroute("**/api/calculations/*/accept")
        page.unroute("**/api/calculations/*/decline")
        page.unroute("**/api/production-jobs/from-calculation/*")

        # ── D. a row click on the OLDEST row (the first save) → /costings/<qn> → which record is shown? ──────
        page.goto(f"{BASE}/mes-app/costings")
        page.wait_for_selector("[data-testid='costings-table']")
        page.wait_for_timeout(2000)
        seen = []
        page.on("request", lambda req: seen.append(req.url) if "validated-references?calculation_id=" in req.url else None)
        row0 = page.locator("[data-testid='costing-row']").filter(
            has=page.locator(f"a[href$='/costings/results/{rec}']")).first
        row0.locator("td").nth(2).click()
        page.wait_for_url("**/costings/**")
        page.wait_for_timeout(2000)
        out["D_row_clicked_record"] = rec
        out["D_url"] = page.url.replace(BASE, "")
        out["D_detail_resolved_to"] = [u.split("calculation_id=")[-1] for u in seen]
        browser.close()
    print(json.dumps(out, indent=1))
    if not keep:
        purge()
        print("purged RT10J* rows")


if __name__ == "__main__":
    main()
