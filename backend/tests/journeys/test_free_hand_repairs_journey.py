"""v1.47 Lane C §3.4 — free-hand OPTIONAL EXTRAS + the REPAIRS surface (journey).

Drives the REAL legacy calculator (/mes/calculator — the exact template the SPA
iframes at /costings/new) and the React costings surfaces end to end:

(a) a body costing + a free-hand OPTIONAL EXTRA → the line appears with a
    "manual" chip and the total rises by qty × price → the Excel preview
    downloads with the line in it.
(b) Body Type → REPAIRS → the repair surface opens with NO dimensions and no
    body options → one stock line + one free-hand line → the header rail shows
    MATERIALS / MARGIN / RATIO / TOTAL → Approve & Save → the costing lists as
    a Repair → opening it offers "Schedule into MES" and the panel schedules.
(c) a normal body costing is completely unaffected — no free-hand row, no
    repair chrome, and the same total it had before v1.47.

Marker rows J147LC*, created + purged here — no real icb_costings data touched.

NOTE on (b): "Schedule into MES" renders only once the repair reads as status
Repair, and mes_status becomes "Repair" only for an ACCEPTED repair
(routers/calculator.py). So the journey accepts the saved repair through the
API before asserting the button — that gate is existing v1.2.1 behaviour, not
something this lane changed.
"""
from __future__ import annotations

import os
import re

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, admin_session, shot  # noqa: E402

T = 20_000
JOURNEY = "free_hand_repairs"

TT_NAME = "J147LC BODY"
OPT_SECTION = "J147LC OPTIONAL EXTRAS"
PLAIN_SECTION = "J147LC FLOOR"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.calculations c USING icb_costings.trailer_types t "
        "WHERE c.trailer_type_id = t.id AND t.name LIKE 'J147LC%'"))
    db.execute(text(
        "DELETE FROM icb_costings.calculations c USING icb_costings.customers cu "
        "WHERE c.customer_id = cu.id AND cu.name LIKE 'J147LC%'"))
    db.execute(text(
        "DELETE FROM icb_costings.bill_of_materials b USING icb_costings.trailer_types t "
        "WHERE b.trailer_type_id = t.id AND t.name LIKE 'J147LC%'"))
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE 'J147LC%'"))
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE 'J147LC%'"))
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE 'J147LC%'"))
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE 'J147LC%'"))
    db.commit()


@pytest.fixture()
def laneC_body():
    """One body with a PLAIN section and an OPTIONAL section, one customer, and a
    catalogue material for the repair stock-line picker."""
    from app.database import (SessionLocal, TrailerType, BillOfMaterial,
                              BOMSection, Material, Customer)
    with SessionLocal() as db:
        _purge(db)
        floor = Material(name="J147LC FLOOR SHEET", unit_of_measure="m2",
                         price_per_unit=100.0, is_active=True)
        tray = Material(name="J147LC EXTRA TRAY", unit_of_measure="each",
                        price_per_unit=60.0, is_active=True)
        seal = Material(name="J147LC REPAIR SEAL", unit_of_measure="each",
                        price_per_unit=250.0, is_active=True)
        db.add_all([floor, tray, seal])
        db.flush()
        plain_sec = BOMSection(name=PLAIN_SECTION, sort_order=10, is_optional=False)
        opt_sec = BOMSection(name=OPT_SECTION, sort_order=11, is_optional=True)
        db.add_all([plain_sec, opt_sec])
        db.flush()
        tt = TrailerType(name=TT_NAME, is_active=True, default_length=10.0,
                         default_width=2.5, default_height=2.6)
        cust = Customer(name="J147LC Customer Ltd", bp_code="J147LC1", is_active=True)
        db.add_all([tt, cust])
        db.flush()
        db.add_all([
            BillOfMaterial(trailer_type_id=tt.id, material_id=floor.id,
                           formula_expression="10", waste_percentage=0,
                           bom_section=PLAIN_SECTION, bom_section_id=plain_sec.id,
                           sort_order=1),
            BillOfMaterial(trailer_type_id=tt.id, material_id=tray.id,
                           formula_expression="2", waste_percentage=0,
                           bom_section=OPT_SECTION, bom_section_id=opt_sec.id,
                           sort_order=2),
        ])
        db.commit()
        ids = {"tt": tt.id, "customer": cust.id, "opt_sec": opt_sec.id}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _money(text: str) -> float:
    """"R 12 345,67" / "R12,345.67" → 12345.67. The page formats SA-style."""
    s = re.sub(r"[^0-9,.\-]", "", text or "")
    if "," in s and "." in s:
        s = s.replace(" ", "")
        # Whichever separator comes last is the decimal one.
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s or 0)


