"""RT10 — revisions visible (journey).

Michael (22 Oct 2026): "The REV (revisions) are not visible on the costings page, please add this so that the user can
see the latest version" · "This version number should also show when the user is viewing the costing." REV = the
stored version − 1 (the first save is REV 0); the quote number is the chain; Latest = its highest live version.

  1. the dispatch's journey: Save as Rev. twice from REV 0 in the calculator (the modal offers REV 1, then REV 2 —
     the server's numbers, never 2 and 2) → the board shows REV 2 · Latest, then REV 1 · earlier and REV 0 · earlier,
     together → open REV 0 → the costing view says REV 0 and "REV 2 is the latest" with its Revisions list → the edit
     banner on REV 0 says "REV 2 is the latest. Open it instead?" → an export of REV 0 carries no REV, one of REV 2
     carries "· REV 2";
  2. the five-vs-three defect (RT10_RETURN_1 §4): the board mounted from an older list, a revision and a new costing
     arriving meanwhile, back to the board — every row shows ONCE (the DOM's record ids = the API's); Accept on the
     newest revision posts ITS id; Accept on REV 0 asks first ("This is REV 0. REV 2 is the latest. Accept REV 0
     anyway?") and then posts REV 0's id; on the latest it does not ask (negative control). Accept is intercepted:
     nothing is accepted;
  3. the duplicate modal: a new costing for a customer that already has a quote for that body is saved as the next
     REV of the quote the button names; Replace names what it would move to Deleted.

Negative control (F6): test 2 fails against the v1.62.0 SPA (the quote-number keys and the quote → id map) — run it
with MES_BASE on a side server whose FRONTEND_DIST is the v1.62.0 build. Marker rows RT10V* only — created and purged
here. Base-aware throughout (MES_BASE), so this file can run alone on a side port against an isolated test DB.
"""
from __future__ import annotations

import io
import json
import os

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, admin_session, shot, wait_calculator_ready  # noqa: E402

T = 20_000
JOURNEY = "rt10_revisions"
MARK = "RT10V"
DIMS = {"length": 6.0, "width": 2.4, "height": 2.4, "floor_thickness": 0.1, "panel_thickness": 0.06,
        "insulation_thickness": 0.06, "num_axles": 2, "num_doors": 2}
SNAP = {"body_option_selections": {}, "drd_srd": {}, "draft_flag_state": {}, "draft_flag_vars": {},
        "draft_category_radio": {}, "draft_masterless_cat": {}, "draft_folder": {}, "optional_sections_enabled": [],
        "optional_row_excl": [], "price_overrides": {}, "ratio": "0.55", "chassis": {"enabled": False},
        "body_variables": {}}


def _base() -> str:
    return os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")


def _purge() -> None:
    from sqlalchemy import text
    from app.database import SessionLocal
    with SessionLocal() as db:
        db.execute(text("DELETE FROM icb_mes.production_jobs WHERE calculation_record_id IN (SELECT c.id FROM "
                        "icb_costings.calculations c JOIN icb_costings.customers cu ON cu.id = c.customer_id "
                        "WHERE cu.name LIKE 'RT10V%')"))
        db.execute(text("DELETE FROM icb_costings.calculations c USING icb_costings.customers cu "
                        "WHERE c.customer_id = cu.id AND cu.name LIKE 'RT10V%'"))
        db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                        "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'RT10V%')"))
        db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE 'RT10V%'"))
        db.execute(text("DELETE FROM icb_costings.materials WHERE material_code = 'RT10V'"))
        db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'RT10V%'"))
        db.commit()


def _csrf(page: Page) -> str:
    from app.database import SessionLocal, UserSession
    sid = next((c["value"] for c in page.context.cookies() if c["name"] == "session_id"), None)
    assert sid, "no session cookie"
    with SessionLocal() as db:
        row = db.get(UserSession, sid)
        return (row.csrf_token or "") if row else ""


