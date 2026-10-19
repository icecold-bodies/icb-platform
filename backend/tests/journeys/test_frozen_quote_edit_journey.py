"""RT8 (v1.62.0) — a re-opened quote is the saved quote (journey).

Michael's rule (19 Oct 2026): when a quote is saved, an exact copy is saved, and anyone editing that quote gets
that exact copy back. Today's template and prices enter a saved quote only when a user asks for them, after seeing
line by line what would change — and then as a new revision only.

The N10022 scenario as a fixture (no customer data): a MEAT HANGER LARGE 7.8 x 2.6 x 2.56 at 4G is saved through
the API; then the template changes the way Michael's did — the ROOF plywood row moves into a NEW radio group
(4MM / 6MM PF PLYWOOD), the SIDES plywood row is re-pointed at another material at the same price, one other row
is deleted, the 4G factor moves from 5581/4100 to 5400/4100. On the real surfaces:

  open the quote for Edit → the screen is the saved quote, the quiet line says what today's prices would change,
  and no calculation ran on open (ten times) → Export preview carries the saved figures → View changes lists the
  new option at its default, the removed row, the PU rate → Update to today's prices → Apply → the re-priced screen
  carries the new option's default line → Save → New revision only (Overwrite is not offered) → the original is
  untouched and the board lists both revisions. A COPY of the quote also gets the new option's default. A stale
  calculation response never renders, and a body picked while the page is still loading is not overwritten by the
  last-session restore. A saved repair opens at its saved prices.

Negative controls (F6): RT8_NC=race|stale|init|overlay patches the served calculator.js to remove that guard, and
the matching test must fail for the right reason. Never set in CI.

Marker rows RT8J* only — created and purged here. Base-aware throughout (MES_BASE), so this file can run alone on
a side port against an isolated test DB.
"""
from __future__ import annotations

import json
import os
import re

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, admin_session, shot  # noqa: E402

T = 20_000
JOURNEY = "frozen_quote_edit"
MARK = "RT8J"
DIMS = {"length": 7.8, "width": 2.6, "height": 2.56, "floor_thickness": 0.1, "panel_thickness": 0.06,
        "insulation_thickness": 0.06, "num_axles": 3, "num_doors": 2}
FACTOR_BEFORE = 5581.0 / 4100.0
FACTOR_AFTER = 5400.0 / 4100.0


def _base() -> str:
    return os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")


def _money(text: str) -> float:
    s = "".join(ch for ch in (text or "") if ch.isdigit() or ch in ".,-")
    if "." in s and "," in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s or 0)


# ── negative controls: the served file with one guard removed ────────────────
_NC = {
    # the race: no suspension on open, no cancel, and the queued calculation prices at TODAY's template
    "race": [("  if (_calcSuspended) return;\n  // v1.47 — a REPAIRS costing has no bomData", "  // v1.47 — a REPAIRS costing has no bomData"),
             ("  const gen = ++_calcGen;\n  lastCalcPayload = frozen ? _buildFrozenPayload(tid) : _buildCalcPayload(tid);",
              "  const gen = ++_calcGen;\n  lastCalcPayload = _buildCalcPayload(tid);"),
             ("    _calcSuspended = false;\n    clearTimeout(calcTimer);\n    _frozenDriftCheck();   // background",
              "    _calcSuspended = false;\n    scheduleCalc();\n    _frozenDriftCheck();   // background")],
    # a stale response renders
    "stale": [("    if (gen !== _calcGen) return;   // stale: a newer calculation owns the screen", "")],
    # the last-session restore overwrites the body the user picked
    "init": [("  if (_userTouchedBody) return false;\n  let session;", "  let session;"),
             ("  if (_userTouchedBody) return false;   // RT8 — the user changed the body during the load: theirs wins", "")],
    # the old REPLACE behaviour: the snapshot replaces today's defaults, and no new group gets a choice
    "overlay": [("  const st = _overlaySnapshot(_todayOptionState, snap);", "  const st = _overlaySnapshot({}, snap);"),
                ("  _newOptionGroups(snap).forEach(g => {\n    if (g.kind !== 'category_radio') return;", "  [].forEach(g => {\n    if (g.kind !== 'category_radio') return;"),
                ("  _applyOptionState(_overlaySnapshot(_captureOptionState(), src));", "  _applyOptionState(_overlaySnapshot({}, src));")],
}


