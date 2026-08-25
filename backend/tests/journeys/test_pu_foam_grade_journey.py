"""v1.51 — PU insulation foam grade on the calculator: 32D PU FOAM vs 4G FOAM.

Burt used to hand-edit the workbook to swap PU grade, which is how single bodies
ended up with mixed pricing. The MES replaces that with ONE selection per costing
under BODY OPTIONS, and this journey is the end-to-end proof:

  1. A body that consumes PU foam opens with the pair visible and 32D checked.
  2. Selecting 4G raises EVERY PU foam line by exactly 5875/4310, raises the
     grand total by the same money, and leaves every other line untouched.
  3. Approve & Save freezes the grade into the record; reopening for edit brings
     it back with the 4G radio checked and the same money on screen.
  4. A body with no PU foam lines never shows the control at all.

Assertions are on the PER-LINE cost (server-computed, margin- and multiplier-
proof) rather than on a number this test predicts, so the journey cannot go red
for a reason that has nothing to do with the foam grade.

Marker J151; purge at setup AND teardown; admin_session gets base=live_server.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "pu_foam_grade"
MARK = "J151"

RATIO = 5875.0 / 4310.0          # PRICE 2017 MARCH.xlsx — C19 / C17


def _money(text: str) -> float:
    """'R 1 363,11' / '1,363.11' -> float. Same normalisation the free-hand
    journey uses; the app formats with the browser locale."""
    s = "".join(ch for ch in (text or "") if ch.isdigit() or ch in ".,-")
    if "." in s and "," in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s or 0)


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("""
        DELETE FROM icb_costings.calculations
         WHERE trailer_type_id IN (SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)
    """), {"m": f"{MARK}%"})
    db.execute(text("""
        DELETE FROM icb_costings.bill_of_materials
         WHERE trailer_type_id IN (SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)
    """), {"m": f"{MARK}%"})
    # Materials are GLOBAL, and one of ours must be named exactly "PU FOAM" for
    # the grade to reach it — so purge on the marker CODE, never on the name.
    db.execute(text("DELETE FROM icb_costings.materials WHERE material_code = :c"), {"c": MARK})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    from app.database import (BillOfMaterial, Customer, Material, SessionLocal,
                              TrailerType)
    with SessionLocal() as db:
        _purge(db)

        customer = Customer(name=f"{MARK} FOAM CUSTOMER")
        db.add(customer)

        def _body(suffix):
            t = TrailerType(name=f"{MARK} {suffix}", is_active=True,
                            default_length=6.0, default_width=2.4, default_height=2.4)
            db.add(t)
            db.flush()
            return t

        # PU body: a real PU foam cost line + a control line that must never move.
        pu_body = _body("PU FOAM BODY")
        # EPS body: same shape, no foam line at all — the control must be absent.
        eps_body = _body("NO FOAM BODY")

        def _mat(name, price, uom="m²"):
            m = Material(name=name, unit_of_measure=uom, price_per_unit=price,
                         material_code=MARK, is_active=True)
            db.add(m)
            db.flush()
            return m

        # Named exactly "PU FOAM" — services.insulation_foam grades on the
        # material NAME, so a marker prefix here would make the journey pass
        # while proving nothing about the real "PU"/"PU FOAM" rows.
        foam = _mat("PU FOAM", 1000.0)
        control = _mat(f"{MARK} CONTROL PLY", 500.0)
        # "PU INJECTION" is a DIFFERENT product; naming ours with the marker
        # keeps the global namespace clean while still exercising the exclusion.
        injection = _mat(f"{MARK} PU INJECTION", 700.0, uom="each")
        front_eps = _mat(f"{MARK} FRONT EPS", 0.0, uom="each")
        front_pu = _mat(f"{MARK} FRONT PU", 0.0, uom="each")

        def _line(trailer, mat, section, **kw):
            r = BillOfMaterial(trailer_type_id=trailer.id, material_id=mat.id,
                               formula_expression="1", waste_percentage=0.0,
                               bom_section=section, sort_order=0, **kw)
            db.add(r)
            db.flush()
            return r

        ids = {"customer": customer.id, "pu_body": pu_body.id, "eps_body": eps_body.id}
        ids["foam_row"] = _line(pu_body, foam, "FRONT").id
        ids["control_row"] = _line(pu_body, control, "FRONT").id
        ids["injection_row"] = _line(pu_body, injection, "FRONT").id
        # The EPS/PU insulation pair this body's foam sits under (v1.39.10 shape:
        # exactly one non-zero side, PU selected by default).
        ids["front_eps"] = _line(pu_body, front_eps, "FRONT", is_body_option=True,
                                 body_option_group="FRONT",
                                 body_option_subgroup="INSULATION",
                                 body_option_default=False, variable_value=0.0).id
        ids["front_pu"] = _line(pu_body, front_pu, "FRONT", is_body_option=True,
                                body_option_group="FRONT",
                                body_option_subgroup="INSULATION",
                                body_option_default=True, variable_value=0.06).id
        # No-foam body: a control line and a FULL insulation pair, so the Body
        # Options panel itself renders — the foam control must be absent because
        # this body has no PU foam LINE, not because the panel is empty.
        ids["eps_control_row"] = _line(eps_body, control, "FRONT").id
        _line(eps_body, front_eps, "FRONT", is_body_option=True,
              body_option_group="FRONT", body_option_subgroup="INSULATION",
              body_option_default=True, variable_value=0.06)
        _line(eps_body, front_pu, "FRONT", is_body_option=True,
              body_option_group="FRONT", body_option_subgroup="INSULATION",
              body_option_default=False, variable_value=0.0)
        db.commit()
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


# ── page helpers ─────────────────────────────────────────────────────────────

def _line_cost(page: Page, bom_id: int) -> float:
    return _money(page.locator(f"tr[data-bom-id='{bom_id}'] td.calc-line-cost").inner_text())


def _grand_total(page: Page) -> float:
    return _money(page.locator("#grand-total").inner_text())


def _open_body(page: Page, tt_id: int) -> None:
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(tt_id))
    expect(page.locator(".calc-grp-hdr").first).to_be_visible(timeout=T)
    expect(page.locator("#grand-total")).not_to_have_text("—", timeout=T)
    # Zero the margin so the grand total is a plain sum of line costs and the
    # money delta below is directly comparable to the line delta.
    page.fill("#f-margin", "0")
    _settle(page)


def _settle(page: Page) -> None:
    """Let the 700 ms debounced recalc land and the BOM table stop rebuilding."""
    expect(page.locator("#calc-status")).to_have_text("", timeout=T)
    page.wait_for_timeout(1200)


def _wait_for_line_cost(page: Page, bom_id: int, expected: float) -> float:
    """Poll for the expected STATE, never for 'it changed' — several debounced
    recalcs can be in flight, and the first intermediate result is about to be
    superseded. Python-side polling: the app's CSP has no unsafe-eval, so
    page.wait_for_function is unusable here."""
    waited, last = 0.0, None
    while waited < T / 1000.0:
        last = _line_cost(page, bom_id)
        if abs(last - expected) < 0.05:
            return last
        page.wait_for_timeout(250)
        waited += 0.25
    raise AssertionError(
        f"line {bom_id} settled on {last!r}, expected {expected:.2f}")


# ── the journey ──────────────────────────────────────────────────────────────

def test_foam_grade_moves_only_the_pu_lines(page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    _open_body(page, ids["pu_body"])

    # 1) The pair is on screen, under Body Options, defaulted to 32D.
    block = page.locator("#insulation-foam-block")
    expect(block).to_be_visible(timeout=T)
    expect(block).to_contain_text("Insulation foam")
    expect(block.locator("input[value='32D']")).to_be_checked()
    expect(block.locator("input[value='4G']")).not_to_be_checked()
    expect(block).to_contain_text("32D PU FOAM")
    expect(block).to_contain_text("4G FOAM")
    shot(page, "01-32d-default", journey=JOURNEY)

    foam32 = _line_cost(page, ids["foam_row"])
    control32 = _line_cost(page, ids["control_row"])
    injection32 = _line_cost(page, ids["injection_row"])
    total32 = _grand_total(page)
    assert foam32 > 0, "the staged PU foam line must cost something to be a test"

    # 2) Switch to 4G — the foam line rises by exactly the price-list ratio.
    block.locator("input[value='4G']").check()
    _wait_for_line_cost(page, ids["foam_row"], foam32 * RATIO)
    _settle(page)
    foam4g = _line_cost(page, ids["foam_row"])
    assert foam4g == pytest.approx(foam32 * RATIO, abs=0.05), (
        f"4G must be 32D x {RATIO:.5f}: {foam32:.2f} -> {foam4g:.2f}")

    # 3) Nothing else moves. PU INJECTION is a different product; the control
    #    line and the EPS side have no business following the grade.
    assert _line_cost(page, ids["control_row"]) == pytest.approx(control32, abs=0.01)
    assert _line_cost(page, ids["injection_row"]) == pytest.approx(injection32, abs=0.01)

    # 4) The grand total rose by exactly the foam line's own increase.
    total4g = _grand_total(page)
    assert total4g - total32 == pytest.approx(foam4g - foam32, abs=0.05), (
        f"total moved {total4g - total32:.2f}, foam line moved {foam4g - foam32:.2f}")
    shot(page, "02-4g-selected", journey=JOURNEY)

    # 5) And back: 32D restores the original money exactly.
    block.locator("input[value='32D']").check()
    _wait_for_line_cost(page, ids["foam_row"], foam32)
    _settle(page)
    assert _grand_total(page) == pytest.approx(total32, abs=0.05)


def test_the_grade_is_frozen_into_the_saved_costing_and_restored_on_edit(
        page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    _open_body(page, ids["pu_body"])

    page.locator("#insulation-foam-block input[value='4G']").check()
    _settle(page)
    foam4g = _line_cost(page, ids["foam_row"])

    # Save. Select the customer BY VALUE — the picker is search-filtered, so a
    # label match is not a reliable handle.
    page.select_option("#cust-select", value=str(ids["customer"]))
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    page.click("#approve-btn")
    # Poll for the saved id with page.evaluate (not wait_for_function — CSP), and
    # on the BARE identifier: calculator.js declares it with a top-level `let`,
    # which is not a property of window.
    rec_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec_id:
            break
    assert rec_id, "the costing did not save"

    # The grade is in the record's own snapshot, not re-derived from the BOM.
    payload = page.request.get(f"{live_server.rstrip('/')}/api/calculations/{rec_id}").json()
    assert payload["insulation_foam"] == "4G"

    # Reopening for edit restores the radio AND the money.
    page.goto(f"/calculator?edit={rec_id}")
    expect(page.locator("#insulation-foam-block input[value='4G']")).to_be_checked(timeout=30_000)
    _settle(page)
    assert _line_cost(page, ids["foam_row"]) == pytest.approx(foam4g, abs=0.05)
    shot(page, "03-reopened-on-4g", journey=JOURNEY)


def test_a_body_without_pu_foam_never_shows_the_control(
        page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    _open_body(page, ids["eps_body"])
    # The panel itself IS on screen (this body has an insulation pair) …
    expect(page.locator("#body-options-section")).to_be_visible(timeout=T)
    # … and the foam control still is not, because nothing here is priced in PU foam.
    expect(page.locator("#insulation-foam-block")).to_be_hidden(timeout=T)
    shot(page, "04-no-foam-no-control", journey=JOURNEY)
