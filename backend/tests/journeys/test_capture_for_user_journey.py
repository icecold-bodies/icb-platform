"""v1.52 — an admin captures a costing FOR another user (journey).

The WO's script, on the real surfaces:

  admin opens the calculator → "Capture for" defaults to admin → picks Nadie → the
  repair's "Your contact (ICB)" prefill follows → save → the board's Rep reads Nadie →
  it is in Nadie's "My costings" AND still in admin's, and NOT in Lezette's → the repair
  quotation's Your Contact reads Nadie → the costing page says "Captured for Nadie by
  admin" → re-assign to Lezette while pending → both moves are journaled → accept →
  the re-assign control is gone and the API refuses it.

  The regression half: a save with the dropdown untouched stores exactly what it did
  before this lane (NULL rep, no journal), and a non-admin sees no control and is
  refused by the API when they try anyway.

  The Pre-Job Card half: an accepted BODY costing captured for Nadie opens its card
  with Nadie in the Sales Rep dropdown.

Every browser identity gets its OWN context: the demo autologin keeps an existing
session, so a second login in the same context would still be admin.

Marker rows J152CF* / j152cf_* only — created and purged here. Base-aware throughout
(MES_BASE), so this file can run alone on a side port.
"""
from __future__ import annotations

import io
import json
import os
import re

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, admin_session, role_session, shot  # noqa: E402

T = 20_000
JOURNEY = "capture_for_user"
MARK = "J152CF"
NADIE = "j152cf_nadie"
LEZETTE = "j152cf_lezette"
CUST = f"{MARK} Carriers"
TT_NAME = f"{MARK} BODY"
SECTION = f"{MARK} FLOOR"
TPL_NAME = f"{MARK} Template"


def _base() -> str:
    return os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")


def _purge(db) -> None:
    from sqlalchemy import text
    owned = ("SELECT c.id FROM icb_costings.calculations c "
             "JOIN icb_costings.customers cu ON cu.id = c.customer_id "
             "WHERE cu.name LIKE 'J152CF%'")
    for tbl, col in (("icb_mes.prejob_cards", "calculation_id"),
                     ("icb_mes.production_jobs", "calculation_record_id")):
        db.execute(text(f"DELETE FROM {tbl} WHERE {col} IN ({owned})"))
    # The capture journal goes with its costings (ON DELETE CASCADE, 0048).
    db.execute(text("DELETE FROM icb_costings.calculations c USING icb_costings.customers cu "
                    "WHERE c.customer_id = cu.id AND cu.name LIKE 'J152CF%'"))
    db.execute(text("DELETE FROM icb_mes.prejob_templates WHERE name LIKE 'J152CF%'"))
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'J152CF%')"))
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE 'J152CF%'"))
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE 'J152CF%'"))
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE 'J152CF%'"))
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'J152CF%'"))
    marker_users = "SELECT id FROM icb_costings.users WHERE username LIKE 'j152cf\\_%'"
    db.execute(text(f"DELETE FROM icb_costings.user_sessions WHERE user_id IN ({marker_users})"))
    db.execute(text("DELETE FROM icb_costings.users WHERE username LIKE 'j152cf\\_%'"))
    db.commit()


@pytest.fixture(scope="module")
def staged():
    """Nadie + Lezette (role 'sales', so the Pre-Job Card's Sales Rep dropdown lists
    them), a marker customer, and a one-row body for the BODY costing."""
    from app.database import (SessionLocal, User, Customer, Material, BOMSection,
                              TrailerType, BillOfMaterial)
    with SessionLocal() as db:
        _purge(db)
        nadie = User(username=NADIE, password_hash="x", role="sales", email="")
        lezette = User(username=LEZETTE, password_hash="x", role="sales", email="")
        cust = Customer(name=CUST, bp_code=f"{MARK}1", is_active=True)
        mat = Material(name=f"{TT_NAME} PLYWOOD", unit_of_measure="m2",
                       price_per_unit=100.0, is_active=True)
        sec = BOMSection(name=SECTION, sort_order=10, is_optional=False)
        tt = TrailerType(name=TT_NAME, is_active=True, default_length=6.0,
                         default_width=2.5, default_height=2.4)
        db.add_all([nadie, lezette, cust, mat, sec, tt])
        db.flush()
        db.add(BillOfMaterial(trailer_type_id=tt.id, material_id=mat.id,
                              formula_expression="10", waste_percentage=0,
                              bom_section=SECTION, bom_section_id=sec.id, sort_order=1))
        admin = db.query(User).filter_by(username="admin").first()
        db.commit()
        ids = {"admin": admin.id, "nadie": nadie.id, "lezette": lezette.id,
               "customer": cust.id, "tt": tt.id}
    yield ids
    with SessionLocal() as db:
        _purge(db)


