"""v1.50 P3 §3.4 — repair from body categories + reusable repair templates (journey).

The WO's script, end to end on the REAL calculator surface:

  repair → set the vehicle (body type + 7.5 × 2.3 × 2.3) → "+ From body
  category" → SIDES → untick two lines → Add selected → the total rises by
  exactly the ticked line → add a stock line + a free-hand line → Save as
  template "Standard side repair" → save the repair → the repair quotation PDF
  carries the lines → a NEW repair → "+ From template" → the same items appear
  priced at TODAY's material-list prices (a price moved in between, and the
  template followed it) → Add selected → save.

Also: the guard — with no vehicle set, "+ From body category" refuses with a
plain toast and never opens the picker (Default 6: no silent no-op).

Money assertions compare DISPLAYED value against DISPLAYED value (the preview's
own numbers vs the surface totals) rather than against precomputed constants —
the server's section snapshot cache decides whether a fresh section's
multiplier is visible yet, and equality across the two surfaces holds either
way (both read the same snapshot). The absolute-quantity proof (34.5 = the
body costing's own SIDES number) lives in the §3.2 units, where the cache is
controlled.

Marker rows J150P3*, created + purged here — no real icb_costings data touched.
"""
from __future__ import annotations

import io
import os
import re

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, admin_session, shot  # noqa: E402

T = 20_000
JOURNEY = "repair_categories"

TT_NAME = "J150P3 BODY"
SEC_SIDES = "J150P3 SIDES"
SEC_FLOOR = "J150P3 FLOOR"
TPL_NAME = "J150P3 Standard side repair"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.repair_template_lines l "
        "USING icb_costings.repair_templates t "
        "WHERE l.template_id = t.id AND t.name LIKE 'J150P3%'"))
    db.execute(text("DELETE FROM icb_costings.repair_templates WHERE name LIKE 'J150P3%'"))
    _owned = (
        "SELECT c.id FROM icb_costings.calculations c "
        "LEFT JOIN icb_costings.trailer_types t ON t.id = c.trailer_type_id "
        "LEFT JOIN icb_costings.customers cu ON cu.id = c.customer_id "
        "WHERE t.name LIKE 'J150P3%' OR cu.name LIKE 'J150P3%'")
    for _tbl, _col in (("icb_mes.prejob_cards", "calculation_id"),
                       ("icb_mes.production_jobs", "calculation_record_id")):
        db.execute(text(f"DELETE FROM {_tbl} WHERE {_col} IN ({_owned})"))
    db.execute(text(
        "DELETE FROM icb_costings.calculations c USING icb_costings.customers cu "
        "WHERE c.customer_id = cu.id AND cu.name LIKE 'J150P3%'"))
    db.execute(text(
        "DELETE FROM icb_costings.bill_of_materials b USING icb_costings.trailer_types t "
        "WHERE b.trailer_type_id = t.id AND t.name LIKE 'J150P3%'"))
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE 'J150P3%'"))
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'J150P3%'"))
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE 'J150P3%'"))
    # An admin price edit (PUT /api/materials) writes price_history, which holds
    # an FK on materials — clear it first or this purge aborts on re-runs.
    db.execute(text(
        "DELETE FROM icb_costings.price_history ph USING icb_costings.materials m "
        "WHERE ph.material_id = m.id AND m.name LIKE 'J150P3%'"))
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE 'J150P3%'"))
    db.commit()