def _install_nc(page: Page) -> None:
    nc = os.environ.get("RT8_NC", "").strip()
    if not nc:
        return
    subs = _NC[nc]

    def handler(route):
        resp = route.fetch()
        body = resp.text().replace("\r\n", "\n")
        for old, new in subs:
            assert body.count(old) == 1, f"NC {nc}: anchor not found exactly once: {old[:60]!r}"
            body = body.replace(old, new)
        route.fulfill(response=resp, body=body)
    page.route("**/static/js/calculator.js*", handler)


# ── the fixture ──────────────────────────────────────────────────────────────
def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_costings.calculations c USING icb_costings.customers cu "
                    "WHERE c.customer_id = cu.id AND cu.name LIKE 'RT8J%'"))
    db.execute(text("DELETE FROM icb_costings.calculations WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'RT8J%')"))
    db.execute(text("DELETE FROM icb_costings.configurator_drafts WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'RT8J%')"))
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'RT8J%')"))
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE 'RT8J%'"))
    db.execute(text("DELETE FROM icb_costings.materials WHERE material_code = 'RT8J'"))
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'RT8J%'"))
    db.commit()


def _set_factor(db, value) -> None:
    from app.database import AdminSetting
    from app.services.insulation_foam import FACTOR_KEY
    row = db.query(AdminSetting).filter_by(key=FACTOR_KEY).first()
    if row is None:
        db.add(AdminSetting(key=FACTOR_KEY, value=str(value)))
    else:
        row.value = str(value)
    db.commit()


def _csrf(page: Page) -> str:
    from app.database import SessionLocal, UserSession
    sid = next((c["value"] for c in page.context.cookies() if c["name"] == "session_id"), None)
    assert sid, "no session cookie — autologin did not establish a session"
    with SessionLocal() as db:
        row = db.get(UserSession, sid)
        return (row.csrf_token or "") if row else ""


def _post(page: Page, path: str, body: dict):
    base = _base()
    return page.request.post(f"{base}{path}", data=json.dumps(body),
                             headers={"Origin": base, "X-CSRF-Token": _csrf(page), "Content-Type": "application/json"})


def _get(page: Page, path: str):
    return page.request.get(f"{_base()}{path}").json()


def _stored(record_id: int) -> dict:
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        return json.loads(db.query(CalculationRecord).filter_by(id=record_id).first().result_json)


def _raw(record_id: int) -> str:
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        return db.query(CalculationRecord).filter_by(id=record_id).first().result_json


