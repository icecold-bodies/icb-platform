"""RT5 — Burt's body rules in red, in a real browser, on the light MES skin (RT5_DISPATCH; RT5_RULING_1).

  1. The family's rule note shows in red under BODY OPTIONS for every body of the family (a v2 body and a flat
     one), changes with the body (a two-line note keeps its lines), and is absent on a body whose family has none.
  2. An admin sets a note in Admin -> Quote templates (the family editor): an HTML string shows as TYPED on the
     calculator and in Body Templates (no element, no script); the edit is read back from the database, then set
     back and read back again.
  3. The INSULATION FOAM picker (RT5_RULING_1): hidden on a chiller-shaped body whose draft offers no PU and has
     none selected; shown on a freezer-shaped body that offers PU; shown again on a costing re-opened with PU on
     it (saved before the draft stopped offering PU, as on prod); and the calculate payload is IDENTICAL with the
     picker hidden and shown.

Negative control (RT5_RETURN_2): with the foam rule removed from calculator.js, test 3's "hidden" assertion fails.

Marker JRT5 only — created and purged here (setup AND teardown). Base-aware: admin_session(base=live_server), so
it runs against MES_BASE (a side port) and never dials :8000 itself.
"""
from __future__ import annotations

import json
import time

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 20_000
JOURNEY = "rt5_rule_notes"
MARK = "JRT5"
NOTE_C = f"No PU insulation for Chillers ({MARK})"
NOTE_F = f"Freezers: EPS insulation in the ROOF and FLOOR only ({MARK})\nnever in the SIDES, FRONT or doors"
XSS = f'<b>{MARK} bold</b> <img src=x onerror="window.__rt5=1"> & done'
RED = "rgb(209, 36, 36)"                         # #D12424 — body_family.RULE_NOTE_INK
EPS, PU = f"{MARK} FRONT EPS", f"{MARK} FRONT PU"


def _purge(db) -> None:
    from sqlalchemy import text
    tt = "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"
    for sql in (f"DELETE FROM icb_costings.calculations WHERE trailer_type_id IN {tt}",
                f"DELETE FROM icb_costings.configurator_drafts WHERE trailer_type_id IN {tt}",
                f"DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN {tt}",
                "DELETE FROM icb_costings.trailer_types WHERE name LIKE :m",
                "DELETE FROM icb_costings.trailer_groups WHERE name LIKE :m",
                "DELETE FROM icb_costings.materials WHERE name LIKE :m OR material_code = :c",
                "DELETE FROM icb_costings.customers WHERE name LIKE :m"):
        db.execute(text(sql), {"m": f"{MARK}%", "c": MARK})
    db.commit()


def _flag(nid, name, parent, value, bind_id) -> dict:
    return {"id": nid, "type": "flag", "label": name, "parentId": parent, "childIds": [], "flagMode": "radio",
            "flagValue": value, "flagBindingName": name, "flagBindingId": bind_id}


def _draft(eps_id, pu_id, eps_on: int, offer_pu: bool) -> dict:
    nodes = {"1": {"id": "1", "type": "category", "label": f"{MARK} FRONT", "sourceCategoryKey": None,
                   "parentId": None, "childIds": ["2", "3"] if offer_pu else ["2"]},
             "2": _flag("2", EPS, "1", eps_on, eps_id)}
    if offer_pu:
        nodes["3"] = _flag("3", PU, "1", 1 - eps_on, pu_id)
    return {"nextId": 4, "rootIds": ["1"], "itemRules": {}, "nodes": nodes}