# ── helpers ──────────────────────────────────────────────────────────────────

def _csrf(page: Page) -> str:
    from app.database import SessionLocal, UserSession
    sid = next((c["value"] for c in page.context.cookies() if c["name"] == "session_id"), None)
    assert sid, "no session cookie — autologin did not establish a session"
    with SessionLocal() as db:
        row = db.get(UserSession, sid)
        return (row.csrf_token or "") if row else ""


def _post(page: Page, path: str, body: dict | None = None):
    base = _base()
    return page.request.post(f"{base}{path}", data=json.dumps(body or {}),
                             headers={"Origin": base, "X-CSRF-Token": _csrf(page),
                                      "Content-Type": "application/json"})


def _as(browser, username: str) -> Page:
    """A fresh context signed in as `username` (its own cookie jar)."""
    ctx = browser.new_context(base_url=_base(), viewport={"width": 1440, "height": 900})
    p = ctx.new_page()
    p.set_default_timeout(15_000)
    role_session(p, username, base=_base())
    return p


def _row(rec_id: int) -> dict:
    from sqlalchemy import text
    from app.database import SessionLocal
    with SessionLocal() as db:
        return dict(db.execute(text("SELECT * FROM icb_costings.calculations WHERE id = :i"),
                               {"i": rec_id}).mappings().first())


def _journal(rec_id: int) -> list[tuple]:
    from sqlalchemy import text
    from app.database import SessionLocal
    with SessionLocal() as db:
        return [tuple(r) for r in db.execute(text(
            "SELECT action, from_username, to_username, actor_username "
            "FROM icb_costings.calculations_sales_rep_audit WHERE calculation_id = :i "
            "ORDER BY created_at, id"), {"i": rec_id})]


def _add_free_hand(page: Page, description: str, qty: str, price: str) -> None:
    page.click("#repair-add-freehand")
    expect(page.locator("#modal-free-hand")).not_to_have_class(re.compile(r"\bhidden\b"), timeout=T)
    page.fill("#fh-description", description)
    page.fill("#fh-qty", qty)
    page.fill("#fh-unit-price", price)
    page.click("#fh-save-btn")
    expect(page.locator("#modal-free-hand")).to_have_class(re.compile(r"\bhidden\b"), timeout=T)


def _start_repair(page: Page, customer_id: int) -> None:
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", "repair")
    expect(page.locator("#repair-add-source")).to_be_visible(timeout=T)
    page.select_option("#f-ratio", "")
    page.fill("#f-margin", "0")
    _add_free_hand(page, "Panel labour", "2", "300")
    expect(page.locator("#repair-lines-body tr")).to_have_count(1, timeout=T)
    page.fill("#f-repair-type", "Side panel replacement")
    page.select_option("#cust-select", value=str(customer_id))


def _save(page: Page) -> int:
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    page.click("#approve-btn")
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec_id:
            return int(rec_id)
    raise AssertionError("the costing did not save")


def _board_row(page: Page, quote_number: str):
    return page.locator("[data-testid='costing-row']").filter(has_text=quote_number).first


def _pdf_text(page: Page, rec_id: int) -> str:
    from pypdf import PdfReader
    resp = page.request.get(f"{_base()}/api/calculations/{rec_id}/repair-quote.pdf")
    assert resp.ok, f"repair quote failed: HTTP {resp.status}"
    return "\n".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(resp.body())).pages)