@pytest.fixture(scope="module")
def staged(browser, live_server: str):
    """The N10022 scenario, saved through the API, then Michael's four template changes."""
    from app.database import (AdminSetting, BillOfMaterial, Customer, Material, SessionLocal, TrailerType)
    from app.services.insulation_foam import FACTOR_KEY
    ids = {}
    with SessionLocal() as db:
        _purge(db)
        row = db.query(AdminSetting).filter_by(key=FACTOR_KEY).first()
        ids["factor_before"] = row.value if row else None
        _set_factor(db, FACTOR_BEFORE)
        cust = Customer(name=f"{MARK} CUSTOMER")
        db.add(cust)
        tt = TrailerType(name=f"{MARK} MEAT HANGER LARGE", is_active=True, configurator_v2=True,
                         default_length=7.8, default_width=2.6, default_height=2.56, default_insulation_foam="4G")
        other = TrailerType(name=f"{MARK} OTHER BODY", is_active=True, default_length=5.0, default_width=2.4,
                            default_height=2.4)
        db.add_all([tt, other])
        db.flush()

        def mat(name, price, uom="m²"):
            m = Material(name=name, unit_of_measure=uom, price_per_unit=price, material_code=MARK, is_active=True)
            db.add(m)
            db.flush()
            return m

        pu = mat("PU", 4100.0)
        ply6 = mat(f"{MARK} 6MM PF PLYWOOD", 86.58)
        ply4 = mat(f"{MARK} 4MM PF PLYWOOD", 68.79)
        birch = mat(f"{MARK} 6MM BIRCH PLYWOOD", 68.79)
        screws = mat(f"{MARK} ROOF SCREWS", 1.5, uom="each")
        floor = mat(f"{MARK} 12MM PF PLYWOOD", 316.78)
        hinge = mat(f"{MARK} REPAIR HINGE", 120.0, uom="each")

        def row(t, m, section, formula, sort, waste=0.0):
            r = BillOfMaterial(trailer_type_id=t.id, material_id=m.id, formula_expression=formula,
                               waste_percentage=waste, bom_section=section, sort_order=sort)
            db.add(r)
            db.flush()
            return r

        ids.update({
            "customer": cust.id, "tt": tt.id, "other": other.id, "other_name": other.name, "tt_name": tt.name,
            "roof_ply": row(tt, ply6, "ROOF", "length*width", 10, waste=2.5).id,
            "roof_pu": row(tt, pu, "ROOF", "length*width*0.0943", 11).id,
            "roof_screws": row(tt, screws, "ROOF", "length*4", 12).id,
            "sides_ply": row(tt, ply4, "SIDES", "length*height*2", 20).id,
            "floor_ply": row(tt, floor, "FLOOR", "length*width", 30).id,
            "other_row": row(other, floor, "FLOOR", "length*width", 1).id,
            "mat_birch": birch.id, "mat_ply4": ply4.id, "hinge": hinge.id,
        })
        db.commit()

    ctx = browser.new_context(base_url=live_server)
    page = ctx.new_page()
    r = page.request.post(f"{live_server}/api/mes/autologin", headers={"Origin": live_server})
    assert r.ok, f"autologin HTTP {r.status}"
    snap = {"body_option_selections": {}, "drd_srd": {}, "draft_flag_state": {}, "draft_flag_vars": {},
            "draft_category_radio": {}, "draft_masterless_cat": {}, "draft_folder": {},
            "optional_sections_enabled": [], "optional_row_excl": [], "price_overrides": {}, "ratio": "0.55",
            "chassis": {"enabled": False}, "body_variables": {}}
    r = _post(page, "/api/approve", {
        "trailer_type_id": ids["tt"], "dimensions": dict(DIMS), "profit_margin": 5, "overrides": {},
        "override_reasons": {}, "chassis": {"enabled": False}, "insulation_foam": "4G",
        "user_excluded_bom_ids": [], "optional_sections_enabled": [], "customer_id": ids["customer"],
        "ratio_value": 0.55, "ratio_label": "55%", "ui_snapshot": snap})
    assert r.ok, r.text()
    ids["rec"] = r.json()["record_id"]
    ids["qno"] = r.json()["quote_number"]
    ids["saved"] = _stored(ids["rec"])
    # a saved repair with a stock line, for the repair check
    r = _post(page, "/api/approve", {
        "is_repair": True, "trailer_type_id": None, "repair_type": f"{MARK} door repair", "repair_scope": None,
        "repair_lines": [{"kind": "stock", "key": "s1", "material_id": ids["hinge"], "qty": 2, "excluded": False},
                         {"kind": "free_hand", "key": "f1", "description": "Labour", "qty": 1, "unit": "each",
                          "unit_price": 500, "excluded": False}],
        "profit_margin": 5, "ratio_value": 0.55, "ratio_label": "55%", "discount_kind": None, "discount_input": None,
        "repair_vehicle": None, "dimensions": {}, "customer_id": ids["customer"]})
    assert r.ok, r.text()
    ids["repair"] = r.json()["record_id"]
    ids["repair_saved"] = _stored(ids["repair"])
    # Michael's changes, afterwards
    draft = {"nextId": 4, "rootIds": ["1"], "itemRules": {}, "nodes": {
        "1": {"id": "1", "type": "category", "label": "ROOF plywood", "parentId": None, "childIds": ["2", "3"],
              "selectionMode": "container", "sourceCategoryKey": "ROOF PLYWOOD"},
        "2": {"id": "2", "type": "category", "label": "4MM PF PLYWOOD", "parentId": "1", "childIds": [],
              "selectionMode": "radio", "sourceCategoryKey": "4MM PF PLYWOOD", "selectionValue": 0},
        "3": {"id": "3", "type": "category", "label": "6MM PF PLYWOOD", "parentId": "1", "childIds": [],
              "selectionMode": "radio", "sourceCategoryKey": "6MM PF PLYWOOD", "selectionValue": 1}}}
    r = page.request.put(f"{live_server}/api/configurator/trailers/{ids['tt']}/draft", data=json.dumps({"draft": draft}),
                         headers={"Origin": live_server, "X-CSRF-Token": _csrf(page), "Content-Type": "application/json"})
    assert r.ok, r.text()
    ctx.close()
    with SessionLocal() as db:
        db.query(BillOfMaterial).filter_by(id=ids["roof_ply"]).first().bom_section = "6MM PF PLYWOOD"
        db.add(BillOfMaterial(trailer_type_id=ids["tt"], material_id=ids["mat_ply4"], formula_expression="length*width",
                              waste_percentage=2.5, bom_section="4MM PF PLYWOOD", sort_order=13))
        db.query(BillOfMaterial).filter_by(id=ids["sides_ply"]).first().material_id = ids["mat_birch"]
        db.query(BillOfMaterial).filter_by(id=ids["roof_screws"]).delete()
        db.query(Material).filter_by(id=ids["hinge"]).first().price_per_unit = 150.0
        _set_factor(db, FACTOR_AFTER)
    yield ids
    with SessionLocal() as db:
        if ids.get("factor_before") is not None:
            _set_factor(db, ids["factor_before"])
        _purge(db)