@pytest.fixture(scope="module")
def staged():
    from app.database import (BillOfMaterial, ConfiguratorDraft, Customer, Material, SessionLocal, TrailerGroup,
                              TrailerType)
    with SessionLocal() as db:
        _purge(db)
        fam = {}
        for key, note, colour, order in (("chill", NOTE_C, "#168ED9", 9201), ("freeze", NOTE_F, "#4263EB", 9202),
                                         ("plain", None, "#7D858C", 9203)):
            g = TrailerGroup(name=f"{MARK} {key.upper()} FAM", colour=colour, sort_order=order, rule_note=note)
            db.add(g)
            db.flush()
            fam[key] = g.id
        customer = Customer(name=f"{MARK} CUSTOMER")
        db.add(customer)

        def mat(name, price=0.0, uom="each", code=None):
            m = Material(name=name, unit_of_measure=uom, price_per_unit=price, material_code=code, is_active=True)
            db.add(m)
            db.flush()
            return m
        m_eps, m_pu = mat(EPS, uom="m3"), mat(PU, uom="m3")
        m_foam = mat("PU FOAM", 4100.0, "m3", code=MARK)       # the engine grades on this exact NAME
        m_board = mat(f"{MARK} EPS BOARD", 900.0, "m3")

        def body(suffix, group, v2, eps_default):
            t = TrailerType(name=f"{MARK} {suffix}", is_active=True, configurator_v2=v2, group_id=fam[group],
                            default_length=6.0, default_width=2.4, default_height=2.4, default_insulation_foam="32D")
            db.add(t)
            db.flush()
            ids = {}
            for m, on, val in ((m_eps, eps_default, 0.06 if eps_default else 0.0),
                               (m_pu, not eps_default, 0.0 if eps_default else 0.06)):
                r = BillOfMaterial(trailer_type_id=t.id, material_id=m.id, formula_expression="1",
                                   is_body_option=True, body_option_group=f"{MARK} FRONT",
                                   body_option_subgroup="INSULATION", body_option_default=on,
                                   variable_value=val, bom_section="BODY OPTIONS")
                db.add(r)
                db.flush()
                ids[m.name] = r.id
            for m, formula in ((m_foam, f"(1.22*2.44*{{{PU}}})*2"), (m_board, f"width*height*{{{EPS}}}")):
                db.add(BillOfMaterial(trailer_type_id=t.id, material_id=m.id, formula_expression=formula,
                                      waste_percentage=0.0, bom_section=f"{MARK} FRONT"))
            db.flush()
            return t.id, ids[EPS], ids[PU]

        ids = {"fam": fam, "customer": customer.id}
        ids["chill"], ids["chill_eps"], ids["chill_pu"] = body("CHILL BODY", "chill", True, True)
        ids["chill2"], _, _ = body("CHILL FLAT BODY", "chill", False, True)
        ids["freeze"], ids["freeze_eps"], ids["freeze_pu"] = body("FREEZE BODY", "freeze", True, False)
        ids["plain"], _, _ = body("PLAIN BODY", "plain", False, True)
        # the chiller's draft still OFFERS PU (as before Michael's removal); test 3 removes it
        db.add(ConfiguratorDraft(trailer_type_id=ids["chill"],
                                 payload=json.dumps(_draft(ids["chill_eps"], ids["chill_pu"], 1, True))))
        db.add(ConfiguratorDraft(trailer_type_id=ids["freeze"],
                                 payload=json.dumps(_draft(ids["freeze_eps"], ids["freeze_pu"], 0, True))))
        db.commit()
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _db_note(gid):
    from app.database import SessionLocal, TrailerGroup
    with SessionLocal() as db:
        return db.get(TrailerGroup, gid).rule_note


def _calc(page: Page, action, tid: int, want=None):
    """Do `action`, then wait for a calculate of body `tid` whose request satisfies `want` (STATE, not 'a calc')."""
    def ok(resp) -> bool:
        if resp.request.method != "POST" or not resp.url.split("?")[0].endswith("/api/calculate"):
            return False
        try:
            req = resp.request.post_data_json or {}
        except Exception:
            return False
        return req.get("trailer_type_id") == tid and (want is None or want(req))
    with page.expect_response(ok, timeout=30_000) as r:
        action()
    return r.value.request.post_data_json


def _pick(page: Page, tid: int, want=None):
    return _calc(page, lambda: page.select_option("#trailer-select", str(tid)), tid, want)


def _note(page: Page):
    return page.locator("#body-rule-note")


def _open_calculator(page: Page) -> None:
    """A NEW quote: the calculator restores this browser's last session on load (it would re-select the previous
    body under our pick). Leave through a same-origin page (the unload handler saves on the way out), forget the
    session there, then open the calculator."""
    page.goto("/health/version")
    page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch (_) {} }")
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)