def _approve(page: Page, body: dict) -> dict:
    base = _base()
    r = page.request.post(f"{base}/api/approve", data=json.dumps(body),
                          headers={"Origin": base, "X-CSRF-Token": _csrf(page), "Content-Type": "application/json"})
    assert r.ok, r.text()
    return r.json()


def _payload(ids: dict, customer: str = "customer", **over) -> dict:
    p = {"trailer_type_id": ids["tt"], "dimensions": dict(DIMS), "profit_margin": 5, "overrides": {},
         "override_reasons": {}, "chassis": {"enabled": False}, "user_excluded_bom_ids": [],
         "optional_sections_enabled": [], "customer_id": ids[customer], "ratio_value": 0.55, "ratio_label": "55%",
         "ui_snapshot": SNAP}
    p.update(over)
    return p


def _version(record_id: int) -> tuple[int, str]:
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=record_id).first()
        return int(json.loads(rec.result_json).get("version", 1)), rec.quote_number


@pytest.fixture(scope="module")
def staged(browser, live_server: str):
    from app.database import BillOfMaterial, Customer, Material, SessionLocal, TrailerType
    _purge()
    ids = {}
    with SessionLocal() as db:
        c1, c2, c3 = Customer(name=f"{MARK} CUSTOMER"), Customer(name=f"{MARK} OTHER"), Customer(name=f"{MARK} DUP")
        tt = TrailerType(name=f"{MARK} BODY", is_active=True, default_length=6.0, default_width=2.4, default_height=2.4)
        db.add_all([c1, c2, c3, tt])
        db.flush()
        for i, (name, price) in enumerate((("PANEL", 250.0), ("FLOOR", 300.0))):
            m = Material(name=f"{MARK} {name}", unit_of_measure="m²", price_per_unit=price, material_code=MARK,
                         is_active=True)
            db.add(m)
            db.flush()
            db.add(BillOfMaterial(trailer_type_id=tt.id, material_id=m.id, formula_expression="length*width",
                                  waste_percentage=0.0, bom_section=name, sort_order=10 * (i + 1)))
        db.commit()
        ids.update(customer=c1.id, other=c2.id, dup=c3.id, tt=tt.id, tt_name=tt.name)
    ctx = browser.new_context(base_url=live_server)
    page = ctx.new_page()
    assert page.request.post(f"{live_server}/api/mes/autologin", headers={"Origin": live_server}).ok
    first = _approve(page, _payload(ids, version_action="save_as_new"))
    ids.update(rev0=first["record_id"], qn=first["quote_number"])
    ctx.close()
    yield ids
    _purge()


def _rows(page: Page) -> list[dict]:
    """The board's rows in DOM order: record id + the Quote # cell's text. The id comes from the row's View link
    (/costings/results/<id>), which the v1.62.0 SPA carries too — so the negative control fails on what it shows,
    not on a missing attribute."""
    return page.evaluate("""() => [...document.querySelectorAll("[data-testid='costing-row']")].map(tr => ({
        id: +(tr.querySelector("a[href*='/costings/results/']")?.getAttribute('href') || '').split('/').pop(),
        text: tr.querySelector('td:nth-child(2)').innerText.replace(/\\s+/g, ' ').trim()}))""")


def _row(page: Page, record_id: int):
    """The board row of one record, by its View link (both SPAs carry it)."""
    return page.locator("[data-testid='costing-row']").filter(
        has=page.locator(f"a[href$='/costings/results/{record_id}']")).first


def _board(page: Page) -> None:
    page.goto("/mes-app/costings")
    expect(page.locator("[data-testid='costing-row']").first).to_be_visible(timeout=T)
    page.wait_for_timeout(1500)                       # the board's mount refresh has landed


