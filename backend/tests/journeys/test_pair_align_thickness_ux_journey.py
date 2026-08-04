"""v1.44.2 — pair-invariant regression on load + thickness-editing UX.

Journey 1 (calculator): a body whose FRONT pair is INVERTED (EPS selected @ 0,
PU carries 0.07) and whose SIDES pair has NO value at all (both NULL — the
EXPLOSIVE-class invisible state) opens in the calculator →
  - FRONT auto-aligns: EPS span shows (0.070 m), template persisted (EPS 0.07,
    PU 0). This is _enforceInsulationInvariant (v1.39.10) doing its job at the
    render chokepoint — locked here as a REGRESSION so the invariant can never
    silently stop covering the load path;
  - SIDES renders BOTH spans as (0.000 m) despite NULL — the v1.44.2 render
    hardening that makes a missing thickness loud + clickable instead of
    invisible (the invariant deliberately skips never-seeded pairs).

Journey 2 (admin): /admin/templates shows the red "no thickness set" chip on
the NULL pair rows; clicking it opens the row editor; saving with an EMPTY
value writes 0.0 (not NULL) for pair rows.

Marker J1442; purge at setup AND teardown; admin_session gets base=live_server.
"""
from __future__ import annotations

import time

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "pair_align_thickness_ux"
MARK = "J1442"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.bill_of_materials WHERE material_id IN "
        "(SELECT id FROM icb_costings.materials WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    from app.database import BillOfMaterial, Material, SessionLocal, TrailerType
    with SessionLocal() as db:
        _purge(db)
        trailer = TrailerType(name=f"{MARK} PAIR UX BODY", is_active=True,
                              default_length=5.0, default_width=2.4, default_height=2.4)
        db.add(trailer)
        db.flush()

        def _mat(name):
            m = Material(name=f"{MARK} {name}", unit_of_measure="each", price_per_unit=0.0)
            db.add(m)
            db.flush()
            return m

        def _bom(name, group, default=False, var=None):
            r = BillOfMaterial(trailer_type_id=trailer.id, material_id=_mat(name).id,
                               is_body_option=True, body_option_group=group,
                               body_option_subgroup="INSULATION",
                               body_option_default=default, variable_value=var)
            db.add(r)
            db.flush()
            return r

        ids = {"trailer": trailer.id}
        # Inverted pair — heal target
        ids["front_eps"] = _bom("FRONT EPS", "FRONT", default=True, var=0.0).id
        ids["front_pu"] = _bom("FRONT PU", "FRONT", var=0.07).id
        # NULL pair — render-hardening + admin-chip target
        ids["sides_eps"] = _bom("SIDES EPS", "SIDES", default=True, var=None).id
        ids["sides_pu"] = _bom("SIDES PU", "SIDES", var=None).id
        db.commit()
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _db_val(ids, key):
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:
        return db.get(BillOfMaterial, ids[key]).variable_value


def test_load_aligns_pair_and_renders_null_as_zero(page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(ids["trailer"]))

    # Pair heal: FRONT EPS (selected) shows the carried 0.070.
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['front_eps']}']")).to_have_text(
        "(0.070 m)", timeout=30_000)
    # Render hardening: NULL pair rows show loud, clickable (0.000 m) spans.
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['sides_eps']}']")).to_have_text("(0.000 m)")
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['sides_pu']}']")).to_have_text("(0.000 m)")
    shot(page, "01-aligned-and-null-rendered", journey=JOURNEY)

    # Heal persisted to the template; NULL pair untouched by the heal (no guess).
    for _ in range(40):
        if float(_db_val(ids, "front_eps") or 0) == 0.07:
            break
        time.sleep(0.5)
    assert float(_db_val(ids, "front_eps") or 0) == 0.07
    assert float(_db_val(ids, "front_pu") or 0) == 0
    assert _db_val(ids, "sides_eps") is None and _db_val(ids, "sides_pu") is None


def test_admin_chip_and_empty_save_writes_zero(page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    page.goto("/admin/templates")
    row = page.locator(f"#tt-{ids['trailer']}")
    expect(row).to_be_visible(timeout=T)
    row.click()

    # Red chip on the NULL pair row (SIDES EPS still NULL — journey 1 didn't guess).
    bom_row = page.locator(f"tr:has(button[onclick*='openEditBOM({ids['sides_eps']})'])")
    chip = bom_row.get_by_text("no thickness set")
    expect(chip).to_be_visible(timeout=30_000)
    shot(page, "02-admin-no-thickness-chip", journey=JOURNEY)

    # Click the chip → row editor opens in Body Variable mode → save with the
    # value EMPTY → pair rows persist 0.0 (not NULL).
    chip.click()
    expect(page.locator("#modal-edit-bom")).to_be_visible(timeout=T)
    inp = page.locator("#edit-bom-variable-value-input")
    expect(inp).to_be_visible(timeout=T)
    inp.fill("")
    page.locator("#modal-edit-bom").get_by_role("button", name="Save Changes").click()
    for _ in range(40):
        if _db_val(ids, "sides_eps") is not None:
            break
        time.sleep(0.5)
    v = _db_val(ids, "sides_eps")
    assert v is not None and float(v) == 0.0, f"empty save must write 0.0, got {v!r}"
    shot(page, "03-empty-save-wrote-zero", journey=JOURNEY)