# ── 1 ─────────────────────────────────────────────────────────────────────────

def test_the_note_shows_for_every_body_of_its_family_changes_with_the_body_and_nowhere_else(
        page: Page, live_server: str, staged) -> None:
    ids = staged
    admin_session(page, base=live_server)
    _open_calculator(page)
    expect(_note(page)).to_be_hidden()                                    # no body picked yet
    _pick(page, ids["chill"])
    expect(_note(page)).to_be_visible(timeout=T)
    expect(page.locator("#body-rule-note-text")).to_have_text(NOTE_C)
    assert page.eval_on_selector("#body-rule-note", "e => getComputedStyle(e).color") == RED
    # it sits under the BODY OPTIONS heading, above the options list
    order = page.evaluate("""() => { const n = document.getElementById('body-rule-note'),
        l = document.getElementById('body-options-list');
        return !!(n.compareDocumentPosition(l) & Node.DOCUMENT_POSITION_FOLLOWING); }""")
    assert order, "the note is not above the options list"
    shot(page, "01-chiller-note-under-body-options", journey=JOURNEY)

    _pick(page, ids["chill2"])                                            # another body of the family (flat panel)
    expect(page.locator("#body-rule-note-text")).to_have_text(NOTE_C, timeout=T)

    _pick(page, ids["freeze"])                                            # the note changes with the body
    expect(page.locator("#body-rule-note-text")).to_have_text(NOTE_F, timeout=T)
    assert page.eval_on_selector("#body-rule-note-text", "e => e.textContent") == NOTE_F
    lines = page.eval_on_selector("#body-rule-note-text", "e => e.innerText.split('\\n').length")
    assert lines == 2, "a two-line note keeps its lines"
    shot(page, "02-freezer-note-two-lines", journey=JOURNEY)

    _pick(page, ids["plain"])                                             # a family with no note
    expect(_note(page)).to_be_hidden(timeout=T)
    shot(page, "03-no-note-on-a-plain-body", journey=JOURNEY)


# ── 2 ─────────────────────────────────────────────────────────────────────────

def _editor_save(page: Page, gid: int, text: str) -> None:
    page.goto("/admin/quote-templates?skin=mes")
    row = page.locator("tr", has=page.locator(f"form[data-family-id='{gid}']"))
    box = row.locator("textarea[name='rule_note']")
    expect(box).to_be_visible(timeout=T)
    box.fill(text)
    with page.expect_navigation(timeout=T):
        row.locator("button[type='submit']").click()


def test_an_admin_edit_shows_as_typed_on_the_calculator_and_in_body_templates(
        page: Page, live_server: str, staged) -> None:
    ids, gid = staged, staged["fam"]["chill"]
    admin_session(page, base=live_server)
    _editor_save(page, gid, XSS)
    assert _db_note(gid) == XSS                                           # the read-back (RT5_RULING_0)

    _open_calculator(page)
    _pick(page, ids["chill"])
    expect(page.locator("#body-rule-note-text")).to_have_text(XSS, timeout=T)
    assert page.eval_on_selector("#body-rule-note", "e => e.querySelectorAll('b, img').length") == 0
    assert page.evaluate("() => window.__rt5") is None, "the note's markup ran"
    shot(page, "04-html-note-shows-as-text", journey=JOURNEY)

    page.goto("/admin/templates?skin=mes")
    page.locator(f"#tt-{ids['chill']}").first.click()
    expect(page.locator("#tt-rule-note")).to_be_visible(timeout=T)
    expect(page.locator("#tt-rule-note-text")).to_have_text(XSS)
    assert page.eval_on_selector("#tt-rule-note", "e => e.querySelectorAll('b, img').length") == 0
    assert page.eval_on_selector("#tt-rule-note", "e => getComputedStyle(e).color") == RED
    shot(page, "05-body-templates-note-under-the-header", journey=JOURNEY)

    _editor_save(page, gid, NOTE_C)                                       # set it back ...
    assert _db_note(gid) == NOTE_C                                        # ... and read it back
    page.goto("/admin/templates?skin=mes")
    page.locator(f"#tt-{ids['freeze']}").first.click()
    expect(page.locator("#tt-rule-note-text")).to_have_text(NOTE_F, timeout=T)
    page.locator(f"#tt-{ids['plain']}").first.click()
    expect(page.locator("#tt-rule-note")).to_be_hidden(timeout=T)