# ── helpers ──────────────────────────────────────────────────────────────────
def _open_edit(page: Page, record_id: int) -> dict:
    """Open a quote for Edit and count the /api/calculate requests the open made."""
    calls = []
    page.on("request", lambda req: calls.append(req.url) if "/api/calculate" in req.url else None)
    page.goto(f"/mes/calculator?edit={record_id}&stay=1")
    expect(page.locator("[data-testid='frozen-saved-line'], [data-testid='frozen-readonly']").first).to_be_visible(timeout=T)
    expect(page.locator("#grand-total")).not_to_have_text("—", timeout=T)
    return {"calls": calls}


def _settle(page: Page, ms: int = 2500) -> None:
    """Longer than the 700 ms debounce: whatever was queued on open has had its chance to land."""
    page.wait_for_timeout(ms)
    expect(page.locator("#calc-status")).to_have_text("", timeout=T)


def _shown(page: Page) -> dict:
    return page.evaluate("() => ({gt: lastResult ? lastResult.grand_total : null, frozen: !!frozen, "
                         "total: document.getElementById('grand-total').textContent, "
                         "n: lastResult && lastResult.items ? lastResult.items.length : 0})")


# ── the journey ──────────────────────────────────────────────────────────────
def test_reopen_shows_the_saved_quote_and_the_race_cannot_replace_it_ten_times(page: Page, live_server: str, staged) -> None:
    ids = staged
    saved = ids["saved"]
    _install_nc(page)
    admin_session(page, base=live_server)
    for run in range(10):
        info = _open_edit(page, ids["rec"])
        _settle(page)
        s = _shown(page)
        assert s["frozen"], f"run {run + 1}: frozen mode did not open"
        assert s["gt"] == pytest.approx(saved["grand_total"], abs=0.005), f"run {run + 1}: {s}"
        assert _money(s["total"]) == pytest.approx(saved["selling_price"], abs=0.05), f"run {run + 1}: {s}"
        assert not info["calls"], f"run {run + 1}: a calculation ran on open: {info['calls']}"
        if run == 0:
            # the saved lines, under their saved names and sections
            rows = page.evaluate("() => lastResult.items.filter(i => !i.excluded).map(i => [i.category, i.material, i.unit_price])")
            assert ["ROOF", f"{MARK} 6MM PF PLYWOOD", 86.58] in rows
            assert ["SIDES", f"{MARK} 4MM PF PLYWOOD", 68.79] in rows
            assert any(m == f"{MARK} ROOF SCREWS" for _c, m, _p in rows), "the deleted row's line is present"
            assert ["ROOF", "PU", pytest.approx(5581.0, abs=0.005)] in rows
            expect(page.locator("[data-testid='frozen-options-note']")).to_contain_text("as saved")
            expect(page.locator("[data-testid='frozen-drift']")).to_be_visible(timeout=T)
            delta = float(page.locator("[data-testid='frozen-drift']").get_attribute("data-delta"))
            assert delta < 0, "today's prices are lower (the PU rate moved down, a row went)"
            assert page.locator("#edit-banner-balance").inner_text().find("Showing the saved figures") < 0
            shot(page, "01-reopened-saved-quote", journey=JOURNEY)


def test_export_preview_during_a_frozen_edit_sends_the_saved_figures(page: Page, live_server: str, staged) -> None:
    ids = staged
    _install_nc(page)
    admin_session(page, base=live_server)
    _open_edit(page, ids["rec"])
    _settle(page)
    sent = page.evaluate("() => _previewPayload({format: 'excel'}).result.grand_total")
    assert sent == pytest.approx(ids["saved"]["grand_total"], abs=0.005)


