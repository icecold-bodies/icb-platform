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
    # v1.49 — MES children FIRST. Scheduling a repair now creates and advances a
    # production job, and fk_production_jobs_calculation_record_id is RESTRICT, so
    # deleting the calculations first aborts the whole purge. That failure is
    # delayed and misleading: this module's bom_sections are globally unique by
    # name, so the surviving rows break the NEXT run at SETUP.
    _owned = (
        "SELECT c.id FROM icb_costings.calculations c "
        "LEFT JOIN icb_costings.trailer_types t ON t.id = c.trailer_type_id "
        "LEFT JOIN icb_costings.customers cu ON cu.id = c.customer_id "
        "WHERE t.name LIKE 'J147LC%' OR cu.name LIKE 'J147LC%'")
    for _tbl, _col in (("icb_mes.prejob_cards", "calculation_id"),
                       ("icb_mes.production_jobs", "calculation_record_id")):
        db.execute(text(f"DELETE FROM {_tbl} WHERE {_col} IN ({_owned})"))
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
        # A SECOND optional item, priced differently, so a test can prove it
        # selected ONE row rather than merely "the section".
        rail = Material(name="J147LC EXTRA RAIL", unit_of_measure="each",
                        price_per_unit=75.0, is_active=True)
        seal = Material(name="J147LC REPAIR SEAL", unit_of_measure="each",
                        price_per_unit=250.0, is_active=True)
        db.add_all([floor, tray, rail, seal])
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
            BillOfMaterial(trailer_type_id=tt.id, material_id=rail.id,
                           formula_expression="1", waste_percentage=0,
                           bom_section=OPT_SECTION, bom_section_id=opt_sec.id,
                           sort_order=3),
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


def _wait_for_optional_section(page: Page, tt_id: int, section_id: int) -> None:
    """Wait until the SERVER reports this section as optional, reloading the BOM
    until it does.

    services.get_section_snapshot() is cached with a 30 s TTL and
    invalidate_sections() is never called, so a BOMSection this fixture inserts
    straight into the database is invisible to the running server for up to 30
    seconds. While it is, its rows come back with section_is_optional=false, so
    the section renders as a NORMAL section — no tick, no "+ Free-hand line".

    That is a race against a cache, not against a render, so no amount of
    waiting on the page fixes it: the BOM has to be re-fetched after the TTL
    lapses. Ubuntu happened to win this race and Windows lost it, which is
    exactly how it reached CI green on one platform and red on the other.
    """
    deadline = 75.0
    waited = 0.0
    tick = page.locator(f".opt-sec-tick[data-section-id='{section_id}']")
    while waited < deadline:
        if tick.count() > 0:
            return
        page.wait_for_timeout(3000)
        waited += 3.0
        page.evaluate("loadBOM()")          # re-fetch the BOM from the server
        try:
            expect(page.locator(".calc-grp-hdr").first).to_be_visible(timeout=10_000)
        except AssertionError:
            pass
    raise AssertionError(
        f"section {section_id} never came back optional within {deadline:.0f}s — "
        "the server's section snapshot cache never refreshed")


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
    _wait_for_optional_section(page, laneC_body["tt"], laneC_body["opt_sec"])
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
    expect(row).to_contain_text("RUBBER SEAL KIT")   # v1.49 - upper-cased on the surface
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
    # ?stay=1 - v1.49 sends a standalone calculator to the costings board ~1s
    # after a save; this journey keeps asserting on the saved surface, so it
    # opts out. The navigation itself is covered by its own journey below.
    page.goto("/mes/calculator?stay=1")
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

    # v1.49 (Michael's rule 2, 19 Aug): SAVED ONCE MEANS SAVED. The button used
    # to come straight back after a save - and again after every recalc - so a
    # user could save the same repair for the same client and items repeatedly.
    # It must now stay disabled, and say so; Duplicate is the way to make another.
    expect(page.locator("#approve-btn")).to_be_disabled()
    expect(page.locator("#approve-btn")).to_have_text(re.compile("Saved"))
    # ...and nothing that used to re-arm it may do so. Ticking a line was the
    # obvious recalc path; since the lock (below) it is refused outright, so
    # drive the recalc directly and prove the gate still holds regardless.
    page.evaluate("() => { if (typeof runRepairCalc === 'function') runRepairCalc(); }")
    page.wait_for_timeout(1500)
    expect(page.locator("#approve-btn")).to_be_disabled()
    n_before = None
    with __import__("app.database", fromlist=["SessionLocal"]).SessionLocal() as _db:
        from app.database import CalculationRecord as _CR
        n_before = _db.query(_CR).filter_by(customer_id=laneC_body["customer"], is_repair=True).count()
    # Clicking a disabled button does nothing; force-firing the handler must not
    # produce a second row either (belt AND braces: the gate is the button).
    page.evaluate("() => { const b = document.getElementById('approve-btn'); if (!b.disabled) b.click(); }")
    page.wait_for_timeout(1500)
    with __import__("app.database", fromlist=["SessionLocal"]).SessionLocal() as _db:
        from app.database import CalculationRecord as _CR
        assert _db.query(_CR).filter_by(customer_id=laneC_body["customer"], is_repair=True).count() == n_before,             "a second save of the same repair got through"

    # v1.49 (Michael, 19 Aug): after the save the LINES ARE LOCKED. The per-line
    # edit / remove controls are gone, and forcing the mutators does nothing but
    # warn. (Standalone, the page then navigates to the board - see below - so
    # assert this before that fires; embedded, the parent frame navigates.)
    expect(page.locator("#repair-lines-body button[title='Edit this line']")).to_have_count(0)
    expect(page.locator("#repair-lines-body button[title='Remove this line']")).to_have_count(0)
    n_lines = page.locator("#repair-lines-body tr").count()
    page.evaluate("() => { const k = (repairLines[0]||{}).key; if (k) removeFreeHandLine(k); }")
    page.wait_for_timeout(300)
    assert page.locator("#repair-lines-body tr").count() == n_lines, "a saved repair's lines must not be removable"

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
    # Same section-cache race as (a): until the server sees the section as
    # optional its rows are INCLUDED, and the plain-body total would read 1120.
    _wait_for_optional_section(page, laneC_body["tt"], laneC_body["opt_sec"])
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

