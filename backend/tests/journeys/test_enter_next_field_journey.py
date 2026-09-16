"""v1.55 — Enter moves to the next parameter on the costing calculator (journey).

Michael (16 Sep): "when the user has changed or typed in a parameter such as length,
width, height, margin or ratio and hits the enter button the app will auto move to the
next text box … similar to excel hitting enter moves the cursor to the next cell."

Ratified with him before building: the walk covers the BODY parameter block only, the
last box WRAPS back to the first, and Enter PRICES the costing there and then instead of
waiting out the 700 ms debounce.

The script, in a real browser: open a body in the calculator → Enter in the body-type
select hands over to Length → type → Enter → Width → … → Margin → Ratio → Enter wraps
back to Length. At each stop the old value is selected, so typing REPLACES it (the Excel
part of the ask, and the part a unit test cannot see). Then, with the page quiet, Enter
alone fires a fresh /api/calculate.

Marker rows J155EN* only — created and purged here. Base-aware (MES_BASE).
"""
from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, admin_session, shot  # noqa: E402

T = 20_000
JOURNEY = "enter_next_field"
MARK = "J155EN"

# Enter is pressed in the key, focus must land on the value. The last hop is the wrap.
WALK = [
    ("trailer-select", "f-length"),
    ("f-length", "f-width"),
    ("f-width", "f-height"),
    ("f-height", "f-margin"),
    ("f-margin", "f-ratio"),
    ("f-ratio", "f-length"),
]
# What is typed at each stop, and what the box must read afterwards if the value was
# selected on arrival (Excel: typing replaces, it does not append).
TYPED = {"f-length": "7.5", "f-width": "2.1", "f-height": "2.2", "f-margin": "12"}


def _base() -> str:
    return os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'J155EN%')"))
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE 'J155EN%'"))
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE 'J155EN%'"))
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE 'J155EN%'"))
    db.commit()


@pytest.fixture(scope="module")
def body():
    """A two-line body whose lines are priced off the parameters being typed."""
    from app.database import (SessionLocal, TrailerType, BillOfMaterial, BOMSection,
                              Material)
    with SessionLocal() as db:
        _purge(db)
        sec = BOMSection(name=f"{MARK} PANELS", sort_order=1, is_optional=False)
        tt = TrailerType(name=f"{MARK} BODY", is_active=True, default_length=6.0,
                         default_width=2.5, default_height=2.4)
        mats = [Material(name=f"{MARK} SKIN", unit_of_measure="m2", price_per_unit=100.0,
                         is_active=True),
                Material(name=f"{MARK} FRAME", unit_of_measure="m", price_per_unit=50.0,
                         is_active=True)]
        db.add_all([sec, tt, *mats])
        db.flush()
        for mat, formula, so in ((mats[0], "length*width", 1), (mats[1], "length*height", 2)):
            db.add(BillOfMaterial(trailer_type_id=tt.id, material_id=mat.id,
                                  formula_expression=formula, waste_percentage=0,
                                  bom_section=sec.name, bom_section_id=sec.id, sort_order=so))
        db.commit()
        ids = {"tt": tt.id}
    yield ids
    with SessionLocal() as db:
        _purge(db)


def _focused(page: Page) -> str:
    return page.evaluate("() => (document.activeElement && document.activeElement.id) || ''")


def test_enter_walks_the_body_parameters_and_prices_the_costing(page: Page, body) -> None:
    base = _base()
    admin_session(page, base=base)

    priced: list[str] = []

    def _watch(request) -> None:
        if request.method == "POST" and request.url.endswith("/api/calculate"):
            priced.append(request.url)

    page.on("request", _watch)

    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(body["tt"]))
    expect(page.locator("#bom-area tr.calc-grp-row[data-bom-id]")).to_have_count(2, timeout=T)
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    started_at = page.url

    # ── the walk ────────────────────────────────────────────────────────────
    page.focus("#trailer-select")
    for pressed_in, lands_on in WALK:
        assert _focused(page) == pressed_in, (
            f"expected to be standing in {pressed_in}, not {_focused(page) or '(nothing)'}")
        page.keyboard.press("Enter")
        assert _focused(page) == lands_on, (
            f"Enter in {pressed_in} landed on {_focused(page) or '(nothing)'}, expected {lands_on}")
        if lands_on in TYPED and pressed_in != "f-ratio":   # the wrap re-visits f-length
            page.keyboard.type(TYPED[lands_on])
            assert page.input_value(f"#{lands_on}") == TYPED[lands_on], (
                f"{lands_on} reads {page.input_value(f'#{lands_on}')!r} — the old value was not "
                f"selected on arrival, so typing appended instead of replacing it")

    assert page.url == started_at, "Enter must not submit or navigate the page"
    shot(page, "01-enter-wrapped-back-to-length", JOURNEY)

    # ── Enter prices the costing, without waiting out the debounce ───────────
    before = -1
    for _ in range(20):                       # let the typing's own recalcs drain
        if before == len(priced):
            break
        before = len(priced)
        page.wait_for_timeout(1200)
    else:
        pytest.fail("the calculator never stopped recalculating")

    page.keyboard.press("Enter")              # standing in f-length, nothing changed
    for _ in range(int(T / 100)):
        if len(priced) > before:
            break
        page.wait_for_timeout(100)
    assert len(priced) > before, (
        "Enter moved the cursor but never priced the costing — the figures would be stale")
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    total = page.locator("#grand-total").text_content() or ""
    assert total.strip() not in ("", "—"), f"the costing shows no total after Enter: {total!r}"
    shot(page, "02-priced-on-enter", JOURNEY)


def test_enter_leaves_the_rest_of_the_page_alone(page: Page, body) -> None:
    """Enter in a box outside the parameter block must not yank the cursor into it."""
    base = _base()
    admin_session(page, base=base)
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(body["tt"]))
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)

    page.focus("#cust-search")
    page.keyboard.press("Enter")
    assert _focused(page) == "cust-search", (
        f"Enter in the customer search moved focus to {_focused(page)!r} — only the body "
        f"parameters walk")