def _save_as_rev_in_the_calculator(page: Page, record_id: int) -> tuple[int, str]:
    page.goto(f"/mes/calculator?edit={record_id}&stay=1")
    wait_calculator_ready(page)
    expect(page.locator("[data-testid='frozen-saved-line'], [data-testid='frozen-readonly']").first).to_be_visible(timeout=T)
    expect(page.locator("#grand-total")).not_to_have_text("—", timeout=T)
    page.click("#approve-btn")
    expect(page.locator("#modal-edit-save")).to_be_visible(timeout=T)
    offered = page.locator("#edit-newver-ver").inner_text().strip()
    page.click("[data-testid='edit-newver-btn']")
    new_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        new_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if new_id and new_id != record_id:
            break
    assert new_id and new_id != record_id, "no new revision was saved"
    return new_id, offered


# ── 1. the dispatch's journey ────────────────────────────────────────────────
def test_save_as_rev_twice_then_the_board_the_view_the_banner_and_the_exports(page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    r1, offered1 = _save_as_rev_in_the_calculator(page, ids["rev0"])
    r2, offered2 = _save_as_rev_in_the_calculator(page, ids["rev0"])          # again from REV 0
    assert (offered1, offered2) == ("REV 1", "REV 2"), "the modal offers the server's next REV"
    assert [_version(r) for r in (r1, r2)] == [(2, ids["qn"]), (3, ids["qn"])], "22 Oct: 2 and 2"
    ids.update(rev1=r1, rev2=r2)

    _board(page)
    mine = [r for r in _rows(page) if r["text"].startswith(ids["qn"])]
    assert [r["id"] for r in mine] == [r2, r1, ids["rev0"]], "together, latest on top"
    assert mine[0]["text"].startswith(f"{ids['qn']} · REV 2") and "Latest" in mine[0]["text"] and "3 revisions" in mine[0]["text"]
    assert mine[1]["text"] == f"{ids['qn']} · REV 1 · earlier" and mine[2]["text"] == f"{ids['qn']} · REV 0 · earlier"
    shot(page, "01-board-rev2-latest-rev1-rev0-earlier", journey=JOURNEY)

    _row(page, ids["rev0"]).locator("td").nth(2).click()
    page.wait_for_url(f"**/costings/**?id={ids['rev0']}")
    expect(page.locator("[data-testid='detail-rev']")).to_have_text("· REV 0", timeout=T)
    expect(page.locator("[data-testid='detail-latest-link']")).to_have_text("REV 2 is the latest →")
    expect(page.locator("[data-testid='revision-row']")).to_have_count(3)
    expect(page.locator("[data-testid='revision-row']").first).to_contain_text("REV 2")
    shot(page, "02-view-rev0-points-to-rev2", journey=JOURNEY)
    page.click("[data-testid='detail-latest-link']")
    page.wait_for_url(f"**?id={r2}")
    expect(page.locator("[data-testid='detail-latest']")).to_be_visible(timeout=T)

    page.goto(f"/mes/calculator?edit={ids['rev0']}&stay=1")
    wait_calculator_ready(page)
    expect(page.locator("[data-testid='edit-banner-rev']")).to_have_text("REV 0", timeout=T)
    expect(page.locator("[data-testid='edit-banner-latest']")).to_contain_text("REV 2 is the latest. Open it instead?")
    shot(page, "03-banner-rev0-rev2-is-the-latest", journey=JOURNEY)

    from openpyxl import load_workbook

    def heading(rid):
        resp = page.request.get(f"{_base()}/results/{rid}/export/excel")
        assert resp.ok, resp.status
        ws = load_workbook(io.BytesIO(resp.body())).worksheets[0]
        return next(str(c.value) for row in ws.iter_rows(max_row=6) for c in row if c.value not in (None, ""))
    assert heading(ids["rev0"]).startswith(f"{ids['qn']} — ") and "REV" not in heading(ids["rev0"])
    assert heading(r2).startswith(f"{ids['qn']} · REV 2 — ")


# ── 2. every row once; Accept acts on the row clicked ────────────────────────
def test_every_row_shows_once_and_accept_acts_on_the_row_clicked(page: Page, live_server: str, staged) -> None:
    ids = staged
    if "rev2" not in ids:
        pytest.skip("needs test 1's revisions")
    admin_session(page, base=live_server)
    _board(page)
    # leave the board inside the SPA, while the world moves on: another revision, and a new costing on top
    other = next(r for r in _rows(page) if not r["text"].startswith(ids["qn"]))
    _row(page, other["id"]).locator("td").nth(2).click()
    page.wait_for_url("**/costings/**")
    page.wait_for_timeout(1500)
    r3 = _approve(page, _payload(ids, version_action="new_version", edit_record_id=ids["rev0"]))["record_id"]
    newest = _approve(page, _payload(ids, "other", version_action="save_as_new"))["record_id"]
    page.click("a:has-text('Back to Costings')")
    page.wait_for_url("**/mes-app/costings")
    page.wait_for_timeout(2500)
    api = [c["id"] for c in page.request.get(f"{_base()}/api/calculations?limit=100").json()]
    dom = [r["id"] for r in _rows(page)]
    assert sorted(dom) == sorted(api) and len(dom) == len(set(dom)), f"rows shown twice: DOM {len(dom)} vs API {len(api)}"
    assert dom.index(newest) < dom.index(r3), "the new costing sits above the revised quote"
    shot(page, "04-board-every-row-once", journey=JOURNEY)

    hits = []

    def capture(route):
        hits.append(route.request.url.replace(_base(), ""))
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))
    page.route("**/api/calculations/*/accept", capture)
    page.route("**/api/production-jobs/from-calculation/*", capture)
    try:
        # the latest (REV 3): no question (the negative control of the ask)
        _row(page, r3).locator("button:has-text('Accept')").click()
        expect(page.locator("button:has-text('Confirm acceptance')")).to_be_visible(timeout=T)
        expect(page.locator("[data-testid='accept-older-line']")).to_have_count(0)
        page.click("button:has-text('Confirm acceptance')")
        page.wait_for_timeout(1500)
        assert hits[:2] == [f"/api/calculations/{r3}/accept", f"/api/production-jobs/from-calculation/{r3}"], hits
        # an older one (REV 0): asks first, and the answer accepts REV 0 — not the latest, not the oldest by accident
        hits.clear()
        _row(page, ids["rev0"]).locator("button:has-text('Accept')").click()
        expect(page.locator("[data-testid='accept-older-line']")).to_have_text(
            "This is REV 0. REV 3 is the latest. Accept REV 0 anyway?", timeout=T)
        shot(page, "05-accept-older-asks", journey=JOURNEY)
        page.click("button:has-text('Accept REV 0')")
        page.wait_for_timeout(1500)
        assert hits[:1] == [f"/api/calculations/{ids['rev0']}/accept"], hits
    finally:
        page.unroute("**/api/calculations/*/accept")
        page.unroute("**/api/production-jobs/from-calculation/*")


# ── 3. the duplicate modal ───────────────────────────────────────────────────
def test_the_duplicate_modal_saves_the_next_rev_of_the_quote_it_names(page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    first = _approve(page, _payload(ids, "dup", version_action="save_as_new"))
    page.goto("/mes/calculator?stay=1")
    wait_calculator_ready(page)
    page.locator("#trailer-select").select_option(str(ids["tt"]))
    page.locator("#cust-select").select_option(str(ids["dup"]))
    expect(page.locator("#grand-total")).not_to_have_text("—", timeout=T)
    page.wait_for_timeout(1200)                       # the debounced calculation has landed
    page.click("#approve-btn")
    expect(page.locator("#modal-duplicate")).to_be_visible(timeout=T)
    expect(page.locator("[data-testid='dup-replace-names']")).to_contain_text(f"{first['quote_number']} · REV 0")
    btn = page.locator("[data-testid='dup-revise-btn']")
    expect(btn).to_have_text(f"⊞ Save as REV 1 of {first['quote_number']}")
    shot(page, "06-duplicate-modal-names-the-quote", journey=JOURNEY)
    btn.click()
    new_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        new_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if new_id:
            break
    assert new_id and _version(new_id) == (2, first["quote_number"])