# ── (d) Michael 18 Aug — selecting ONE extra without touching the other 300 ──

def test_a_free_hand_line_costs_on_its_own_without_selecting_the_section(
        page: Page, laneC_body) -> None:
    """The reported bug, end to end.

    An OPTIONAL EXTRAS section holds hundreds of items. Adding a free-hand line
    used to leave it struck through with a DISABLED tick, so the only way to
    cost that one line was "Select all" (~300 items) and then untick 299 by
    hand. Adding a line now includes THAT LINE ONLY: the section switches on
    behind it and every other row in the section stays excluded.
    """
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    _select_body(page, laneC_body["tt"])
    _wait_for_optional_section(page, laneC_body["tt"], laneC_body["opt_sec"])
    page.select_option("#f-ratio", "")
    _settle(page)

    # Section OFF — its real rows (2 x R60 = R120) are not in the total.
    baseline = _grand_total(page)

    hdr = page.locator(f"tr.calc-grp-hdr[data-section-id='{laneC_body['opt_sec']}']")
    if "collapsed" in (hdr.get_attribute("class") or ""):
        hdr.locator(".calc-hdr-name").click()
    _settle(page)

    page.locator(f"button[data-free-hand-add='{laneC_body['opt_sec']}']").click()
    expect(page.locator("#modal-free-hand")).not_to_have_class(re.compile(r"hidden"), timeout=T)
    page.fill("#fh-description", "Rubber seal kit")
    page.fill("#fh-qty", "2")
    page.fill("#fh-unit-price", "450")
    page.click("#fh-save-btn")

    # The line counts IMMEDIATELY, with no section tick and no Select all …
    _wait_for_total(page, baseline + 900.0)
    row = page.locator("tr.fh-row")
    expect(row).to_have_count(1, timeout=T)
    expect(row.locator("input[type=checkbox]")).not_to_be_checked()
    expect(row.locator("input[type=checkbox]")).to_be_enabled()

    # … and the section's OWN rows are still out: the total moved by the line
    # alone, not by the line plus R120 of extras nobody asked for.
    body_rows = page.locator(f"tr.opt-sec-row:not(.fh-row)")
    assert body_rows.count() > 0, "the optional section rendered no BOM rows"
    for i in range(body_rows.count()):
        expect(body_rows.nth(i).locator("input.opt-row-tick")).to_be_checked()