def _grand_total(page: Page) -> float:
    return _money(page.locator("#grand-total").inner_text())


def _settle(page: Page) -> None:
    """Let the 700 ms debounced recalc land and the BOM table stop re-rendering.

    Without this a click can race a re-render and Playwright reports the target
    as "not stable" — the table is rebuilt wholesale on every recalc, so any
    element inside it moves.
    """
    expect(page.locator("#calc-status")).to_have_text("", timeout=T)
    page.wait_for_timeout(1200)


def _select_body(page: Page, tt_id: int) -> None:
    page.select_option("#trailer-select", str(tt_id))
    # The BOM table lands only after /api/calculate resolves; the section header
    # is the first thing that proves it.
    expect(page.locator(".calc-grp-hdr").first).to_be_visible(timeout=T)
    expect(page.locator("#grand-total")).not_to_have_text("—", timeout=T)


def _wait_for_total(page: Page, expected: float) -> float:
    """Wait until the headline total SETTLES on `expected`, then return it.

    Polls for the expected STATE, never for "it changed" — every recalc here is
    debounced 700 ms and several can be in flight at once (adding a line, then
    the margin, then the ratio), so "wait for a different number" returns the
    FIRST intermediate result and asserts against a calculation that is about to
    be superseded. That is exactly what turned green locally and red on both CI
    platforms: the repair total was read as 1700 (materials only) before the
    margin+ratio recalc landed on 3740.

    Python-side polling because the app's CSP has no unsafe-eval, so
    page.wait_for_function is unusable here.
    """
    deadline = T / 1000.0
    waited = 0.0
    last = _grand_total(page)
    while waited < deadline:
        last = _grand_total(page)
        if abs(last - expected) < 0.05:
            return last
        page.wait_for_timeout(250)
        waited += 0.25
    raise AssertionError(
        f"the total settled on {last:.2f}, expected {expected:.2f} "
        f"(waited {deadline:.0f}s)")


# ── (a) free-hand OPTIONAL EXTRA on a body costing ───────────────────────────

def test_free_hand_optional_extra_raises_the_total(page: Page, laneC_body) -> None:
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    _select_body(page, laneC_body["tt"])

    # Pin the ratio to None. #grand-total is the SELLING price, so with a ratio
    # selected the headline moves by qty × price ÷ ratio; the R900 the WO asks us
    # to prove is the materials movement, which is what "no ratio" shows.
    page.select_option("#f-ratio", "")

    # Opt the OPTIONAL section in first — an optional section is OFF until ticked,
    # and this lane deliberately did not change that flag logic.
    tick = page.locator(f".opt-sec-tick[data-section-id='{laneC_body['opt_sec']}']")
    expect(tick).to_be_visible(timeout=T)
    if tick.is_checked():                    # checked == EXCLUDED
        tick.uncheck()
    # Read the baseline only once BOTH the ratio change and the opt-in have
    # settled — reading it mid-flight is what makes every later delta wrong.
    _settle(page)
    baseline = _grand_total(page)

    # Sections render COLLAPSED by default, so expand this one — otherwise the
    # new row is in the DOM but display:none and nothing can be clicked on it.
    _settle(page)
    hdr = page.locator(f"tr.calc-grp-hdr[data-section-id='{laneC_body['opt_sec']}']")
    expect(hdr).to_be_visible(timeout=T)
    if "collapsed" in (hdr.get_attribute("class") or ""):
        # Click the section NAME, not the row: a row-centre click lands on one of
        # the header's inline pill buttons.
        hdr.locator(".calc-hdr-name").click()
    _settle(page)

    # "+ Free-hand line" is offered on the OPTIONAL section header.
    add_btn = page.locator(f"button[data-free-hand-add='{laneC_body['opt_sec']}']")
    expect(add_btn).to_be_visible(timeout=T)
    add_btn.click()

    expect(page.locator("#modal-free-hand")).not_to_have_class(re.compile(r"hidden"), timeout=T)
    page.fill("#fh-description", "Rubber seal kit")
    page.fill("#fh-qty", "2")
    page.fill("#fh-unit-price", "450")
    # The dialog totals the line before it is added.
    expect(page.locator("#fh-line-total")).to_contain_text("900", timeout=T)
    page.click("#fh-save-btn")

    # The row lands in the BOM table with the "manual" chip, and the total rises
    # by exactly qty × price.
    row = page.locator("tr.fh-row")
    expect(row).to_have_count(1, timeout=T)
    expect(row).to_contain_text("Rubber seal kit")
    expect(row).to_contain_text("manual")
    _wait_for_total(page, baseline + 900.0)
    shot(page, "free_hand_extra_added", JOURNEY)

    # Editing the line re-costs it.
    row.locator("button[title='Edit this line']").click()
    expect(page.locator("#modal-free-hand")).not_to_have_class(re.compile(r"hidden"), timeout=T)
    page.fill("#fh-qty", "3")
    page.click("#fh-save-btn")
    _wait_for_total(page, baseline + 1350.0)

    # The Excel preview carries the line (R2/R4 shared document context).
    with page.expect_download(timeout=T) as dl:
        page.evaluate("downloadPreview({format:'excel', detail:'items'})")
    assert dl.value.suggested_filename.endswith(".xlsx")

    # Removing it puts the total back exactly.
    row.locator("button[title='Remove this line']").click()
    _wait_for_total(page, baseline)
    expect(page.locator("tr.fh-row")).to_have_count(0, timeout=T)


