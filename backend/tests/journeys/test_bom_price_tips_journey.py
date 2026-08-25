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
        row = BillOfMaterial(trailer_type_id=t.id, material_id=m.id,
                             formula_expression="1", waste_percentage=0.0,
                             bom_section="FRONT", sort_order=0)
        db.add(row)
        db.flush()
        ids = {"trailer": t.id, "row": row.id}
        db.commit()
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _open(page: Page, tt_id: int) -> None:
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(tt_id))
    expect(page.locator(".calc-grp-hdr").first).to_be_visible(timeout=T)
    expect(page.locator("#calc-status")).to_have_text("", timeout=T)
    page.wait_for_timeout(1200)


def _bubble_opacity(page: Page, bom_id: int) -> float:
    """Computed opacity of the tooltip bubble WHILE HOVERING the price cell.
    Reads the real pseudo-element, so it fails if the CSS gate regresses."""
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


def test_price_tips_are_off_by_default_and_opt_in(page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    # A first-time user has no stored preference at all.
    page.goto("/calculator")
    page.evaluate("() => localStorage.removeItem('bom_price_tips')")
    _open(page, ids["trailer"])

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


def test_the_choice_is_remembered_across_a_reload(page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    _open(page, ids["trailer"])
    page.locator("#bom-tips-toggle").check()
    page.wait_for_timeout(1000)

    _open(page, ids["trailer"])          # full page load
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
    _open(page, ids["trailer"])
    expect(page.locator("#bom-tips-toggle")).not_to_be_checked()
    # A BOM section header keeps its native hint while price tips are off.
    hdr = page.locator(".calc-grp-hdr[title]").first
    expect(hdr).to_be_visible(timeout=T)
    assert hdr.get_attribute("title"), "section header hints must not be suppressed"
    # And so does the Tips control itself, which is how it explains what it does.
    assert page.get_attribute("#bom-tips-lbl", "title"), "the Tips control lost its own hint"
    shot(page, "03-other-hints-intact", journey=JOURNEY)
