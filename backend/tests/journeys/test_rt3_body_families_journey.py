"""RT3 — body families in colour, in a real browser, on the light MES skin (RT3_RULING_1 + 1a).

  1. The MES calculator's BODY TYPE box lists one optgroup per family in the families' order; each option is in
     its family's ink; the closed box carries the selected body's family bar and names the family in its tooltip
     and in the top-bar chip; Enter in the box still hands over to Length (the Enter chain).
  2. An admin changes a family's colour on Admin -> Quote templates (MES skin): a colour too light for the MES
     screens WARNS and Cancel saves nothing; an approved one saves; the new colour then shows on the calculator
     and on the MES costings list's family chip (the body name stays the readable text; the row is not coloured).

Marker rows RT3J* only — created and purged here. Base-aware (MES_BASE).
"""
from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, SCREENSHOT_ROOT, admin_session, shot  # noqa: E402

T = 20_000
JOURNEY = "rt3_body_families"
MARK = "RT3J"
QUOTE = "RT3J-0001"


def _base() -> str:
    return os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_costings.calculations WHERE quote_number = :q"), {"q": QUOTE})
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'RT3J%')"))
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE 'RT3J%'"))
    db.execute(text("DELETE FROM icb_costings.trailer_groups WHERE name LIKE 'RT3J%'"))
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE 'RT3J%'"))
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE 'RT3J%'"))
    db.commit()


@pytest.fixture()
def fams():
    """Two families ordered after every real one, a priced body in each, and a saved costing on the first."""
    from app.database import (BillOfMaterial, BOMSection, CalculationRecord, Material, SessionLocal,
                              TrailerGroup, TrailerType)
    with SessionLocal() as db:
        _purge(db)
        ga = TrailerGroup(name=f"{MARK} ALPHA", colour="#E03131", sort_order=9101)
        gb = TrailerGroup(name=f"{MARK} BETA", colour="#168ED9", sort_order=9102)
        sec = BOMSection(name=f"{MARK} PANELS", sort_order=1, is_optional=False)
        mat = Material(name=f"{MARK} SKIN", unit_of_measure="m2", price_per_unit=100.0, is_active=True)
        db.add_all([ga, gb, sec, mat])
        db.flush()
        ta = TrailerType(name=f"{MARK} BODY ALPHA", is_active=True, group_id=ga.id, default_length=6.0,
                         default_width=2.5, default_height=2.4)
        tb = TrailerType(name=f"{MARK} BODY BETA", is_active=True, group_id=gb.id, default_length=6.0,
                         default_width=2.5, default_height=2.4)
        db.add_all([ta, tb])
        db.flush()
        for tt in (ta, tb):
            db.add(BillOfMaterial(trailer_type_id=tt.id, material_id=mat.id, formula_expression="length*width",
                                  waste_percentage=0, bom_section=sec.name, bom_section_id=sec.id, sort_order=1))
        db.add(CalculationRecord(trailer_type_id=ta.id, quote_number=QUOTE, dimensions_json="{}",
                                 result_json='{"items": []}', status="pending"))
        db.commit()
        ids = {"ga": ga.id, "gb": gb.id, "ta": ta.id, "tb": tb.id}
    yield ids
    with SessionLocal() as db:
        _purge(db)


def _rgb(hex_: str) -> str:
    h = hex_.lstrip("#")
    return f"rgb({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)})"


def _bar(page: Page) -> str:
    return page.evaluate("() => getComputedStyle(document.getElementById('trailer-select')"
                         ".closest('.fam-select-wrap'), '::before').backgroundColor")