# ── the journey ──────────────────────────────────────────────────────────────

def test_admin_captures_a_repair_for_nadie_then_reassigns_it(page: Page, browser, staged) -> None:
    base = _base()
    admin_session(page, base=base)
    _start_repair(page, staged["customer"])

    # "Capture for" — admin only, defaults to the logged-in user, lists every user
    # with their role.
    picker = page.locator("#capture-for-select")
    expect(picker).to_be_visible(timeout=T)
    expect(picker).to_have_value(str(staged["admin"]))
    expect(picker.locator(f"option[value='{staged['nadie']}']")).to_have_text(
        f"{NADIE} (sales)", timeout=T)
    expect(page.locator("#f-repair-contact")).to_have_value("admin")

    picker.select_option(str(staged["nadie"]))
    # The quotation's "Your contact (ICB)" prefill follows the pick; the phone is typed.
    expect(page.locator("#f-repair-contact")).to_have_value(NADIE)
    expect(page.locator("#capture-for-note")).to_contain_text(f"Credited to {NADIE}")
    page.fill("#f-repair-contact-tel", "082 000 0152")
    shot(page, "01-calculator-capture-for-nadie", JOURNEY)

    rec_id = _save(page)
    row = _row(rec_id)
    assert row["user_id"] == staged["admin"], "authorship must never be rewritten"
    assert row["sales_rep_user_id"] == staged["nadie"]
    expect(picker).to_be_disabled(timeout=T)      # saved once — the costing page re-assigns
    quote_no = row["quote_number"]
    assert quote_no

    # ── the board: Rep reads Nadie; admin's own list keeps it ────────────────
    page.goto("/mes-app/costings")
    expect(page.get_by_test_id("costings-table")).to_be_visible(timeout=T)
    expect(_board_row(page, quote_no).get_by_test_id("costing-rep")).to_have_text(NADIE, timeout=T)
    page.get_by_role("button", name="My costings").click()
    expect(_board_row(page, quote_no)).to_be_visible(timeout=T)
    shot(page, "02-board-rep-nadie-admin-my-costings", JOURNEY)

    # ── Nadie's own list has it; Lezette's does not ──────────────────────────
    nadie_page = _as(browser, NADIE)
    try:
        nadie_page.goto("/mes-app/costings")
        expect(nadie_page.get_by_test_id("costings-table")).to_be_visible(timeout=T)
        nadie_page.get_by_role("button", name="My costings").click()
        expect(_board_row(nadie_page, quote_no)).to_be_visible(timeout=T)
        shot(nadie_page, "03-board-my-costings-as-nadie", JOURNEY)

        # A non-admin sees no control on the calculator …
        nadie_page.goto("/mes/calculator?stay=1")
        expect(nadie_page.locator("#trailer-select")).to_be_visible(timeout=T)
        expect(nadie_page.locator("#capture-for-block")).to_have_count(0)
        assert nadie_page.evaluate("() => canCaptureForUser") is False
        # … and is refused by the API when she tries anyway.
        refused = _post(nadie_page, "/api/approve", {
            "is_repair": True, "trailer_type_id": None, "customer_id": staged["customer"],
            "repair_type": "attempt", "profit_margin": 0, "dimensions": {},
            "repair_lines": [{"kind": "free_hand", "key": "x", "description": "x",
                              "qty": 1, "unit": "each", "unit_price": 1}],
            "sales_rep_user_id": staged["lezette"]})
        assert refused.status == 403, f"expected 403, got {refused.status}: {refused.text()[:300]}"
    finally:
        nadie_page.context.close()

    lezette_page = _as(browser, LEZETTE)
    try:
        lezette_page.goto("/mes-app/costings")
        expect(lezette_page.get_by_test_id("costings-table")).to_be_visible(timeout=T)
        expect(_board_row(lezette_page, quote_no)).to_be_visible(timeout=T)   # All: everyone sees it
        lezette_page.get_by_role("button", name="My costings").click()
        expect(_board_row(lezette_page, quote_no)).to_have_count(0, timeout=T)
    finally:
        lezette_page.context.close()

    # ── the quotation's Your Contact reads Nadie ─────────────────────────────
    text = _pdf_text(page, rec_id)
    assert "Your Contact" in text and NADIE in text, text[:600]

    # ── the costing page: attribution line, then re-assign while pending ─────
    page.goto("/mes-app/costings")
    _board_row(page, quote_no).click()
    panel = page.get_by_test_id("capture-for-panel")
    expect(panel).to_be_visible(timeout=T)
    expect(panel.get_by_test_id("capture-for-rep")).to_have_text(NADIE)
    lines = panel.get_by_test_id("capture-for-line")
    expect(lines).to_have_count(1)
    expect(lines.nth(0)).to_contain_text(f"Captured for {NADIE} by admin · ")
    shot(page, "04-detail-captured-for-nadie", JOURNEY)

    reassign = panel.get_by_test_id("capture-for-reassign")
    expect(reassign.locator(f"option[value='{staged['lezette']}']")).to_have_count(1, timeout=T)
    reassign.select_option(str(staged["lezette"]))
    panel.get_by_test_id("capture-for-reassign-save").click()
    expect(panel.get_by_test_id("capture-for-rep")).to_have_text(LEZETTE, timeout=T)
    expect(lines).to_have_count(2, timeout=T)
    expect(lines.nth(1)).to_contain_text(f"Re-assigned from {NADIE} to {LEZETTE} by admin · ")
    shot(page, "05-detail-reassigned-to-lezette", JOURNEY)
    assert _journal(rec_id) == [("capture", "admin", NADIE, "admin"),
                                ("reassign", NADIE, LEZETTE, "admin")]
    assert _row(rec_id)["user_id"] == staged["admin"]

    page.goto("/mes-app/costings")
    expect(_board_row(page, quote_no).get_by_test_id("costing-rep")).to_have_text(LEZETTE, timeout=T)

    # ── accept: the attribution freezes with the rest of the quote ───────────
    acc = _post(page, f"/api/calculations/{rec_id}/accept")
    assert acc.ok, f"accept failed: HTTP {acc.status} {acc.text()[:200]}"
    page.reload()
    _board_row(page, quote_no).click()
    panel = page.get_by_test_id("capture-for-panel")
    expect(panel.get_by_test_id("capture-for-rep")).to_have_text(LEZETTE, timeout=T)
    expect(panel.get_by_test_id("capture-for-line")).to_have_count(2)
    expect(panel.get_by_test_id("capture-for-reassign")).to_have_count(0)
    frozen = _post(page, f"/api/calculations/{rec_id}/sales-rep",
                   {"sales_rep_user_id": staged["nadie"]})
    assert frozen.status == 409, f"expected 409, got {frozen.status}: {frozen.text()[:300]}"
    assert _row(rec_id)["sales_rep_user_id"] == staged["lezette"]