@pytest.fixture()
def p3_body():
    """One body with a three-line SIDES section (multiplier 2) and a FLOOR
    section; a catalogue material for the stock line; one customer."""
    from app.database import (SessionLocal, TrailerType, BillOfMaterial,
                              BOMSection, Material, Customer)
    with SessionLocal() as db:
        _purge(db)
        panel = Material(name="J150P3 SIDE PANEL", unit_of_measure="m2",
                         price_per_unit=100.0, is_active=True)
        rivet = Material(name="J150P3 RIVETS", unit_of_measure="each",
                         price_per_unit=2.0, is_active=True)
        sglue = Material(name="J150P3 SIDE GLUE", unit_of_measure="each",
                         price_per_unit=5.0, is_active=True)
        ply = Material(name="J150P3 FLOOR PLY", unit_of_measure="m2",
                       price_per_unit=80.0, is_active=True)
        glue = Material(name="J150P3 GLUE", unit_of_measure="each",
                        price_per_unit=250.0, is_active=True)
        db.add_all([panel, rivet, sglue, ply, glue])
        db.flush()
        s_sides = BOMSection(name=SEC_SIDES, sort_order=40, multiplier=2.0)
        s_floor = BOMSection(name=SEC_FLOOR, sort_order=41)
        db.add_all([s_sides, s_floor])
        db.flush()
        tt = TrailerType(name=TT_NAME, is_active=True, default_length=7.5,
                         default_width=2.3, default_height=2.3)
        cust = Customer(name="J150P3 Customer Ltd", bp_code="J150P31", is_active=True)
        db.add_all([tt, cust])
        db.flush()
        db.add_all([
            BillOfMaterial(trailer_type_id=tt.id, material_id=panel.id,
                           formula_expression="length * height", waste_percentage=0,
                           bom_section=SEC_SIDES, bom_section_id=s_sides.id, sort_order=1),
            BillOfMaterial(trailer_type_id=tt.id, material_id=rivet.id,
                           formula_expression="100", waste_percentage=10,
                           bom_section=SEC_SIDES, bom_section_id=s_sides.id, sort_order=2),
            BillOfMaterial(trailer_type_id=tt.id, material_id=sglue.id,
                           formula_expression="10", waste_percentage=0,
                           bom_section=SEC_SIDES, bom_section_id=s_sides.id, sort_order=3),
            BillOfMaterial(trailer_type_id=tt.id, material_id=ply.id,
                           formula_expression="length * width", waste_percentage=0,
                           bom_section=SEC_FLOOR, bom_section_id=s_floor.id, sort_order=4),
        ])
        db.commit()
        ids = {"tt": tt.id, "customer": cust.id, "glue_mat": glue.id}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _money(text: str) -> float:
    s = re.sub(r"[^0-9,.\-]", "", text or "")
    if "," in s and "." in s:
        s = s.replace(" ", "")
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s or 0)


def _grand_total(page: Page) -> float:
    return _money(page.locator("#grand-total").inner_text())


def _wait_for_total(page: Page, expected: float) -> float:
    """Poll until the headline SETTLES on `expected` (banked pattern: poll for
    the STATE across the 700 ms debounce, never for "it changed"; python-side
    because the CSP has no unsafe-eval)."""
    deadline = T / 1000.0
    waited = 0.0
    last = _grand_total(page)
    while waited < deadline:
        last = _grand_total(page)
        if abs(last - expected) < 0.05:
            return last
        page.wait_for_timeout(250)
        waited += 0.25
    raise AssertionError(f"the total settled on {last:.2f}, expected {expected:.2f}")


def _enter_repair_mode(page: Page) -> None:
    page.select_option("#trailer-select", "repair")
    expect(page.locator("#repair-add-source")).to_be_visible(timeout=T)


def _open_source_menu(page: Page) -> None:
    page.click("#repair-add-source")
    expect(page.locator("#repair-source-menu")).to_be_visible(timeout=T)


def _menu_item(page: Page, label: str):
    return page.locator("#repair-source-menu > div", has_text=label).first


def _lp_modal_open(page: Page) -> None:
    expect(page.locator("#modal-line-pick")).not_to_have_class(re.compile(r"\bhidden\b"), timeout=T)


def _lp_rows(page: Page):
    """The picker's own row model — [{d, ticked, total, price}]. page.evaluate
    on the bare identifiers (top-level `let`, so not window properties)."""
    return page.evaluate(
        "() => _lpRows.map(r => ({d: r.line.description, ticked: r.ticked,"
        " total: r.line.line_total, price: r.line.unit_price, qty: r.line.qty}))")


# ── The WO script, end to end ────────────────────────────────────────────────

