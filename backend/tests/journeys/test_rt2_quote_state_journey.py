"""RT2 Part 1 + 1c — a quote never writes the Body Template; a new costing opens on its
body's default foam grade (RT2_DISPATCH Part 1 §4, RT2_RULING_1 R3 / R6.7).

Part 1 (the door body, flat panel — a DRD/SRD pair each, a FRONT EPS/PU pair, one PU
FOAM line whose quantity reads {FRONT PU}):
  1. Toggling DRD <-> SRD and EPS <-> PU, several times, moves the QUOTE — every calc's
     body_variables (what the price used) follow each toggle, and the PU FOAM line is
     priced only while FRONT is PU — while the six template thicknesses in the DB never
     move. Saving freezes the quote's own door + insulation into the costing; re-opening
     it brings back ITS door (SRD) and ITS thicknesses; the template is still untouched.
  2. The NEXT user (a fresh browser) opens the body on the TEMPLATE's door (DRD), not on
     the door the previous quote ended on — the RT1 door-report defect, closed.

Part 1c (two foam bodies of the same shape; one defaults to 4G in Body Templates):
  3. A new costing on the 4G-default body opens on 4G — even though this browser's old
     v1.51 memory says 32D — the radio says "(body default)", and the calc is priced 4G.
     Switched to 32D and saved, it re-opens on 32D (a saved costing keeps its own grade).
  4. A 32D-default body is unchanged: it opens on 32D, labelled "(body default)".

Negative control (RT2_RETURN_2): with the pre-RT2 calculator.js restored, test 1's
template assertion and test 3's 4G assertion fail.

Marker JRT2; purge at setup AND teardown (materials by the marker CODE, because the foam
line's material must be named exactly "PU FOAM"); admin_session gets base=live_server.
"""
from __future__ import annotations

import time

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "rt2_quote_state"
MARK = "JRT2"
FOAM_FORMULA = f"(1.22*2.44*{{{MARK} FRONT PU}}/2.98)*(1.22*2.44)*2"     # Burt's PU row, term for term
FOAM_QTY_AT_60MM = (1.22 * 2.44 * 0.06 / 2.98) * (1.22 * 2.44) * 2


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_costings.calculations WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE material_code = :c"), {"c": MARK})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    from app.database import BillOfMaterial, Customer, Material, SessionLocal, TrailerType
    with SessionLocal() as db:
        _purge(db)
        customer = Customer(name=f"{MARK} CUSTOMER")
        db.add(customer)

        def mat(name, price=0.0, uom="each"):
            m = Material(name=name, unit_of_measure=uom, price_per_unit=price,
                         material_code=MARK, is_active=True)
            db.add(m)
            db.flush()
            return m

        def body(suffix, foam="32D"):
            t = TrailerType(name=f"{MARK} {suffix}", is_active=True, default_length=6.0,
                            default_width=2.4, default_height=2.4, default_insulation_foam=foam)
            db.add(t)
            db.flush()
            return t

        masters = {n: mat(f"{MARK} {n}") for n in
                   ("DRD EPS", "DRD PU", "SRD EPS", "SRD PU", "FRONT EPS", "FRONT PU")}
        foam = mat("PU FOAM", 4100.0, uom="m3")          # the engine grades on this exact NAME

        def master(t, name, group, default, value):
            r = BillOfMaterial(trailer_type_id=t.id, material_id=masters[name].id, is_body_option=True,
                               body_option_group=group, body_option_subgroup="INSULATION",
                               body_option_default=default, variable_value=value)
            db.add(r)
            db.flush()
            return r.id

        def foam_line(t):
            r = BillOfMaterial(trailer_type_id=t.id, material_id=foam.id, formula_expression=FOAM_FORMULA,
                               waste_percentage=0.0, bom_section="FRONT", sort_order=1)
            db.add(r)
            db.flush()
            return r.id

        door = body("DOOR BODY")
        ids = {"customer": customer.id, "door": door.id, "door_masters": {
            "DRD EPS": master(door, "DRD EPS", "DRD", True, 0.06),
            "DRD PU": master(door, "DRD PU", "DRD", False, 0.0),
            "SRD EPS": master(door, "SRD EPS", "SRD", False, 0.0),
            "SRD PU": master(door, "SRD PU", "SRD", False, 0.0),
            "FRONT EPS": master(door, "FRONT EPS", "FRONT", True, 0.06),
            "FRONT PU": master(door, "FRONT PU", "FRONT", False, 0.0)}}
        ids["door_foam"] = foam_line(door)
        for key, grade in (("foam4g", "4G"), ("foam32", "32D")):
            t = body(f"FOAM {grade} BODY", foam=grade)
            ids[key] = t.id
            ids[f"{key}_masters"] = {"FRONT EPS": master(t, "FRONT EPS", "FRONT", False, 0.0),
                                     "FRONT PU": master(t, "FRONT PU", "FRONT", True, 0.06)}
            ids[f"{key}_foam"] = foam_line(t)
        db.commit()
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


DOOR_TEMPLATE = {"DRD EPS": 0.06, "DRD PU": 0.0, "SRD EPS": 0.0, "SRD PU": 0.0,
                 "FRONT EPS": 0.06, "FRONT PU": 0.0}


