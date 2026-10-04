"""RT4 Part A — "Move into existing section" in a real browser, Body Templates on the MES skin (RT4_RULING_1 Q4).

  1. Body A's section 'RT4J DOOR FITTINGS SRD' is renamed, in its Edit-section dialog, to the name of the shared
     section 'RT4J SRD DOOR FITTINGS' (typed in lower case). The dialog does not fail: it OFFERS THE MOVE, naming
     how many other bodies use the target and how many of this body's lines move. Move → A's lines show under the
     new section, and because no body uses the old one any more, it offers "Delete: no body uses it any more" —
     Delete removes it from the section list.
  2. A plain rename of a section two bodies share warns first and names both bodies; Cancel changes nothing.

Marker rows RT4J* only — created and purged here. Base-aware (MES_BASE).
Negative control (RT4_RETURN_2): with the v1.60.0 admin_templates.js put back, step 1 fails (no move offer).
"""
from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

from _common import _DEFAULT_BASE, SCREENSHOT_ROOT, admin_session  # noqa: E402

T = 20_000
JOURNEY = "rt4_section_move"
MARK = "RT4J"
OLD = f"{MARK} DOOR FITTINGS SRD"
NEW = f"{MARK} SRD DOOR FITTINGS"


def _base() -> str:
    return os.environ.get("MES_BASE", _DEFAULT_BASE).rstrip("/")


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE 'RT4J%')"))
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE 'RT4J%'"))
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE 'RT4J%'"))
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE 'RT4J%'"))
    db.commit()


@pytest.fixture()
def bodies():
    """A: two lines in OLD. B: one line in NEW (so NEW is 'used by 1 other body')."""
    from app.database import BillOfMaterial, BOMSection, Material, SessionLocal, TrailerType
    with SessionLocal() as db:
        _purge(db)
        old = BOMSection(name=OLD, sort_order=9301)
        new = BOMSection(name=NEW, sort_order=9302)
        mat = Material(name=f"{MARK} HINGE", unit_of_measure="each", price_per_unit=10.0, is_active=True)
        a = TrailerType(name=f"{MARK} BODY A", is_active=True, default_length=6.0, default_width=2.5,
                        default_height=2.4)
        b = TrailerType(name=f"{MARK} BODY B", is_active=True, default_length=6.0, default_width=2.5,
                        default_height=2.4)
        db.add_all([old, new, mat, a, b])
        db.flush()
        for t, s, n in ((a, old, 2), (b, new, 1)):
            for i in range(n):
                db.add(BillOfMaterial(trailer_type_id=t.id, material_id=mat.id, formula_expression=str(i + 1),
                                      waste_percentage=0, bom_section=s.name, bom_section_id=s.id, sort_order=i))
        db.commit()
        ids = {"a": a.id, "b": b.id, "old": old.id, "new": new.id}
    yield ids
    with SessionLocal() as db:
        _purge(db)


def _sections_by_name() -> dict:
    from app.database import BOMSection, SessionLocal
    with SessionLocal() as db:
        return {s.name: s.id for s in db.query(BOMSection).filter(BOMSection.name.like(f"{MARK}%")).all()}


def _open_body(page: Page, tid: int) -> None:
    page.goto("/admin/templates?skin=mes")
    page.locator(f"#tt-{tid}").first.click()
    expect(page.locator("#bom-title")).to_contain_text(MARK, timeout=T)


def _edit_section(page: Page, name: str) -> None:
    page.locator("tr", has_text=name).locator("span[title^='Edit section']").first.click()
    expect(page.locator("#modal-edit-section")).to_be_visible(timeout=T)
    expect(page.locator("#es-name")).to_have_value(name)


def test_rename_to_an_existing_name_offers_the_move_then_the_delete(page: Page, bodies) -> None:
    admin_session(page, base=_base())
    _open_body(page, bodies["a"])
    _edit_section(page, OLD)
    expect(page.locator("#es-usage")).to_contain_text("used by 1 body", timeout=T)
    page.fill("#es-name", NEW.lower())                       # any case: it IS the shared section
    page.click("#modal-edit-section button.btn-primary")

    msg = page.locator("#confirm-message")
    expect(msg).to_have_text(f"'{NEW}' is already used by 1 other body. "
                             f"Move this body's 2 lines from '{OLD}' into it?", timeout=T)
    expect(page.locator("#confirm-ok")).to_have_text("Move")
    out = SCREENSHOT_ROOT / JOURNEY
    out.mkdir(parents=True, exist_ok=True)
    page.locator("#modal-confirm .modal").screenshot(path=str(out / "01-move-offer.png"))
    page.click("#confirm-ok")

    expect(page.locator("#confirm-title")).to_have_text("Delete: no body uses it any more", timeout=T)
    expect(msg).to_contain_text(f"No body uses '{OLD}' any more")
    page.locator("#modal-confirm .modal").screenshot(path=str(out / "02-delete-offer.png"))
    page.click("#confirm-ok")

    expect(page.locator("tr", has_text=NEW).first).to_be_visible(timeout=T)
    expect(page.locator("tr", has_text=OLD)).to_have_count(0)
    assert OLD not in _sections_by_name()                    # deleted, as offered
    page.screenshot(path=str(out / "03-lines-under-the-shared-section.png"), clip={"x": 0, "y": 0, "width": 1280, "height": 640})


def test_a_plain_rename_of_a_shared_section_warns_and_names_the_bodies(page: Page, bodies) -> None:
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:                               # A also uses NEW: two bodies share it
        db.query(BillOfMaterial).filter_by(trailer_type_id=bodies["a"]).update(
            {"bom_section": NEW, "bom_section_id": bodies["new"]})
        db.commit()
    admin_session(page, base=_base())
    _open_body(page, bodies["a"])
    _edit_section(page, NEW)
    page.fill("#es-name", f"{MARK} RENAMED")
    page.click("#modal-edit-section button.btn-primary")
    expect(page.locator("#confirm-title")).to_have_text("Rename a shared section", timeout=T)
    expect(page.locator("#confirm-message")).to_contain_text(
        f"This renames '{NEW}' on all 2 bodies that use it: {MARK} BODY A, {MARK} BODY B.")
    page.click("#confirm-cancel")
    assert NEW in _sections_by_name() and f"{MARK} RENAMED" not in _sections_by_name()


def test_the_sections_list_reaches_a_section_no_body_uses(page: Page, bodies) -> None:
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:                               # nothing uses OLD any more
        db.query(BillOfMaterial).filter_by(trailer_type_id=bodies["a"]).update(
            {"bom_section": NEW, "bom_section_id": bodies["new"]})
        db.commit()
    admin_session(page, base=_base())
    page.goto("/admin/templates?skin=mes")
    page.click("#btn-sections")
    page.fill("#sections-filter", MARK)
    row = page.locator(".sections-row", has_text=OLD)
    expect(row).to_contain_text("unused", timeout=T)
    row.click()
    expect(page.locator("#es-usage")).to_have_text("No body uses it any more.", timeout=T)
    expect(page.locator("#es-delete")).to_have_text("Delete: no body uses it any more")