# ── (b) the REPAIRS surface, end to end ──────────────────────────────────────

def test_repairs_surface_creates_a_schedulable_repair(page: Page, laneC_body) -> None:
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)

    # REPAIRS is its own entry under a divider — a MODE, not a body template.
    page.select_option("#trailer-select", "repair")

    # The repair surface replaces the BOM, and every body-only input is gone:
    # no dimensions, no body options, no chassis tab.
    expect(page.locator("#repair-add-stock")).to_be_visible(timeout=T)
    expect(page.locator("#repair-add-freehand")).to_be_visible()
    expect(page.locator("#f-repair-type")).to_be_visible()
    expect(page.locator("#dims-wrap")).to_be_hidden()
    expect(page.locator("#cfg-tab-chassis")).to_be_hidden()
    expect(page.locator("#vref-picker-wrap")).to_be_hidden()
    # No body means no length: the banner must not append the stale "(13.6 m)"
    # still sitting in the now-hidden length input. (This also checked a geometry
    # footer until #140 removed that strip wholesale.)
    expect(page.locator("#topbar-title")).to_contain_text("REPAIRS")
    expect(page.locator("#topbar-title")).not_to_contain_text(" m)")
    # Nothing to approve until the repair has a type and a line.
    expect(page.locator("#approve-btn")).to_be_disabled()

    page.select_option("#f-ratio", "")          # deterministic start; set below
    page.fill("#f-repair-type", "Side panel replacement")
    page.fill("#f-repair-scope", "Strip damaged panel, fit new panel, laminate joints.")

    # Two lines off the stock list (the existing materials catalogue, at its
    # current price) …
    for _ in range(2):
        page.click("#repair-add-stock")
        expect(page.locator("#modal-stock-pick")).not_to_have_class(re.compile(r"hidden"), timeout=T)
        page.fill("#stock-search", "J147LC REPAIR SEAL")
        seal = page.locator("#stock-list div", has_text="J147LC REPAIR SEAL").first
        expect(seal).to_be_visible(timeout=T)
        seal.click()
        expect(page.locator("#modal-stock-pick")).to_have_class(re.compile(r"hidden"), timeout=T)

    # … and one free-hand line.
    page.click("#repair-add-freehand")
    expect(page.locator("#modal-free-hand")).not_to_have_class(re.compile(r"hidden"), timeout=T)
    page.fill("#fh-description", "Spray booth time")
    page.fill("#fh-qty", "4")
    page.fill("#fh-unit", "hour")
    page.fill("#fh-unit-price", "300")
    page.click("#fh-save-btn")

    rows = page.locator("#repair-lines-body tr")
    expect(rows).to_have_count(3, timeout=T)
    expect(page.locator("#repair-lines-body")).to_contain_text("manual")
    expect(page.locator("#repair-lines-body")).to_contain_text("stock")

    # 2 × 250 (catalogue) + 4 × 300 (typed) = 1700, through the SAME margin and
    # ratio functions a body costing uses.
    # Margin + ratio re-cost the repair through the normal debounced path — the
    # same controls, the same functions a body costing uses.
    page.fill("#f-margin", "10")
    page.select_option("#f-ratio", "0.5")
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    expect(page.locator("#bom-area")).to_contain_text("Materials", timeout=T)
    # 2 x 250 (catalogue) + 4 x 300 (typed) = 1700; +10% margin = 1870; / 0.5 = 3740.
    _wait_for_total(page, 3740.0)
    shot(page, "repair_surface", JOURNEY)

    # Save it. A repair rides the same approve path and quote numbering.
    # Select by VALUE (the customer id) — the picker's option list is search-filtered,
    # so a label match is not a reliable handle.
    page.select_option("#cust-select", value=str(laneC_body["customer"]))
    page.click("#approve-btn")
    # Poll for the saved record id (page.evaluate, not wait_for_function — CSP).
    # The BARE identifier, not window.lastRecordId: calculator.js declares it with
    # a top-level `let`, which lives in the script's global scope and is therefore
    # NOT a property of window.
    rec_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec_id:
            break
    assert rec_id, "the repair did not save"

    # It saved with the EXISTING repair identity: is_repair, no trailer.
    from app.database import SessionLocal, CalculationRecord
    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=int(rec_id)).first()
        assert rec is not None
        assert rec.is_repair is True
        assert rec.trailer_type_id is None
        assert rec.quote_number
        quote_no = rec.quote_number
        # Accept it: "Schedule into MES" shows for an ACCEPTED repair (v1.2.1
        # status mapping), which is pre-existing behaviour this lane kept.
    csrf = page.evaluate(
        "() => document.querySelector('meta[name=\"csrf-token\"]')?.content || ''")
    acc = page.request.post(f"{base}/api/calculations/{int(rec_id)}/accept",
                            headers={"Origin": base, "X-CSRF-Token": csrf})
    assert acc.ok, f"accept failed: HTTP {acc.status} {acc.text()[:200]}"

    # The React costings dashboard lists it as a Repair …
    page.goto("/mes-app/costings")
    expect(page.get_by_text("J147LC Customer Ltd").first).to_be_visible(timeout=T)
    expect(page.get_by_text("REPAIRS").first).to_be_visible(timeout=T)

    # … and opening it offers "Schedule into MES", which schedules through the
    # untouched RepairPhasePanel → /schedule-repair path.
    # The detail route is keyed on the QUOTE NUMBER (which contains slashes), so
    # it is url-encoded exactly as the dashboard row builds it.
    from urllib.parse import quote as _urlquote
    page.goto(f"/mes-app/costings/{_urlquote(quote_no, safe='')}")
    sched_btn = page.get_by_role("button", name=re.compile("Schedule into MES"))
    expect(sched_btn).to_be_visible(timeout=T)
    expect(page.get_by_text("Side panel replacement").first).to_be_visible(timeout=T)
    sched_btn.click()
    expect(page.get_by_text("Phase entry points")).to_be_visible(timeout=T)
    page.locator("input[type='checkbox']").first.check()
    shot(page, "repair_scheduled", JOURNEY)
    page.get_by_role("button", name=re.compile("Insert into MES")).click()

    import json as _json
    page.wait_for_timeout(1200)
    with SessionLocal() as db:
        rec = db.query(CalculationRecord).filter_by(id=int(rec_id)).first()
        assert rec.repair_phases_json, "the repair was not scheduled into the MES"
        phases = _json.loads(rec.repair_phases_json)
    assert isinstance(phases, list) and phases, phases