def test_pull_a_category_save_a_template_and_reuse_it(page: Page, p3_body) -> None:
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    _enter_repair_mode(page)

    # ── The guard: no vehicle yet → the action explains itself, never a silent
    # no-op. The menu item is dimmed with a hint, and clicking it toasts.
    _open_source_menu(page)
    expect(_menu_item(page, "From body category")).to_contain_text(
        "Set the vehicle")
    _menu_item(page, "From body category").click()
    expect(page.locator("#modal-line-pick")).to_have_class(re.compile(r"\bhidden\b"))
    expect(page.locator(".toast-msg", has_text="body type and dimensions").first
           ).to_be_visible(timeout=T)

    # ── Set the vehicle. Picking the body type prefills its default dims —
    # exactly the WO's 7.5 × 2.3 × 2.3.
    page.select_option("#f-repair-vt", str(p3_body["tt"]))
    expect(page.locator("#f-repair-len")).to_have_value("7.5")
    expect(page.locator("#f-repair-wid")).to_have_value("2.3")
    expect(page.locator("#f-repair-hei")).to_have_value("2.3")

    # Deterministic money: no ratio, no margin.
    page.select_option("#f-ratio", "")
    page.fill("#f-margin", "0")

    # ── "+ From body category" → SIDES → preview.
    _open_source_menu(page)
    _menu_item(page, "From body category").click()
    _lp_modal_open(page)
    expect(page.locator("#lp-list")).to_contain_text(SEC_SIDES, timeout=T)
    page.locator("#lp-list label", has_text=SEC_SIDES).locator("input").check()
    expect(page.locator("#lp-primary-btn")).to_be_enabled()
    page.click("#lp-primary-btn")

    # Every line of the category, each ticked by default.
    expect(page.locator("#lp-list")).to_contain_text("J150P3 SIDE PANEL", timeout=T)
    rows = _lp_rows(page)
    assert [r["d"] for r in rows] == ["J150P3 SIDE PANEL", "J150P3 RIVETS", "J150P3 SIDE GLUE"]
    assert all(r["ticked"] for r in rows)
    shot(page, "category_preview", JOURNEY)

    # ── Untick two lines; only the ticked one may land.
    boxes = page.locator("#lp-list tbody input[type=checkbox]")
    boxes.nth(1).uncheck()
    boxes.nth(2).uncheck()
    expect(page.locator("#lp-summary")).to_contain_text("1 of 3")
    panel_total = _lp_rows(page)[0]["total"]
    assert panel_total > 0
    page.click("#lp-primary-btn")
    expect(page.locator("#modal-line-pick")).to_have_class(re.compile(r"\bhidden\b"), timeout=T)

    # The pulled line is an ordinary repair line wearing its origin chip, and
    # the total rises by EXACTLY the ticked line (baseline was zero).
    line_rows = page.locator("#repair-lines-body tr")
    expect(line_rows).to_have_count(1, timeout=T)
    expect(line_rows.first).to_contain_text("J150P3 SIDE PANEL")
    expect(line_rows.first).to_contain_text(SEC_SIDES)          # the chip
    _wait_for_total(page, panel_total)
    shot(page, "pulled_line_added", JOURNEY)

    # ── Two more lines the WO's template needs: one off the stock list …
    page.click("#repair-add-stock")
    expect(page.locator("#modal-stock-pick")).not_to_have_class(re.compile(r"\bhidden\b"), timeout=T)
    page.fill("#stock-search", "J150P3 GLUE")
    glue_row = page.locator("#stock-list div", has_text="J150P3 GLUE").first
    expect(glue_row).to_be_visible(timeout=T)
    glue_row.click()
    expect(page.locator("#modal-stock-pick")).to_have_class(re.compile(r"\bhidden\b"), timeout=T)
    # … and one free-hand.
    page.click("#repair-add-freehand")
    expect(page.locator("#modal-free-hand")).not_to_have_class(re.compile(r"\bhidden\b"), timeout=T)
    page.fill("#fh-description", "Labour")
    page.fill("#fh-qty", "8")
    page.fill("#fh-unit", "hours")
    page.fill("#fh-unit-price", "350")
    page.click("#fh-save-btn")
    expect(line_rows).to_have_count(3, timeout=T)
    _wait_for_total(page, panel_total + 250.0 + 2800.0)

    # ── Save as template — the three lines, ticked, named as the WO names it.
    _open_source_menu(page)
    _menu_item(page, "Save lines as a template").click()
    _lp_modal_open(page)
    expect(page.locator("#lp-summary")).to_contain_text("3 of 3")
    # No money is stored: the dialog says where each price will come from.
    expect(page.locator("#lp-list")).to_contain_text("list price at use")
    expect(page.locator("#lp-list")).to_contain_text("typed at use")
    page.fill("#lp-tpl-name", TPL_NAME)
    page.fill("#lp-tpl-desc", "Panel + glue + labour for a standard side repair")
    page.click("#lp-primary-btn")
    expect(page.locator("#modal-line-pick")).to_have_class(re.compile(r"\bhidden\b"), timeout=T)
    expect(page.locator(".toast-msg", has_text="saved").first).to_be_visible(timeout=T)

    # ── Save the repair. The type is typed LAST, after every line change — the
    # stale-payload fix this lane shipped is exactly what makes this order work.
    page.fill("#f-repair-type", "Side panel replacement")
    page.select_option("#cust-select", value=str(p3_body["customer"]))
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    page.click("#approve-btn")
    rec_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec_id:
            break
    assert rec_id, "the repair did not save"

    # The saved record: still a REPAIR (no trailer), lines with their origin,
    # and the vehicle block in input_state — reopening re-offers the pull.
    from app.database import SessionLocal, CalculationRecord
    import json as _json
    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=int(rec_id)).first()
        assert rec.is_repair is True and rec.trailer_type_id is None
        state = _json.loads(rec.result_json)["input_state"]
    assert state["repair_vehicle"]["trailer_type_id"] == p3_body["tt"]
    assert state["repair_vehicle"]["length"] == 7.5
    assert [l.get("origin") for l in state["repair_lines"]] == [SEC_SIDES, None, None]

    # ── Export the quote: the customer-facing PDF carries the lines.
    pdf = page.request.get(f"{base}/api/calculations/{int(rec_id)}/repair-quote.pdf")
    assert pdf.ok, f"repair quote failed: HTTP {pdf.status}"
    assert "pdf" in (pdf.headers.get("content-type") or "")
    from pypdf import PdfReader                      # hard dependency (requirements.txt)
    text = "\n".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(pdf.body())).pages)
    for needle in ("J150P3 SIDE PANEL", "J150P3 GLUE", "LABOUR"):
        assert needle in text, f"{needle!r} missing from the quotation PDF"

    # ── A NEW repair, from the template — priced at TODAY's prices. Move the
    # GLUE price first so "today" is provably not "when the template was saved".
    from app.database import Material
    with SessionLocal() as db:
        db.query(Material).filter_by(id=p3_body["glue_mat"]).update({"price_per_unit": 275.0})
        db.commit()

    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    _enter_repair_mode(page)
    _open_source_menu(page)
    _menu_item(page, "From template").click()
    _lp_modal_open(page)
    tpl_row = page.locator("#lp-list div", has_text=TPL_NAME).first
    expect(tpl_row).to_be_visible(timeout=T)
    tpl_row.click()

    # The same items, at the material list's CURRENT prices: the stock line
    # follows the price move (250 → 275); the pulled line is offered at its
    # material's live price; the plain free-hand line is priced at use.
    expect(page.locator("#lp-title")).to_contain_text(TPL_NAME, timeout=T)
    rows = _lp_rows(page)
    by_desc = {r["d"]: r for r in rows}
    assert set(by_desc) == {"J150P3 SIDE PANEL", "J150P3 GLUE", "LABOUR"}
    assert by_desc["J150P3 GLUE"]["price"] == 275.0
    assert by_desc["J150P3 SIDE PANEL"]["price"] == 100.0
    assert by_desc["LABOUR"]["price"] is None
    shot(page, "template_reuse_live_prices", JOURNEY)

    page.click("#lp-primary-btn")                    # Add selected (all three)
    expect(page.locator("#modal-line-pick")).to_have_class(re.compile(r"\bhidden\b"), timeout=T)
    expect(page.locator("#repair-lines-body tr")).to_have_count(3, timeout=T)
    expect(page.locator("#repair-lines-body")).to_contain_text("275")
    page.select_option("#f-ratio", "")
    page.fill("#f-margin", "0")
    # Each line at its template default qty × today's price: the panel at 100,
    # the glue (qty 1 — the stock picker's default) at the moved 275, labour at
    # the to-be-typed 0.
    panel_qty = by_desc["J150P3 SIDE PANEL"]["qty"]
    glue_qty = by_desc["J150P3 GLUE"]["qty"]
    _wait_for_total(page, round(panel_qty * 100.0 + glue_qty * 275.0, 2))
    shot(page, "template_lines_on_new_repair", JOURNEY)

    # And it saves like any repair.
    page.fill("#f-repair-type", "Second side repair")
    page.select_option("#cust-select", value=str(p3_body["customer"]))
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    page.click("#approve-btn")
    rec2 = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec2 = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec2 and rec2 != rec_id:
            break
    assert rec2 and rec2 != rec_id, "the second repair did not save"