def test_an_untouched_dropdown_saves_exactly_as_before(page: Page, staged) -> None:
    admin_session(page, base=_base())
    _start_repair(page, staged["customer"])
    expect(page.locator("#capture-for-select")).to_have_value(str(staged["admin"]), timeout=T)
    rec_id = _save(page)
    row = _row(rec_id)
    assert row["sales_rep_user_id"] is None, "an untouched dropdown must store NULL, as before"
    assert _journal(rec_id) == []
    page.goto("/mes-app/costings")
    expect(_board_row(page, row["quote_number"]).get_by_test_id("costing-rep")).to_have_text(
        "admin", timeout=T)


def test_an_admin_edit_keeps_who_the_costing_is_for(page: Page, staged) -> None:
    """Reopening a captured costing re-selects its rep. Without that the dropdown would
    come back on "you", and an admin who only fixed a line would silently take the
    costing over on Overwrite."""
    admin_session(page, base=_base())
    made = _post(page, "/api/approve", {
        "is_repair": True, "trailer_type_id": None, "customer_id": staged["customer"],
        "repair_type": "Door seal", "profit_margin": 0, "dimensions": {},
        "icb_contact_name": NADIE, "icb_contact_phone": "082 000 0152",
        "repair_lines": [{"kind": "free_hand", "key": "e1", "description": "Seal kit",
                          "qty": 1, "unit": "each", "unit_price": 450}],
        "sales_rep_user_id": staged["nadie"]})
    assert made.ok, f"save failed: HTTP {made.status} {made.text()[:300]}"
    rec_id = made.json()["record_id"]

    page.goto(f"/mes/calculator?edit={rec_id}&stay=1")
    expect(page.locator("#repair-add-freehand")).to_be_visible(timeout=T)
    expect(page.locator("#capture-for-select")).to_have_value(str(staged["nadie"]), timeout=T)
    expect(page.locator("#capture-for-note")).to_contain_text(f"Credited to {NADIE}")
    expect(page.locator("#f-repair-contact")).to_have_value(NADIE)
    page.fill("#f-repair-type", "Door seal (edited)")
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    page.click("#approve-btn")
    overwrite = page.locator("#modal-edit-save button[onclick*='overwrite']")
    expect(overwrite).to_be_visible(timeout=T)
    overwrite.click()
    expect(page.locator("#approve-btn")).to_contain_text("Saved", timeout=T)

    row = _row(rec_id)
    assert json.loads(row["result_json"])["repair_type"] == "Door seal (edited)", "the edit did not save"
    assert row["sales_rep_user_id"] == staged["nadie"], "the edit silently re-assigned the costing"
    assert row["user_id"] == staged["admin"]
    assert _journal(rec_id) == [("capture", "admin", NADIE, "admin")]