def test_view_changes_then_update_to_todays_prices_saves_a_new_revision_only(page: Page, live_server: str, staged) -> None:
    ids = staged
    original = _raw(ids["rec"])
    _install_nc(page)
    admin_session(page, base=live_server)
    _open_edit(page, ids["rec"])
    _settle(page)
    page.click("[data-testid='frozen-view-changes']")
    expect(page.locator("[data-testid='reprice-lines']")).to_be_visible(timeout=T)
    opts = page.locator("[data-testid='reprice-new-option']").all_inner_texts()
    assert any("ROOF plywood: new option" in o and "6MM PF PLYWOOD (default)" in o for o in opts), opts
    kinds = page.locator("[data-testid='reprice-lines'] tbody tr").evaluate_all("rs => rs.map(r => r.dataset.kind)")
    assert "removed_from_template" in kinds and "price" in kinds and "renamed" in kinds, kinds
    table = page.locator("[data-testid='reprice-lines']").inner_text()
    assert "ROOF SCREWS" in table and "removed from template" in table
    assert "6MM BIRCH PLYWOOD" in table
    assert re.search(r"5[\s ]?581,00.*5[\s ]?400,00", table.replace("\n", " ")), "PU 5,581 → 5,400"
    expect(page.locator("[data-testid='reprice-delta-selling']")).to_contain_text("−")
    shot(page, "02-view-changes", journey=JOURNEY)
    expect(page.locator("[data-testid='reprice-apply']")).to_be_enabled()
    page.click("[data-testid='reprice-apply']")
    expect(page.locator("[data-testid='repriced-line']")).to_be_visible(timeout=T)
    _settle(page)
    # the overlay rule: the re-priced quote carries the new option at its default, today's PU rate, the SIDES
    # line under today's name, and not the deleted row
    rows = page.evaluate("() => lastResult.items.filter(i => !i.excluded).map(i => [i.category, i.material, i.unit_price])")
    assert ["6MM PF PLYWOOD", f"{MARK} 6MM PF PLYWOOD", 86.58] in rows, rows
    assert not any(c == "4MM PF PLYWOOD" for c, _m, _p in rows)
    assert ["ROOF", "PU", pytest.approx(5400.0, abs=0.005)] in rows
    assert ["SIDES", f"{MARK} 6MM BIRCH PLYWOOD", 68.79] in rows
    assert not any(m == f"{MARK} ROOF SCREWS" for _c, m, _p in rows)
    assert page.evaluate("() => !frozen && !!repricedFrom")
    # save: Overwrite is not offered; a new revision is
    page.click("#approve-btn")
    expect(page.locator("#modal-edit-save")).to_be_visible(timeout=T)
    expect(page.locator("[data-testid='edit-overwrite-btn']")).to_be_hidden()
    expect(page.locator("[data-testid='edit-save-repriced-note']")).to_be_visible()
    shot(page, "03-save-new-revision-only", journey=JOURNEY)
    page.click("#modal-edit-save button:has-text('new Revision')")
    rec_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec_id and rec_id != ids["rec"]:
            break
    assert rec_id and rec_id != ids["rec"], "no new revision was saved"
    assert _raw(ids["rec"]) == original, "the original must stay exactly as sent"
    rev = _stored(rec_id)
    assert rev["version"] == 2 and rev["repriced"]["from_record_id"] == ids["rec"]
    assert rev["repriced"]["comparison"]["new_options"][0]["text"].endswith("6MM PF PLYWOOD (default)")
    assert any(i["material"] == f"{MARK} 6MM PF PLYWOOD" for i in rev["items"] if not i["excluded"])
    # the board lists both revisions under the one quote number
    listing = _get(page, "/api/calculations?limit=500")
    rows_ = listing if isinstance(listing, list) else (listing.get("items") or listing.get("records") or listing.get("calculations") or [])
    both = [c for c in rows_ if c.get("quote_number") == ids["qno"]]
    assert len(both) == 2, [c.get("quote_number") for c in rows_][:10]
    ids["rev2"] = rec_id


def test_a_copy_of_the_quote_gets_the_new_options_default(page: Page, live_server: str, staged) -> None:
    ids = staged
    _install_nc(page)
    admin_session(page, base=live_server)
    page.goto(f"/mes/calculator?from={ids['rec']}&stay=1")
    expect(page.locator("#grand-total")).not_to_have_text("—", timeout=T)
    _settle(page)
    rows = page.evaluate("() => lastResult.items.filter(i => !i.excluded).map(i => [i.category, i.material])")
    assert ["6MM PF PLYWOOD", f"{MARK} 6MM PF PLYWOOD"] in rows, rows
    assert not any(c == "4MM PF PLYWOOD" for c, _m in rows)
    assert page.evaluate("() => !frozen && !editingRecordId")