# ── 3 ─────────────────────────────────────────────────────────────────────────

def _foam(page: Page):
    return page.locator("#insulation-foam-block")


def _save(page: Page, ids) -> int:
    page.fill("#f-margin", "0")
    page.select_option("#cust-select", value=str(ids["customer"]))
    expect(page.locator("#approve-btn")).to_be_enabled(timeout=T)
    page.click("#approve-btn")
    for _ in range(int(T / 250)):
        page.wait_for_timeout(250)
        rec = page.evaluate("() => (typeof lastRecordId !== 'undefined') ? lastRecordId : null")
        if rec:
            return rec
    raise AssertionError("the costing did not save")


def test_the_foam_picker_hides_only_when_no_pu_is_offered_or_selected(page: Page, live_server: str, staged) -> None:
    from app.database import ConfiguratorDraft, SessionLocal
    ids = staged
    pu_on = lambda req: (req.get("body_option_selections") or {}).get(str(ids["chill_pu"])) is True  # noqa: E731
    pu_off = lambda req: not (req.get("body_option_selections") or {}).get(str(ids["chill_pu"]))  # noqa: E731
    admin_session(page, base=live_server)

    # (a) before the removal: the chiller's draft offers PU — a quote is saved with PU on it
    _open_calculator(page)
    _pick(page, ids["chill"])
    _calc(page, lambda: page.locator(f"#body-options-list [data-draft-flag-mids='{ids['chill_pu']}']").check(),
          ids["chill"], pu_on)
    expect(_foam(page)).to_be_visible(timeout=T)
    rec_id = _save(page, ids)

    # (b) the removal (Michael's Settings-page edit on prod): the draft offers EPS only
    with SessionLocal() as db:
        d = db.query(ConfiguratorDraft).filter_by(trailer_type_id=ids["chill"]).first()
        d.payload = json.dumps(_draft(ids["chill_eps"], ids["chill_pu"], 1, False))
        db.commit()

    # (c) a new chiller quote: no PU offered, none selected -> the picker is HIDDEN
    _open_calculator(page)
    hidden_req = _pick(page, ids["chill"], pu_off)
    expect(page.locator(f"#body-options-list [data-draft-flag-mids='{ids['chill_pu']}']")).to_have_count(0)
    expect(_foam(page)).to_be_hidden(timeout=T)
    expect(_note(page)).to_be_visible()
    shot(page, "06-chiller-note-and-no-foam-picker", journey=JOURNEY)

    # ... and the payload is IDENTICAL with the picker shown (the rule bypassed in this page only)
    shown_req = _calc(page, lambda: page.evaluate(
        "() => { window._puInsulationOffered = () => true; renderInsulationFoam(bomData); runCalc(); }"),
        ids["chill"], pu_off)
    expect(_foam(page)).to_be_visible(timeout=T)
    assert shown_req == hidden_req, "the hidden picker changed what the quote sends"
    assert hidden_req.get("insulation_foam") == "32D"

    # (d) a freezer-shaped body that offers PU: SHOWN
    _open_calculator(page)
    _pick(page, ids["freeze"])
    expect(_foam(page)).to_be_visible(timeout=T)
    shot(page, "07-freezer-note-and-foam-picker", journey=JOURNEY)

    # (e) the chiller costing saved with PU, re-opened after the removal: SHOWN (PU is selected on it)
    page.goto("/mes/calculator?stay=1")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    _calc(page, lambda: page.goto(f"/mes/calculator?stay=1&edit={rec_id}"), ids["chill"], pu_on)
    expect(_foam(page)).to_be_visible(timeout=T)
    expect(_note(page)).to_be_visible()
    shot(page, "08-reopened-chiller-costing-with-pu-shows-the-picker", journey=JOURNEY)
    time.sleep(0.2)