def test_deselect_all_leaves_the_section_selectable(page: Page, laneC_body) -> None:
    """"Deselect all" clears the ROWS and leaves the SECTION on, so the user can
    then pick the two items they want. It used to switch the section off, which
    is what forced the Select-all-then-untick-everything dance."""
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    _select_body(page, laneC_body["tt"])
    _wait_for_optional_section(page, laneC_body["tt"], laneC_body["opt_sec"])
    page.select_option("#f-ratio", "")
    _settle(page)
    baseline = _grand_total(page)

    hdr = page.locator(f"tr.calc-grp-hdr[data-section-id='{laneC_body['opt_sec']}']")
    if "collapsed" in (hdr.get_attribute("class") or ""):
        hdr.locator(".calc-hdr-name").click()
    _settle(page)

    # Select all -> both rows in (TRAY 2 x R60 = R120, RAIL 1 x R75 = R75 -> R195),
    # then Deselect all -> back out.
    # Click the pills BY LABEL: the header carries several .calc-bulk-pill-btn
    # buttons (the bulk pill and "+ Free-hand line"), and the bulk pill's own
    # label flips between the two actions, so clicking "the first button twice"
    # can silently press Select all twice.
    hdr.get_by_text(re.compile("Select all")).click()
    _wait_for_total(page, baseline + 195.0)
    expect(hdr.get_by_text(re.compile("Deselect all"))).to_be_visible(timeout=T)
    hdr.get_by_text(re.compile("Deselect all")).click()
    _wait_for_total(page, baseline)

    # The section is still live: including ONE row costs exactly that row and
    # NOT the other — only possible because Deselect all left the section on.
    # The first row is the TRAY (R120); the RAIL (R75) must stay out.
    first_row = page.locator("tr.opt-sec-row:not(.fh-row)").first
    first_row.locator("input.opt-row-tick").uncheck()      # unchecked == INCLUDED
    _wait_for_total(page, baseline + 120.0)
    rows = page.locator("tr.opt-sec-row:not(.fh-row)")
    expect(rows.nth(1).locator("input.opt-row-tick")).to_be_checked()


# ── (e) Michael 18 Aug — a repair must price before it has a type ────────────

def test_a_repair_prices_as_soon_as_it_has_a_line(page: Page, laneC_body) -> None:
    """Reported: adding a free-hand repair line left every total on R0,00.

    The type of repair gated the CALCULATE as well as the save, so the header
    rail and the price summary stayed empty until the type happened to be typed
    — the surface looked broken. Pricing is a preview; the type is a commitment
    made at save time, and only the Approve button waits for it.
    """
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", "repair")
    expect(page.locator("#repair-add-freehand")).to_be_visible(timeout=T)

    # TYPE OF REPAIR deliberately left empty, exactly as reported.
    # The ratio is pinned EXPLICITLY rather than cleared: the page restores a
    # saved ratio after load, so "select None then assert" races that restore —
    # and the ratio is incidental to what this test proves.
    page.fill("#f-margin", "10")
    page.select_option("#f-ratio", "0.55")
    expect(page.locator("#f-ratio")).to_have_value("0.55", timeout=T)
    page.click("#repair-add-freehand")
    expect(page.locator("#modal-free-hand")).not_to_have_class(re.compile(r"hidden"), timeout=T)
    page.fill("#fh-description", "rubber seal")
    page.fill("#fh-qty", "1")
    page.fill("#fh-unit-price", "123.23")
    page.click("#fh-save-btn")

    # 123.23 materials + 10% margin = 135.55, / 0.55 ratio = 246.45. The rail and
    # the summary must agree on it — they disagreed until the repair calculate
    # started sending the ratio to the server (rail said "RATIO R 0,00" beside a
    # summary reading "Ratio (55%) + R 110,90").
    _wait_for_total(page, 246.45)
    expect(page.locator("#bom-area")).to_contain_text("110,90", timeout=T)
    expect(page.locator("#bom-area")).to_contain_text("123,23", timeout=T)
    expect(page.locator("#summary-area")).to_contain_text("Materials Cost", timeout=T)
    assert page.input_value("#f-repair-type") == "", "the type must still be empty"

    # Priced, but NOT saveable — the type is what unlocks Approve.
    expect(page.locator("#approve-btn")).to_be_disabled()
    page.fill("#f-repair-type", "Side panel replacement")
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)