def test_the_prejob_card_defaults_to_the_captured_for_rep(page: Page, staged) -> None:
    """A BODY costing captured for Nadie, accepted and anchored to a job, opens its
    Pre-Job Card with Nadie already chosen as the Sales Rep."""
    from app.database import SessionLocal, Branch
    from app.models.mes import PrejobTemplate, ProductionJob
    admin_session(page, base=_base())
    made = _post(page, "/api/approve", {
        "trailer_type_id": staged["tt"], "customer_id": staged["customer"],
        "dimensions": {"length": 6.0, "width": 2.5, "height": 2.4},
        "profit_margin": 0, "version_action": "save_as_new",
        "sales_rep_user_id": staged["nadie"]})
    assert made.ok, f"save failed: HTTP {made.status} {made.text()[:300]}"
    rec_id = made.json()["record_id"]
    quote_no = made.json()["quote_number"]
    assert _post(page, f"/api/calculations/{rec_id}/accept").ok
    with SessionLocal() as db:
        branch = db.query(Branch).order_by(Branch.id).first()
        db.add(PrejobTemplate(name=TPL_NAME, body_type="chiller", size_category="big",
                              product_line="standard", is_active=True, created_by="j152cf",
                              header_format=f"{MARK} header",
                              sections=[{"name": "GRP SECTION", "items": [{"text": "x"}]}]))
        db.add(ProductionJob(calculation_record_id=rec_id, branch_id=branch.id, source="quote",
                             status="accepted", job_number=f"{MARK}01"))
        db.commit()

    page.goto("/mes-app/costings")
    expect(page.get_by_test_id("costings-dashboard")).to_be_visible(timeout=T)
    row = _board_row(page, quote_no)
    expect(row.get_by_test_id("costing-rep")).to_have_text(NADIE, timeout=T)
    row.get_by_role("button", name="Pre-Job Card").click()
    expect(page.get_by_test_id("prejob-card-modal")).to_be_visible(timeout=T)
    page.get_by_test_id("prejob-template-select").select_option(label=TPL_NAME)
    page.get_by_test_id("prejob-create-draft").click()
    rep = page.get_by_test_id("prejob-sales-rep")
    expect(rep).to_have_value(str(staged["nadie"]), timeout=T)
    expect(rep.locator("option:checked")).to_have_text(NADIE)
    shot(page, "06-prejob-card-sales-rep-nadie", JOURNEY)