def _template(master_ids: dict) -> dict:
    """The Body Template's thicknesses, from the DB."""
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:
        return {n: round(float(db.get(BillOfMaterial, i).variable_value or 0), 6) for n, i in master_ids.items()}


def _bv(res: dict) -> dict:
    """The quote's thicknesses AS PRICED: the calc response's body_variables, unprefixed."""
    pre = f"{MARK} "
    return {k[len(pre):]: v for k, v in (res.get("body_variables") or {}).items() if k.startswith(pre)}


def _calc_until(page: Page, action, want: dict, tid: int):
    """Do `action`, then wait for a calc of body `tid` whose priced thicknesses read
    `want` — the STATE, never 'a calc happened' (debounced calcs can be in flight)."""
    def ok(resp) -> bool:
        if resp.request.method != "POST" or not resp.url.split("?")[0].endswith("/api/calculate"):
            return False
        try:
            req = resp.request.post_data_json or {}
            got = _bv(resp.json())
        except Exception:
            return False
        return req.get("trailer_type_id") == tid and all(got.get(k) == v for k, v in want.items())
    with page.expect_response(ok, timeout=30_000) as r:
        action()
    return r.value.request.post_data_json, r.value.json()


def _item(res: dict, bom_id: int) -> dict:
    return next(i for i in res.get("items") or [] if i.get("bom_id") == bom_id)


def _pick_radio(page: Page, bom_id: int) -> None:
    """A flat-panel EPS/PU radio; the 'switch ALL insulation?' modal is answered No."""
    page.locator(f"#body-options-list input[type='radio'][data-bom-id='{bom_id}']").check()
    modal = page.locator("#modal-insulation-switch")
    expect(modal).to_be_visible(timeout=T)
    modal.locator(".btn-outline").click()
    expect(modal).to_be_hidden(timeout=T)


def _door_toggle(page: Page, grp: str) -> None:
    page.locator(f"#drd-srd-{grp}").check(force=True)    # the input sits inside a styled pill


def _open(page: Page, tid: int, want: dict):
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    return _calc_until(page, lambda: page.select_option("#trailer-select", str(tid)), want, tid)


def _still_untouched(ids: dict) -> None:
    time.sleep(1.0)                                       # any (wrong) template write would have landed
    assert _template(ids["door_masters"]) == DOOR_TEMPLATE


# ── Part 1 ────────────────────────────────────────────────────────────────────

def test_toggles_price_the_quote_and_never_write_the_template(page: Page, live_server: str, staged) -> None:
    ids, tid, m = staged, staged["door"], staged["door_masters"]
    assert _template(m) == DOOR_TEMPLATE                  # fixture sanity
    admin_session(page, base=live_server)
    _, res = _open(page, tid, {"DRD EPS": 0.06, "SRD EPS": 0.0, "FRONT EPS": 0.06, "FRONT PU": 0.0})
    assert _item(res, ids["door_foam"])["line_cost"] == 0              # FRONT is EPS: no PU foam
    shot(page, "01-opened-on-the-template", journey=JOURNEY)

    # Toggle, toggle back, toggle again — each step priced on the quote, none written.
    steps = [
        ("SRD door", lambda: _door_toggle(page, "SRD"), {"DRD EPS": 0.0, "SRD EPS": 0.06}),
        ("FRONT PU", lambda: _pick_radio(page, m["FRONT PU"]), {"FRONT EPS": 0.0, "FRONT PU": 0.06}),
        ("DRD door", lambda: _door_toggle(page, "DRD"), {"DRD EPS": 0.06, "SRD EPS": 0.0}),
        ("FRONT EPS", lambda: _pick_radio(page, m["FRONT EPS"]), {"FRONT EPS": 0.06, "FRONT PU": 0.0}),
        ("SRD door again", lambda: _door_toggle(page, "SRD"), {"DRD EPS": 0.0, "SRD EPS": 0.06}),
        ("FRONT PU again", lambda: _pick_radio(page, m["FRONT PU"]), {"FRONT EPS": 0.0, "FRONT PU": 0.06}),
    ]
    for label, act, want in steps:
        _, res = _calc_until(page, act, want, tid)
        _still_untouched(ids)
        print(f"   toggle {label!r}: quote priced {want}; template unchanged")
    foam = _item(res, ids["door_foam"])
    assert foam["quantity"] == pytest.approx(FOAM_QTY_AT_60MM, abs=5e-5)   # the price followed the quote
    assert foam["line_cost"] == pytest.approx(FOAM_QTY_AT_60MM * 4100.0, abs=0.5)    # (the API rounds qty)
    shot(page, "02-srd-and-front-pu-on-the-quote", journey=JOURNEY)

    # Save: the quote's own door and insulation go INTO the costing.
    page.fill("#f-margin", "0")
    page.select_option("#cust-select", value=str(ids["customer"]))
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    page.click("#approve-btn")
    rec_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec_id:
            break
    assert rec_id, "the costing did not save"
    saved = page.request.get(f"{live_server.rstrip('/')}/api/calculations/{rec_id}").json()
    sbv = _bv(saved.get("saved_result") or {})
    assert (sbv["SRD EPS"], sbv["DRD EPS"], sbv["FRONT PU"], sbv["FRONT EPS"]) == (0.06, 0.0, 0.06, 0.0), sbv
    _still_untouched(ids)

    # Re-open it: ITS door (SRD) and ITS thicknesses come back.
    page.goto("/calculator")                              # a fresh page load, same browser
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    _, res = _calc_until(page, lambda: page.goto(f"/calculator?edit={rec_id}"),
                         {"SRD EPS": 0.06, "DRD EPS": 0.0, "FRONT PU": 0.06, "FRONT EPS": 0.0}, tid)
    expect(page.locator("#drd-srd-SRD")).to_be_checked(timeout=T)
    expect(page.locator(f"#body-options-list input[type='radio'][data-bom-id='{m['FRONT PU']}']")).to_be_checked()
    assert _item(res, ids["door_foam"])["line_cost"] == pytest.approx(FOAM_QTY_AT_60MM * 4100.0, abs=0.5)
    _still_untouched(ids)
    print(f"   {len(steps)} toggles + save + re-open: template unchanged after each of the {len(steps) + 2} checks")
    shot(page, "03-reopened-with-its-own-door", journey=JOURNEY)