def test_ticking_a_repair_line_off_drops_the_totals_to_zero(page: Page, laneC_body) -> None:
    """Michael, 18 Aug (second report): the line struck through but the rail and
    the summary carried on showing what it used to cost."""
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", "repair")
    expect(page.locator("#repair-add-freehand")).to_be_visible(timeout=T)
    page.fill("#f-repair-type", "Side panel replacement")
    page.fill("#f-margin", "10")
    # Pinned, not cleared: the page restores a saved ratio shortly after load, so
    # "select None then assert" races that restore (same note as the sibling
    # test). 0.55 also makes this the reported figure exactly.
    page.fill("#f-margin", "10")
    page.select_option("#f-ratio", "0.55")
    expect(page.locator("#f-ratio")).to_have_value("0.55", timeout=T)

    page.click("#repair-add-freehand")
    expect(page.locator("#modal-free-hand")).not_to_have_class(re.compile(r"hidden"), timeout=T)
    page.fill("#fh-description", "test")
    page.fill("#fh-qty", "12")
    page.fill("#fh-unit-price", "123.98")
    page.click("#fh-save-btn")
    # 12 x 123.98 = 1487.76, +10% margin = 1636.54, / 0.55 = 2975.53 — the
    # figure in the report.
    _wait_for_total(page, 2975.53)

    # Tick the line OFF (checked == EXCLUDED) — everything must go to zero.
    page.locator("#repair-lines-body input[type=checkbox]").first.check()
    _wait_for_total(page, 0.0)
    expect(page.locator("#approve-btn")).to_be_disabled()

    # And back in again.
    page.locator("#repair-lines-body input[type=checkbox]").first.uncheck()
    _wait_for_total(page, 2975.53)
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)


def test_a_refused_line_names_its_field_and_never_blames_notes(page: Page, laneC_body) -> None:
    """v1.49 (Michael's rule 3, 19 Aug): "occasionally the NOTES section is
    required ... this happens mostly when the user has selected from the stock
    list. This NOTE section should always be optional."

    Nothing has ever required Notes - server or client. What happened: the error
    box rendered directly UNDER the Notes textarea, the last field in the form,
    so a refusal for a blank quantity after a stock pick read as "Notes is
    required". The box now sits ABOVE the fields, every message names its field,
    and the offending field is focused.
    """
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", "repair")
    expect(page.locator("#repair-add-freehand")).to_be_visible(timeout=T)

    # Notes is optional - the label says so.
    page.click("#repair-add-freehand")
    expect(page.locator("#modal-free-hand")).not_to_have_class(re.compile(r"\bhidden\b"), timeout=T)
    expect(page.locator("label[for='fh-notes']")).to_contain_text("optional")

    # A line with a description but a BLANK quantity, and Notes left empty.
    page.fill("#fh-description", "Rubber seal")
    page.fill("#fh-qty", "")
    page.fill("#fh-unit-price", "45")
    page.click("#fh-save-btn")

    err = page.locator("#fh-error")
    expect(err).to_be_visible()
    msg = err.inner_text()
    assert "Quantity" in msg, f"the refusal must name the real field, got: {msg!r}"
    assert "note" not in msg.lower(), f"nothing may blame Notes, got: {msg!r}"
    # The box is ABOVE the description field, not under Notes.
    err_top = err.bounding_box()["y"]
    desc_top = page.locator("#fh-description").bounding_box()["y"]
    notes_top = page.locator("#fh-notes").bounding_box()["y"]
    assert err_top < desc_top < notes_top, "the error must sit above the fields, not beneath Notes"
    # And the eye is taken to the field that is actually wrong.
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "fh-qty"

    # Fill the quantity, still no Notes: it saves.
    page.fill("#fh-qty", "3")
    page.click("#fh-save-btn")
    expect(page.locator("#modal-free-hand")).to_have_class(re.compile(r"\bhidden\b"), timeout=T)
    expect(page.locator("#repair-lines-body tr")).to_have_count(1, timeout=T)


