"""v1.44.1 — rear-door insulation invariant enforced on LOAD.

A body opens with DRD as the (default) door while its SRD pair still carries
non-zero thickness in the template (the pre-invariant dirt Michael reported).
Opening the body in the calculator must: show the SRD pair at (0.000 m), toast
the heal, and PERSIST the zeros to the body template — while leaving the
active DRD pair's thickness untouched. Second load: nothing left to heal.

Marker J1441; purge at setup AND teardown. admin_session gets base=live_server
(banked MES_BASE trap).
"""
from __future__ import annotations

import time

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "door_invariant_load"
MARK = "J1441"


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
    """DRD active by default (its EPS carries 0.06); SRD pair DIRTY (0.05/0.02)."""
    from app.database import BillOfMaterial, Material, SessionLocal, TrailerType
    with SessionLocal() as db:
        _purge(db)
        trailer = TrailerType(name=f"{MARK} DOOR DIRT BODY", is_active=True,
                              default_length=5.0, default_width=2.4, default_height=2.4)
        db.add(trailer)
        db.flush()

        def _mat(name):
            m = Material(name=f"{MARK} {name}", unit_of_measure="each", price_per_unit=0.0)
            db.add(m)
            db.flush()
            return m

        def _bom(mat, group, sub, default=False, var=None):
            r = BillOfMaterial(trailer_type_id=trailer.id, material_id=mat.id,
                               is_body_option=True, body_option_group=group,
                               body_option_subgroup=sub, body_option_default=default,
                               variable_value=var)
            db.add(r)
            db.flush()
            return r

        ids = {"trailer": trailer.id}
        ids["drd_eps"] = _bom(_mat("DRD EPS"), "DRD", "INSULATION", True, 0.06).id
        ids["drd_pu"] = _bom(_mat("DRD PU"), "DRD", "INSULATION", False, 0.0).id
        ids["srd_eps"] = _bom(_mat("SRD EPS"), "SRD", "INSULATION", False, 0.05).id
        ids["srd_pu"] = _bom(_mat("SRD PU"), "SRD", "INSULATION", False, 0.02).id
        db.commit()
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


HEALED = {"drd_eps": 0.06, "drd_pu": 0.0, "srd_eps": 0.0, "srd_pu": 0.0}


def _db_vals(ids) -> dict:
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:
        return {k: float(db.get(BillOfMaterial, ids[k]).variable_value or 0)
                for k in ("drd_eps", "drd_pu", "srd_eps", "srd_pu")}


def _wait_for_heal(ids, tries: int = 40) -> dict:
    """The heal's PUTs land asynchronously after the panel renders — poll the DB."""
    for _ in range(tries):
        vals = _db_vals(ids)
        if vals == HEALED:
            return vals
        time.sleep(0.5)
    return _db_vals(ids)


def test_load_zeroes_inactive_door_and_persists(page: Page, live_server: str, staged) -> None:
    ids = staged
    assert _db_vals(ids)["srd_eps"] == 0.05          # fixture sanity: dirty before

    admin_session(page, base=live_server)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(ids["trailer"]))

    # Active door renders with its thickness intact. The INACTIVE door's rows
    # deliberately do NOT render (children unrender when the gate is off), so
    # the heal is asserted where it matters: the persisted template values.
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['drd_eps']}']")).to_have_text(
        "(0.060 m)", timeout=30_000)
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['srd_eps']}']")).to_have_count(0)

    vals = _wait_for_heal(ids)
    assert vals == HEALED, vals                       # persist-to-template semantics
    shot(page, "01-healed-panel", journey=JOURNEY)


def test_second_load_is_clean_noop(page: Page, live_server: str, staged) -> None:
    ids = staged
    assert _db_vals(ids) == HEALED                    # already healed by test 1
    admin_session(page, base=live_server)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(ids["trailer"]))
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['drd_eps']}']")).to_have_text(
        "(0.060 m)", timeout=30_000)
    time.sleep(2)                                     # give any (wrong) writes time to land
    assert _db_vals(ids) == HEALED                    # unchanged — heal is idempotent
    shot(page, "02-second-load-clean", journey=JOURNEY)
