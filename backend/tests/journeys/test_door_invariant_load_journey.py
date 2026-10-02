"""v1.44.1 — rear-door insulation invariant enforced on LOAD; RT2 Part 1 — on the QUOTE only.

A body opens with DRD as the (default) door while its SRD pair still carries
non-zero thickness in the template (the pre-invariant dirt Michael reported).
Opening the body in the calculator must price the quote with the inactive SRD pair
at 0 / 0 — while leaving the active DRD pair's thickness untouched.

Until RT2 the heal PERSISTED those zeros to the Body Template on mere open, from the
door the opening browser remembered: that is how one user's last door became the next
user's template (RT2_RETURN_1 §1.2). Now the heal is the quote's own state: the calc's
body_variables carry it, and the template stays exactly as staged — on every open.

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


STAGED = {"drd_eps": 0.06, "drd_pu": 0.0, "srd_eps": 0.05, "srd_pu": 0.02}   # the template, as staged
HEALED = {"drd_eps": 0.06, "drd_pu": 0.0, "srd_eps": 0.0, "srd_pu": 0.0}     # the QUOTE after the heal
NAMES = {k: f"{MARK} {k.replace('_', ' ').upper()}" for k in STAGED}


def _db_vals(ids) -> dict:
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:
        return {k: float(db.get(BillOfMaterial, ids[k]).variable_value or 0)
                for k in ("drd_eps", "drd_pu", "srd_eps", "srd_pu")}


def _is_healed_calc(resp) -> bool:
    if "/api/calculate" not in resp.url or resp.request.method != "POST" or resp.status != 200:
        return False
    bv = resp.json().get("body_variables") or {}
    return all(bv.get(NAMES[k]) == v for k, v in HEALED.items())


def _open_body(page: Page, live_server: str, ids) -> dict:
    admin_session(page, base=live_server)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    with page.expect_response(_is_healed_calc, timeout=30_000) as calc:
        page.select_option("#trailer-select", str(ids["trailer"]))
    return calc.value.json()


def test_load_zeroes_inactive_door_on_the_quote_only(page: Page, live_server: str, staged) -> None:
    ids = staged
    assert _db_vals(ids) == STAGED                    # fixture sanity: dirty before

    res = _open_body(page, live_server, ids)          # waits for a calc that priced the heal
    bv = res["body_variables"]
    assert {k: bv[NAMES[k]] for k in HEALED} == HEALED
    # Active door renders with its thickness intact. The INACTIVE door's rows
    # deliberately do NOT render (children unrender when the gate is off).
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['drd_eps']}']")).to_have_text(
        "(0.060 m)", timeout=30_000)
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['srd_eps']}']")).to_have_count(0)

    time.sleep(2)                                     # give any (wrong) template write time to land
    assert _db_vals(ids) == STAGED                    # RT2: the template is untouched
    shot(page, "01-healed-panel", journey=JOURNEY)


def test_every_load_heals_the_quote_again(page: Page, live_server: str, staged) -> None:
    """Nothing was persisted, so a second open heals its OWN quote again — and still
    writes nothing."""
    ids = staged
    assert _db_vals(ids) == STAGED
    res = _open_body(page, live_server, ids)
    assert {k: res["body_variables"][NAMES[k]] for k in HEALED} == HEALED
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['drd_eps']}']")).to_have_text(
        "(0.060 m)", timeout=30_000)
    time.sleep(2)
    assert _db_vals(ids) == STAGED
    shot(page, "02-second-load-clean", journey=JOURNEY)