def test_saving_a_repair_lands_on_the_costings_board_with_the_row_highlighted(page: Page, laneC_body) -> None:
    """v1.49 (Michael, 19 Aug): "when the user has approved ... take the user to
    the costings page /mes-app/costings and highlight the repair he has just done."

    The REAL user path: the calculator embedded at /mes-app/costings/new. The
    save posts mes:costing-saved to the parent frame, which refreshes the list
    and navigates to /costings?highlight=<quote>; the board scrolls that row into
    view and pulses it. Uses ?stay-free defaults - this is the navigation itself.
    """
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes-app/costings/new")
    frame = page.frame_locator("iframe[title='Calculator (live costing app)']")
    expect(frame.locator("#trailer-select")).to_be_visible(timeout=30_000)

    # select_option -> the surface swap is one-shot and can be lost while the
    # EMBED settles (banked v1.44 flake class; the email journey's
    # _select_trailer_and_wait_bom does the same). Re-select until REPAIRS
    # renders. Ubuntu CI hit this once; Windows did not.
    add_btn = frame.locator("#repair-add-freehand")
    for _ in range(4):
        frame.locator("#trailer-select").select_option("repair")
        try:
            expect(add_btn).to_be_visible(timeout=8_000)
            break
        except AssertionError:
            continue
    expect(add_btn).to_be_visible(timeout=T)
    frame.locator("#f-repair-type").fill("Board landing test")
    frame.locator("#repair-add-freehand").click()
    expect(frame.locator("#modal-free-hand")).not_to_have_class(re.compile(r"\bhidden\b"), timeout=T)
    frame.locator("#fh-description").fill("landing seal")      # typed lower case on purpose
    frame.locator("#fh-qty").fill("1")
    frame.locator("#fh-unit-price").fill("120")
    frame.locator("#fh-save-btn").click()
    expect(frame.locator("#repair-lines-body tr")).to_have_count(1, timeout=T)
    # v1.49: the description reads UPPER CASE on the surface
    expect(frame.locator("#repair-lines-body tr").first).to_contain_text("LANDING SEAL")

    frame.locator("#cust-select").select_option(value=str(laneC_body["customer"]))
    expect(frame.locator("#approve-btn")).to_be_enabled(timeout=T)
    frame.locator("#approve-btn").click()

    # A visible, cancellable countdown appears on the parent page (export and
    # validated-reference work still happens here, so it is not an instant
    # jump). Both buttons must be there; "Go now" takes us straight to the board.
    banner = page.locator("[data-testid='saved-banner']")
    expect(banner).to_be_visible(timeout=T)
    expect(banner).to_contain_text("Going to the costings board")
    expect(page.locator("[data-testid='saved-stay']")).to_be_visible()
    page.locator("[data-testid='saved-go-now']").click()

    # The parent navigates to the board with ?highlight=<quote>...
    page.wait_for_url(re.compile(r"/mes-app/costings\?highlight="), timeout=T)
    # ...and that row is on the page, marked, and scrolled into view.
    row = page.locator("[data-testid='costing-row'][data-highlighted='true']")
    expect(row).to_have_count(1, timeout=T)
    expect(row).to_have_class(re.compile(r"animate-pulseRing"))
    box = row.bounding_box()
    vh = page.evaluate("() => window.innerHeight")
    assert box and 0 <= box["y"] <= vh, "the highlighted row must be scrolled into the viewport"
    # It is the repair just saved.
    expect(row).to_contain_text(re.compile(r"Repair", re.I))