def test_the_next_user_opens_the_templates_door(page: Page, live_server: str, staged) -> None:
    """A fresh browser (no remembered state) after the quote above ended on SRD + PU."""
    ids = staged
    admin_session(page, base=live_server)
    _open(page, ids["door"], {"DRD EPS": 0.06, "SRD EPS": 0.0, "FRONT EPS": 0.06, "FRONT PU": 0.0})
    expect(page.locator("#drd-srd-DRD")).to_be_checked(timeout=T)
    expect(page.locator("#drd-srd-SRD")).not_to_be_checked()
    assert _template(ids["door_masters"]) == DOOR_TEMPLATE
    shot(page, "04-next-user-gets-the-template-door", journey=JOURNEY)


# ── Part 1c ───────────────────────────────────────────────────────────────────

def _foam_block(page: Page):
    block = page.locator("#insulation-foam-block")
    expect(block).to_be_visible(timeout=T)
    return block


def test_a_new_costing_opens_on_the_bodys_default_foam(page: Page, live_server: str, staged) -> None:
    ids, tid = staged, staged["foam4g"]
    admin_session(page, base=live_server)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    # This browser's OLD v1.51 memory says 32D for this body — it must no longer decide.
    page.evaluate(f"() => localStorage.setItem('ins_foam_{tid}', '32D')")
    req, res = _calc_until(page, lambda: page.select_option("#trailer-select", str(tid)), {"FRONT PU": 0.06}, tid)
    assert req["insulation_foam"] == "4G"
    block = _foam_block(page)
    expect(block.locator("input[value='4G']")).to_be_checked()
    expect(block.locator("input[value='4G']")).to_have_attribute("data-body-default", "1")
    expect(block).to_contain_text("4G FOAM (body default)")
    foam = _item(res, ids["foam4g_foam"])
    assert foam["unit_price"] > 4100.0                     # graded 4G by the stored factor
    shot(page, "05-4g-default-body-opens-on-4g", journey=JOURNEY)

    # The user switches this quote to 32D and saves: the saved costing keeps 32D.
    page.fill("#f-margin", "0")
    req, res = _calc_until(page, lambda: block.locator("input[value='32D']").check(), {"FRONT PU": 0.06}, tid)
    assert req["insulation_foam"] == "32D"
    assert _item(res, ids["foam4g_foam"])["unit_price"] == pytest.approx(4100.0)
    page.select_option("#cust-select", value=str(ids["customer"]))
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    page.click("#approve-btn")
    rec_id = None
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec_id = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec_id:
            break
    assert rec_id, "the costing did not save"
    assert page.request.get(f"{live_server.rstrip('/')}/api/calculations/{rec_id}").json()["insulation_foam"] == "32D"
    req, _ = _calc_until(page, lambda: page.goto(f"/calculator?edit={rec_id}"), {"FRONT PU": 0.06}, tid)
    assert req["insulation_foam"] == "32D"
    expect(_foam_block(page).locator("input[value='32D']")).to_be_checked(timeout=T)
    expect(_foam_block(page)).to_contain_text("4G FOAM (body default)")    # the default still shows where it is
    shot(page, "06-saved-32d-costing-reopens-on-32d", journey=JOURNEY)


def test_a_32d_default_body_is_unchanged(page: Page, live_server: str, staged) -> None:
    ids, tid = staged, staged["foam32"]
    admin_session(page, base=live_server)
    req, res = _open(page, tid, {"FRONT PU": 0.06})
    assert req["insulation_foam"] == "32D"
    block = _foam_block(page)
    expect(block.locator("input[value='32D']")).to_be_checked()
    expect(block).to_contain_text("32D PU FOAM (body default)")
    assert _item(res, ids["foam32_foam"])["unit_price"] == pytest.approx(4100.0)
    shot(page, "07-32d-default-body-unchanged", journey=JOURNEY)