def test_a_stale_calculation_response_never_renders(page: Page, live_server: str, staged) -> None:
    ids = staged
    _install_nc(page)
    admin_session(page, base=live_server)
    page.goto(f"/mes/calculator?trailer={ids['other']}&stay=1")
    expect(page.locator("#grand-total")).not_to_have_text("—", timeout=T)
    _settle(page)
    held = {}

    def handler(route):
        if "route" not in held:
            held["route"] = route          # the FIRST calculation is held back …
            return
        route.continue_()
    page.route("**/api/calculate", handler)
    page.evaluate("() => { document.getElementById('f-length').value = '8'; _recalcNow(); }")
    page.wait_for_timeout(300)
    page.evaluate("() => { document.getElementById('f-length').value = '8.2'; _recalcNow(); }")
    for _ in range(int(T / 200)):
        page.wait_for_timeout(200)
        if page.evaluate("() => lastResult && lastResult.geometry && lastResult.geometry.length === 8.2"):
            break
    assert page.evaluate("() => lastResult.geometry.length") == 8.2
    # … and lands last, carrying a figure that would be unmistakable on screen
    stale = {"items": [], "category_totals": {}, "category_multipliers": {}, "grand_total": 999999.99, "cost_per_sqm": 0,
             "geometry": {"length": 8}, "trailer_name": ids["other_name"], "rule_breaches": [], "rule_unclassified": []}
    held["route"].fulfill(status=200, content_type="application/json", body=json.dumps(stale))
    page.wait_for_timeout(800)
    assert page.evaluate("() => lastResult.grand_total") != 999999.99
    assert page.evaluate("() => lastResult.geometry.length") == 8.2
    assert "999" not in page.locator("#grand-total").inner_text()


def test_the_init_restore_stands_down_once_the_user_changed_the_body(page: Page, live_server: str, staged) -> None:
    ids = staged
    _install_nc(page)
    admin_session(page, base=live_server)
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.evaluate("(tid) => localStorage.setItem('last_costing_session', JSON.stringify({trailer_type_id: String(tid), "
                  "dims: {length: 7.8, width: 2.6, height: 2.56}, margin: 5, ratio: '0.55'}))", ids["tt"])
    held = {}

    def handler(route):
        if "route" not in held:
            held["route"] = route          # the page's first awaited load is held: the restore cannot start yet
            return
        route.continue_()
    page.route(re.compile(r"/api/trailers$"), handler)
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    for _ in range(50):
        page.wait_for_timeout(100)
        if "route" in held:
            break
    assert "route" in held, "the trailers load was not intercepted"
    page.select_option("#trailer-select", str(ids["other"]))      # the user picks a body while the page still loads
    expect(page.locator(".calc-grp-hdr").first).to_be_visible(timeout=T)
    # the user's own calculation re-saves the last session as it goes; the stored session the restore will read is
    # the OLD one, so it is put back before the page's loads are released
    page.evaluate("(tid) => localStorage.setItem('last_costing_session', JSON.stringify({trailer_type_id: String(tid), "
                  "dims: {length: 7.8, width: 2.6, height: 2.56}, margin: 5, ratio: '0.55'}))", ids["tt"])
    held["route"].continue_()
    _settle(page, 3000)
    assert page.locator("#trailer-select").input_value() == str(ids["other"]), "the restore overwrote the user's body"
    expect(page.locator("#topbar-title")).to_contain_text(ids["other_name"].upper() if ids["other_name"].isupper() else ids["other_name"])


def test_a_saved_repair_opens_at_its_saved_prices(page: Page, live_server: str, staged) -> None:
    ids = staged
    saved = ids["repair_saved"]
    _install_nc(page)
    admin_session(page, base=live_server)
    _open_edit(page, ids["repair"])
    _settle(page)
    s = _shown(page)
    assert s["frozen"] and s["gt"] == pytest.approx(saved["grand_total"], abs=0.005), s
    rows = page.evaluate("() => lastResult.items.map(i => [i.material, i.unit_price])")
    assert [f"{MARK} REPAIR HINGE", 120.0] in rows, rows
    expect(page.locator("[data-testid='frozen-drift']")).to_be_visible(timeout=T)
    shot(page, "04-repair-saved-prices", journey=JOURNEY)