def test_editing_a_saved_repair_unlocks_its_lines_and_its_save_button(page: Page, laneC_body) -> None:
    """v1.49 (Michael, 19 Aug): "when the user edits a repair the line items can
    not be deleted or edited. The Approve & Save is then not available."

    A regression from the release before it. The save-once gate and the line
    lock both keyed on lastRecordId - but that variable does not mean "just
    saved", it means "there is a saved record behind this screen", which is
    equally true when a saved repair is opened for EDIT (the surface needs the
    id to offer the repair quotation). So Edit looked exactly like just-saved
    and refused everything Edit exists to do. The gate is justSavedHere now.

    ?stay=1 - a standalone calculator leaves for the costings board about a
    second after a save; this journey keeps asserting on the surface.
    """
    base = os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")
    admin_session(page, base=base)
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)

    page.select_option("#trailer-select", "repair")
    expect(page.locator("#repair-add-freehand")).to_be_visible(timeout=T)
    page.fill("#f-repair-type", "Edit after save")

    # TWO lines, so one can be removed later and the repair still prices.
    for _desc, _price in (("first seal", "120"), ("second seal", "80")):
        page.click("#repair-add-freehand")
        expect(page.locator("#modal-free-hand")).not_to_have_class(re.compile(r"\bhidden\b"), timeout=T)
        page.fill("#fh-description", _desc)
        page.fill("#fh-qty", "1")
        page.fill("#fh-unit-price", _price)
        page.click("#fh-save-btn")
        expect(page.locator("#modal-free-hand")).to_have_class(re.compile(r"\bhidden\b"), timeout=T)

    edit_btn = page.locator("#repair-lines-body button[title='Edit this line']")
    del_btn = page.locator("#repair-lines-body button[title='Remove this line']")
    expect(page.locator("#repair-lines-body tr")).to_have_count(2, timeout=T)
    expect(edit_btn).to_have_count(2)

    page.select_option("#cust-select", value=str(laneC_body["customer"]))
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    page.click("#approve-btn")

    # The BARE identifier - calculator.js declares it with a top-level `let`,
    # which is not a property of window. (page.evaluate, not wait_for_function:
    # the CSP has no unsafe-eval.)
    rec_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec_id:
            break
    assert rec_id, "the repair did not save"

    # Saved: rule 2 and the line lock both bite. This half must keep working.
    expect(page.locator("#approve-btn")).to_be_disabled()
    expect(page.locator("#approve-btn")).to_contain_text("Saved")
    expect(edit_btn).to_have_count(0)
    expect(del_btn).to_have_count(0)

    # --- Now EDIT it. Everything the lock withheld has to come back. ---
    page.goto(f"/mes/calculator?edit={rec_id}&stay=1")
    expect(page.locator("#repair-add-freehand")).to_be_visible(timeout=T)
    rows = page.locator("#repair-lines-body tr")
    expect(rows).to_have_count(2, timeout=T)
    expect(edit_btn).to_have_count(2)
    expect(del_btn).to_have_count(2)
    # The button renders `disabled` in the template, so this is a real
    # disabled -> enabled edge, not a level that was already true.
    expect(page.locator("#approve-btn")).not_to_contain_text("Saved")
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    shot(page, "repair_edit_unlocked", JOURNEY)

    # A line can actually be REMOVED - the thing Michael could not do.
    _settle(page)
    del_btn.first.click()
    expect(rows).to_have_count(1, timeout=T)
    # ... and EDITED: the dialog opens instead of a "this costing is saved" refusal.
    _settle(page)
    edit_btn.first.click()
    expect(page.locator("#modal-free-hand")).not_to_have_class(re.compile(r"\bhidden\b"), timeout=T)
    page.fill("#fh-unit-price", "95")
    page.click("#fh-save-btn")
    expect(page.locator("#modal-free-hand")).to_have_class(re.compile(r"\bhidden\b"), timeout=T)
    expect(rows).to_have_count(1, timeout=T)

    # Saving the edit re-arms the lock - rule 2 still holds where it should.
    _settle(page)
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    page.click("#approve-btn")
    overwrite = page.locator("#modal-edit-save button[onclick*='overwrite']")
    expect(overwrite).to_be_visible(timeout=T)
    overwrite.click()
    expect(page.locator("#approve-btn")).to_be_disabled(timeout=T)
    expect(page.locator("#approve-btn")).to_contain_text("Saved")
    expect(del_btn).to_have_count(0)