def test_the_body_type_box_groups_and_colours_by_family(page: Page, fams) -> None:
    from app.services import body_family as bf
    admin_session(page, base=_base())
    page.goto("/mes/calculator?stay=1")
    sel = page.locator("#trailer-select")
    expect(sel).to_be_visible(timeout=T)
    assert page.evaluate("() => [...document.styleSheets].some(s => (s.href || '').includes('theme-mes'))")

    labels = sel.locator("optgroup").evaluate_all("gs => gs.map(g => g.label)")
    assert labels.index(f"{MARK} ALPHA") < labels.index(f"{MARK} BETA") and labels[-1] == "──────────"
    ink = sel.locator(f"option[value='{fams['ta']}']").evaluate("o => getComputedStyle(o).color")
    assert ink == _rgb(bf.ink("#E03131"))

    page.select_option("#trailer-select", str(fams["ta"]))
    expect(page.locator("#bom-area tr.calc-grp-row[data-bom-id]")).to_have_count(1, timeout=T)
    assert _bar(page) == _rgb("#E03131")
    expect(sel).to_have_attribute("title", f"Family: {MARK} ALPHA")
    expect(page.locator("#topbar-title .fam-chip")).to_have_text(f"{MARK} ALPHA")
    # the top bar + the BODY TYPE panel only: the cost summary's customer list never goes into a screenshot
    out = SCREENSHOT_ROOT / JOURNEY
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / "01-body-type-family-bar.png"), clip={"x": 0, "y": 0, "width": 975, "height": 520})

    page.select_option("#trailer-select", str(fams["tb"]))
    expect(page.locator("#topbar-title .fam-chip")).to_have_text(f"{MARK} BETA", timeout=T)
    assert _bar(page) == _rgb("#168ED9")

    # the Enter chain: the body-type box still hands over to Length
    page.focus("#trailer-select")
    page.keyboard.press("Enter")
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "f-length"


def test_an_admin_colour_change_shows_on_the_calculator_and_the_costings_list(page: Page, fams) -> None:
    from app.services import body_family as bf
    admin_session(page, base=_base())
    page.goto("/admin/quote-templates?skin=mes")
    expect(page.locator(f"input[name='name'][value='{MARK} ALPHA']")).to_be_visible(timeout=T)

    def _family_row(name: str):
        """(colour box, Save button) of a family's row: one name, one colour box and one Save per group row, in
        page order, so the row's index picks all three (a table-row form's inputs are not its DOM children)."""
        i = page.locator("input[name='name']").evaluate_all(f"els => els.findIndex(e => e.value === '{name}')")
        assert i >= 0, name
        return (page.locator("input[name='colour']").nth(i),
                page.locator("button[type=submit]").filter(has_text="Save").nth(i))

    # a colour too light for the MES screens: it warns, and Cancel saves nothing
    hex_box, save = _family_row(f"{MARK} ALPHA")
    hex_box.fill("#38BDF8")
    save.click()
    expect(page.locator("#confirm-message")).to_contain_text("needs 3:1", timeout=T)
    shot(page, "02-low-contrast-warning", JOURNEY)
    page.locator("#modal-confirm button").filter(has_text="Cancel").click()
    page.goto("/admin/quote-templates?skin=mes")
    expect(page.locator(f"input[name='name'][value='{MARK} ALPHA']")).to_be_visible(timeout=T)
    from app.database import SessionLocal, TrailerGroup
    with SessionLocal() as db:
        assert db.get(TrailerGroup, fams["ga"]).colour == "#E03131", "Cancel must save nothing"

    # an approved colour saves without a warning
    hex_box, save = _family_row(f"{MARK} ALPHA")
    hex_box.fill("#D63384")
    with page.expect_navigation(timeout=T):
        save.click()
    with SessionLocal() as db:
        assert db.get(TrailerGroup, fams["ga"]).colour == "#D63384"

    # the calculator shows the new colour
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(fams["ta"]))
    expect(page.locator("#topbar-title .fam-chip")).to_have_text(f"{MARK} ALPHA", timeout=T)
    assert _bar(page) == _rgb("#D63384")

    # …and so does the MES costings list: the body name stays the text, the chip sits beside it
    page.goto("/mes-app/costings")
    row = page.locator("[data-testid='costing-row']", has_text=QUOTE)
    expect(row).to_be_visible(timeout=30_000)
    chip = row.locator("[data-testid='family-chip']")
    expect(chip).to_have_text(f"{MARK} ALPHA")
    expect(row).to_contain_text(f"{MARK} BODY ALPHA")
    assert chip.evaluate("c => getComputedStyle(c).color") == _rgb(bf.ink("#D63384"))
    assert chip.locator("span").first.evaluate("d => getComputedStyle(d).backgroundColor") == _rgb("#D63384")
    assert row.evaluate("r => getComputedStyle(r).backgroundColor") in ("rgba(0, 0, 0, 0)", "rgb(255, 255, 255)"), (
        "the row must not be coloured — the chip carries the family")
    # only OUR row: the list's other rows carry customer names, which never go into a committed screenshot
    out = SCREENSHOT_ROOT / JOURNEY
    out.mkdir(parents=True, exist_ok=True)
    row.screenshot(path=str(out / "03-costings-list-family-chip.png"))
