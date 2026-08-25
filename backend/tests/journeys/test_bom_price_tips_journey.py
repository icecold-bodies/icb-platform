"""v1.51 — BOM price tips are OPT-IN (Michael, 25 Aug).

The coloured price-cell bubbles (quote-only override / recently updated /
outdated / bulk-updated) used to fire on every hover anywhere in the Bill of
Materials. They are now OFF by default, behind a "Tips" checkbox in the BOM
header, and the choice is remembered.

Two mechanisms have to move together, which is what this journey pins:
  * the CSS bubble, gated on body[data-tips="on"] — asserted through the
    COMPUTED opacity of the ::after pseudo-element while hovering, not through
    the class name, so the test fails if the gate stops working;
  * the NATIVE browser tooltip, a `title` carrying the same text, which CSS
    cannot suppress — so the attribute must be absent while tips are off. This
    is the half that a CSS-only implementation silently gets wrong.

Marker J151T; purge at setup AND teardown; admin_session gets base=live_server.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "bom_price_tips"
MARK = "J151T"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("""
        DELETE FROM icb_costings.bill_of_materials
         WHERE trailer_type_id IN (SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)
    """), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE material_code = :c"), {"c": MARK})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    """A body with one RECENTLY-PRICED line — that is what earns a price bubble
    (`price-recent-cell`) without needing a quote-level override."""
    from datetime import datetime, timezone
    from app.database import BillOfMaterial, Material, SessionLocal, TrailerType
    with SessionLocal() as db:
        _purge(db)
        t = TrailerType(name=f"{MARK} TIPS BODY", is_active=True,
                        default_length=6.0, default_width=2.4, default_height=2.4)
        db.add(t)
        db.flush()
        m = Material(name=f"{MARK} RECENTLY PRICED PLY", unit_of_measure="each",
                     price_per_unit=500.0, material_code=MARK, is_active=True,
                     last_updated=datetime.now(timezone.utc))
        db.add(m)
        db.flush()
        # NOT formula "1": _showFormulaTooltip returns early on a trivial formula
        # (`if (!formula || formula === '1') return;`), so a "1" row can never
        # open the panel and the test would pass for the wrong reason.
        row = BillOfMaterial(trailer_type_id=t.id, material_id=m.id,
                             formula_expression="length*2", waste_percentage=0.0,
                             bom_section="FRONT", sort_order=0)
        db.add(row)
        db.flush()
        ids = {"trailer": t.id, "row": row.id}
        db.commit()
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _open(page: Page, tt_id: int, row_id: int | None = None) -> None:
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(tt_id))
    expect(page.locator(".calc-grp-hdr").first).to_be_visible(timeout=T)
    expect(page.locator("#calc-status")).to_have_text("", timeout=T)
    page.wait_for_timeout(1200)
    if row_id is not None:
        _ensure_visible(page, row_id)


def _ensure_visible(page: Page, bom_id: int) -> None:
    """BOM groups render COLLAPSED, so a price cell is ATTACHED but has zero
    height — Playwright resolves the locator and then times out waiting for it to
    be visible. Expand until the row really is on screen, which is also the state
    a user hovering a price is in. (This is what turned the first CI run red.)"""
    probe = ("(id) => { const r = document.querySelector('tr[data-bom-id=\"' + id + '\"]');"
             "          return !!r && r.getBoundingClientRect().height > 0; }")
    for _ in range(8):
        if page.evaluate(probe, str(bom_id)):
            return
        page.locator("#bom-collapse-lbl").click()
        page.wait_for_timeout(1200)
    raise AssertionError(f"BOM row {bom_id} never became visible - cannot hover it")


def _bubble_opacity(page: Page, bom_id: int) -> float:
    """Computed opacity of the tooltip bubble WHILE HOVERING the price cell.
    Reads the real pseudo-element, so it fails if the CSS gate regresses."""
    _ensure_visible(page, bom_id)
    cell = page.locator(f"tr[data-bom-id='{bom_id}'] td.price-recent-cell")
    cell.hover()
    page.wait_for_timeout(400)   # the bubble transitions over .15s
    return float(page.evaluate(
        """(id) => {
             const el = document.querySelector(`tr[data-bom-id="${id}"] td.price-recent-cell`);
             return getComputedStyle(el, '::after').opacity;
           }""", str(bom_id)))


def _title_attr(page: Page, bom_id: int):
    return page.get_attribute(f"tr[data-bom-id='{bom_id}'] td.price-recent-cell", "title")


def _formula_panel(page: Page, bom_id: int) -> str:
    """Computed display of the hover FORMULA panel while over a BOM row.

    This is the BIG one — the panel showing the substituted formula and the
    resolved {NAME} variables. It has its own page-level state that used to
    default to ON and could only be changed by CLICKING a row, which is why it
    fired on every hover with no visible way to stop it."""
    _ensure_visible(page, bom_id)
    # Move OFF the row first. The panel opens on a `mouseover` EVENT, so hovering
    # a row the pointer is already sitting on fires nothing and the panel never
    # appears — a false negative that has nothing to do with the Tips state.
    page.mouse.move(4, 4)
    page.wait_for_timeout(150)
    page.locator(f"tr[data-bom-id='{bom_id}']").hover()
    page.wait_for_timeout(500)
    return page.evaluate(
        "() => { const t = document.getElementById('formula-tooltip');"
        "        return t ? getComputedStyle(t).display : 'absent'; }")


def test_price_tips_are_off_by_default_and_opt_in(page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    # A first-time user has no stored preference at all.
    page.goto("/calculator")
    page.evaluate("() => localStorage.removeItem('bom_price_tips')")
    _open(page, ids["trailer"], ids["row"])

    toggle = page.locator("#bom-tips-toggle")
    expect(page.locator("#bom-tips-lbl")).to_be_visible(timeout=T)
    expect(toggle).not_to_be_checked()
    expect(page.locator("body")).not_to_have_attribute("data-tips", "on")

    # OFF: the cell still carries its colour class and its bubble TEXT, but the
    # bubble does not paint and the native tooltip attribute is not there.
    cell = page.locator(f"tr[data-bom-id='{ids['row']}'] td.price-recent-cell")
    expect(cell).to_have_count(1)
    assert cell.get_attribute("data-tooltip"), "the bubble's text source must survive"
    assert _title_attr(page, ids["row"]) is None, \
        "native browser tooltip would still pop — title must not be emitted while tips are off"
    assert _bubble_opacity(page, ids["row"]) == 0.0, "bubble painted while tips are off"
    shot(page, "01-tips-off", journey=JOURNEY)

    # ON: both mechanisms come back together.
    rows_before = page.locator("tr[data-bom-id]").count()
    hdrs_before = page.locator(".calc-grp-hdr").count()
    toggle.check()
    page.wait_for_timeout(1200)
    expect(page.locator("body")).to_have_attribute("data-tips", "on")
    assert _title_attr(page, ids["row"]), "title must return when tips are on"
    assert _bubble_opacity(page, ids["row"]) == 1.0, "bubble did not paint when tips are on"

    # REGRESSION GUARD: toggling must not touch the costed table. The first cut
    # re-rendered on toggle, and refreshBomDisplay() paints the PRE-calc parts
    # view — so ticking Tips replaced the calculated BOM with the uncalculated
    # one (209 price cells -> 0, measured on FREEZER LARGE). The tips state is
    # now patched onto the existing DOM instead.
    assert page.locator("tr[data-bom-id]").count() == rows_before, \
        "the Tips toggle re-rendered and lost BOM rows"
    assert page.locator(".calc-grp-hdr").count() == hdrs_before, \
        "the Tips toggle replaced the costed table with the pre-calc view"
    shot(page, "02-tips-on", journey=JOURNEY)

    # And OFF again — the toggle is not one-way.
    toggle.uncheck()
    page.wait_for_timeout(1200)
    assert _title_attr(page, ids["row"]) is None
    assert _bubble_opacity(page, ids["row"]) == 0.0


def test_the_formula_panel_follows_the_same_switch(page: Page, live_server: str, staged) -> None:
    """The hover FORMULA panel is the loud one. It shares the page-level tooltip
    state, which defaulted to ON and was only reachable by clicking a row — so
    the Tips checkbox owns that state now, and owns it in both directions."""
    ids = staged
    admin_session(page, base=live_server)
    page.goto("/calculator")
    page.evaluate("() => localStorage.removeItem('bom_price_tips')")
    _open(page, ids["trailer"], ids["row"])

    assert _formula_panel(page, ids["row"]) in ("none", "absent"), \
        "the formula panel showed on hover with Tips off"

    # A stray click on a row must not bring it back through the invisible cycle.
    page.locator(f"tr[data-bom-id='{ids['row']}']").click()
    page.wait_for_timeout(600)
    assert _formula_panel(page, ids["row"]) in ("none", "absent"), \
        "a row click resurrected the formula panel while Tips was off"

    page.locator("#bom-tips-toggle").check()
    page.wait_for_timeout(1200)
    assert _formula_panel(page, ids["row"]) == "block", \
        "the formula panel did not come back when Tips was switched on"
    shot(page, "04-formula-panel-on", journey=JOURNEY)

    page.locator("#bom-tips-toggle").uncheck()
    page.wait_for_timeout(1000)
    assert _formula_panel(page, ids["row"]) in ("none", "absent")


def test_the_choice_is_remembered_across_a_reload(page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    _open(page, ids["trailer"], ids["row"])
    page.locator("#bom-tips-toggle").check()
    page.wait_for_timeout(1000)

    _open(page, ids["trailer"], ids["row"])          # full page load
    expect(page.locator("#bom-tips-toggle")).to_be_checked(timeout=T)
    expect(page.locator("body")).to_have_attribute("data-tips", "on")
    assert _title_attr(page, ids["row"]), "the remembered ON state must restore both mechanisms"

    # Leave the shared browser context on the default so a later journey in the
    # same context starts from the shipped behaviour.
    page.locator("#bom-tips-toggle").uncheck()
    page.wait_for_timeout(800)


def test_other_tooltips_are_untouched(page: Page, live_server: str, staged) -> None:
    """Scope guard: only the PRICE bubbles are opt-in. Control affordances keep
    their native hints whatever the Tips state is."""
    ids = staged
    admin_session(page, base=live_server)
    _open(page, ids["trailer"], ids["row"])
    expect(page.locator("#bom-tips-toggle")).not_to_be_checked()
    # A BOM section header keeps its native hint while price tips are off.
    hdr = page.locator(".calc-grp-hdr[title]").first
    expect(hdr).to_be_visible(timeout=T)
    assert hdr.get_attribute("title"), "section header hints must not be suppressed"
    # And so does the Tips control itself, which is how it explains what it does.
    assert page.get_attribute("#bom-tips-lbl", "title"), "the Tips control lost its own hint"
    shot(page, "03-other-hints-intact", journey=JOURNEY)