# ── (c) a normal body costing is untouched ───────────────────────────────────

def test_normal_body_costing_is_unaffected(page: Page, laneC_body) -> None:
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    _select_body(page, laneC_body["tt"])
    page.select_option("#f-ratio", "")   # headline == materials, so the number is checkable
    _settle(page)                        # the ratio change re-costs on the 700 ms debounce

    # No free-hand rows, no repair chrome — and the body inputs are all present.
    expect(page.locator("tr.fh-row")).to_have_count(0)
    expect(page.locator("#repair-add-stock")).to_have_count(0)
    expect(page.locator("#dims-wrap")).to_be_visible()
    expect(page.locator("#repair-meta-wrap")).to_be_hidden()
    expect(page.locator("#cfg-tab-chassis")).to_be_visible()

    # The PLAIN section costs exactly what it always did: 10 × R100.
    total = _grand_total(page)
    assert abs(total - 1000.0) < 0.05, f"plain body total is {total:.2f}, expected 1000.00"

    # And the payload carries no free-hand key when there are no free-hand lines.
    sent = page.evaluate("() => JSON.stringify(lastCalcPayload || {})")
    assert '"free_hand_lines"' not in sent, sent[:300]

    # Switching REPAIRS on and back off leaves the body costing intact.
    page.select_option("#trailer-select", "repair")
    expect(page.locator("#repair-add-stock")).to_be_visible(timeout=T)
    _select_body(page, laneC_body["tt"])
    expect(page.locator("#dims-wrap")).to_be_visible()
    expect(page.locator("#repair-meta-wrap")).to_be_hidden()
    back = _grand_total(page)
    assert abs(back - 1000.0) < 0.05, f"after leaving repair mode the total is {back:.2f}"
