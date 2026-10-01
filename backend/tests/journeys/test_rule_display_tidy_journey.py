"""v1.59.2 (BA ruling 7a) — rule chips read the database; rule-excluded lines read plain English.

A. Admin -> Trailer Designer: a line's rule chips show the DATABASE rule (what the
   engine prices), never the draft's itemRules copy. A copy that disagrees raises a
   "draft differs" marker; a condition from outside the branch reads "kept", as the
   v1.59.1 rule editor shows it.
B. Calculator: a line a RULE switched off reads plain English on its struck-through
   badge ("not used with SRD PU"); the engine's words stay in the tooltip and in the
   API (excluded_reason unchanged).

Fixture body (configurator v2) mirroring FREEZER MEDIUM on dev (30 Sep): a ROOT
REAR FRAME & FLOOR PLATE category whose lines carry the Manifest A rule
``SRD EPS = N`` AND ``SRD PU = N`` (both flags live under DOOR TYPE, so both are out of
branch), DRD / SRD door folders with EPS/PU insulation masters, and the original door
DRD with PU 0.06 m. One REAR FRAME line has a stale draft copy — the v1.59.1 defect's
signature (``FRONT EPS = N``). A journey cannot use dev's real FREEZER MEDIUM: pytest
refuses any database not named *_test (db_guard), and the test DB holds no bodies.

Door trap (gone in RT2 Part 1): a door switch used to REWRITE the body template's
rear-door thickness (the carry). It now moves the thickness on the quote only — the
journey checks the quote's body_variables after each switch and the template in the DB.

Marker JRD7; purge at setup AND teardown; admin_session gets base=live_server.
"""
from __future__ import annotations

import json
import re
import time

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "rule_display_tidy"
MARK = "JRD7"
RF = f"{MARK} REAR FRAME & FLOOR PLATE"
# The door sections carry their REAL names: the calculator ties the rear-door gate
# (drdSrdEnabled, which the load-time door invariant trusts) to draft categories
# keyed exactly DRD / SRD. Sections are global and unique by name, so the fixture
# gets-or-creates them and deletes only what it created (never by natural key).
SRD_SEC = "SRD"
DRD_SEC = "DRD"
KEPT_NOTE = ("This condition uses a flag from another part of the tree. It still applies; "
             "edit it with the tool or ask the administrator.")
ORIGINAL_DOOR = {"drd_eps": 0.0, "drd_pu": 0.06, "srd_eps": 0.0, "srd_pu": 0.0}


def _purge(db) -> None:
    from sqlalchemy import text
    tt_sub = "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"
    for sql in (
        f"DELETE FROM icb_costings.configurator_draft_snapshots WHERE trailer_type_id IN {tt_sub}",
        f"DELETE FROM icb_costings.configurator_drafts WHERE trailer_type_id IN {tt_sub}",
        f"DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN {tt_sub}",
        "DELETE FROM icb_costings.materials WHERE name LIKE :m",
        "DELETE FROM icb_costings.bom_sections WHERE name LIKE :m",
        "DELETE FROM icb_costings.trailer_types WHERE name LIKE :m",
    ):
        db.execute(text(sql), {"m": f"{MARK}%"})
    db.commit()


def _drop_created_sections(db, created: list) -> None:
    """Delete the door sections THIS fixture created, and only while nothing else
    uses them — a pre-existing DRD / SRD is never touched."""
    from sqlalchemy import text
    for sid in created:
        db.execute(text(
            "DELETE FROM icb_costings.bom_sections s WHERE s.id = :i AND NOT EXISTS "
            "(SELECT 1 FROM icb_costings.bill_of_materials b WHERE b.bom_section_id = s.id)"),
            {"i": sid})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    from sqlalchemy import func
    from app.database import (
        BillOfMaterial, BOMSection, ConfiguratorDraft, Material, SessionLocal, TrailerType,
    )
    created: list[int] = []
    with SessionLocal() as db:
        _purge(db)
        body = TrailerType(name=f"{MARK} BODY", is_active=True, configurator_v2=True,
                           default_length=5.0, default_width=2.4, default_height=2.4)
        db.add(body)

        def section(name, sort_order):
            s = db.query(BOMSection).filter(func.upper(BOMSection.name) == name.upper()).first()
            if s is None:
                s = BOMSection(name=name, sort_order=sort_order)
                db.add(s)
                db.flush()
                if name != RF:
                    created.append(s.id)
            return s

        secs = {name: section(name, 9700 + i) for i, name in enumerate((RF, SRD_SEC, DRD_SEC))}
        db.flush()

        def mat(name, price=0.0):
            m = Material(name=f"{MARK} {name}", unit_of_measure="each", price_per_unit=price)
            db.add(m)
            db.flush()
            return m

        def bom(m, sec=None, conditions=None, sort=0, **master):
            r = BillOfMaterial(trailer_type_id=body.id, material_id=m.id, formula_expression="1",
                               sort_order=sort, is_body_option=bool(master),
                               bom_section=(sec.name if sec else "BODY OPTIONS"),
                               bom_section_id=(sec.id if sec else None),
                               bom_conditions=conditions, **master)
            db.add(r)
            db.flush()
            return r

        def master(name, group, default, var):
            return bom(mat(name), body_option_group=group, body_option_subgroup="INSULATION",
                       body_option_default=default, variable_value=var)

        drd_eps = master("DRD EPS", "DRD", False, 0.0)
        drd_pu = master("DRD PU", "DRD", True, 0.06)           # the original door: DRD, PU
        srd_eps = master("SRD EPS", "SRD", False, 0.0)
        srd_pu = master("SRD PU", "SRD", False, 0.0)
        rf_rule = json.dumps([
            {"option": f"{MARK} SRD EPS", "equals": "N", "option_id": srd_eps.id},
            {"option": f"{MARK} SRD PU", "equals": "N", "option_id": srd_pu.id}])
        rail = bom(mat("FRAME RAIL", 100.0), secs[RF], rf_rule, 1)
        plate = bom(mat("FLOOR PLATE", 50.0), secs[RF], rf_rule, 2)
        srd_hinge = bom(mat("SRD HINGE", 30.0), secs[SRD_SEC],
                        json.dumps([{"option": f"{MARK} SRD PU", "equals": "Y"}]), 3)
        # The door's insulation-side lines, as on FREEZER MEDIUM's DRD section: on a
        # PU quote the EPS line is out ("needs DRD EPS"). A door folder that is OFF
        # never reaches the engine at all (the page sends it as excluded_categories).
        bom(mat("DRD PU LINER", 20.0), secs[DRD_SEC],
            json.dumps([{"option": f"{MARK} DRD PU", "equals": "Y"}]), 4)
        drd_eps_liner = bom(mat("DRD EPS LINER", 25.0), secs[DRD_SEC],
                            json.dumps([{"option": f"{MARK} DRD EPS", "equals": "Y"}]), 5)

        def flag(nid, parent, m, on):
            return {"id": nid, "type": "flag", "label": m.material.name, "parentId": parent,
                    "childIds": [], "flagMode": "radio", "flagValue": 1 if on else 0,
                    "flagBindingName": m.material.name, "flagBindingId": m.id}

        draft = {
            "nextId": 11, "rootIds": ["1", "2"],
            "nodes": {
                "1": {"id": "1", "type": "category", "label": RF, "sourceCategoryKey": RF,
                      "parentId": None, "childIds": []},
                "2": {"id": "2", "type": "folder", "label": f"{MARK} DOOR TYPE",
                      "folderMode": "container", "parentId": None, "childIds": ["3", "7"]},
                "3": {"id": "3", "type": "folder", "label": f"{MARK} DRD DOORS",
                      "folderMode": "radio", "folderValue": 1, "parentId": "2", "childIds": ["4"]},
                "4": {"id": "4", "type": "category", "label": DRD_SEC, "sourceCategoryKey": DRD_SEC,
                      "parentId": "3", "childIds": ["5", "6"]},
                "5": flag("5", "4", drd_eps, False),
                "6": flag("6", "4", drd_pu, True),
                "7": {"id": "7", "type": "folder", "label": f"{MARK} SRD DOORS",
                      "folderMode": "radio", "folderValue": 0, "parentId": "2", "childIds": ["8"]},
                "8": {"id": "8", "type": "category", "label": SRD_SEC, "sourceCategoryKey": SRD_SEC,
                      "parentId": "7", "childIds": ["9", "10"]},
                "9": flag("9", "8", srd_eps, False),
                "10": flag("10", "8", srd_pu, True),
            },
            # The v1.59.1 defect's signature: an old editor Save swapped the rule for
            # the first flag on offer and only the DRAFT kept that copy.
            "itemRules": {str(plate.id): {"mode": "include", "conditions": [
                {"option": f"{MARK} FRONT EPS", "equals": "N"}]}},
        }
        db.add(ConfiguratorDraft(trailer_type_id=body.id, payload=json.dumps(draft)))
        db.commit()
        ids = {"body": body.id, "rail": rail.id, "plate": plate.id, "srd_hinge": srd_hinge.id,
               "drd_eps_liner": drd_eps_liner.id,
               "drd_eps": drd_eps.id, "drd_pu": drd_pu.id, "srd_eps": srd_eps.id,
               "srd_pu": srd_pu.id, "rf_rule": rf_rule}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)
        _drop_created_sections(db, created)


def _door(ids) -> dict:
    """The body template's rear-door insulation thicknesses, from the DB."""
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:
        return {k: round(float(db.get(BillOfMaterial, ids[k]).variable_value or 0), 4)
                for k in ORIGINAL_DOOR}


def _stored(item_id: int) -> str | None:
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:
        return db.get(BillOfMaterial, item_id).bom_conditions


# ── A. Trailer Designer ─────────────────────────────────────────────────────────

def _row(page: Page, scope, row_cls: str, name_cls: str, name: str):
    """A catalog / preview row found by its item NAME (the base template has no
    data-item-id, and the negative control must reach the chips to fail on them)."""
    return scope.locator(row_cls).filter(
        has=page.locator(name_cls, has_text=re.compile(rf"^{re.escape(name)}$")))


def _card(page: Page, section: str):
    # Match the card TITLE exactly: an expanded REAR FRAME card's kept chips also
    # contain the text "JRD7 SRD", so a plain has_text would pick the wrong card.
    title = page.locator(".vs-catalog-title", has_text=re.compile(rf"^{re.escape(section)}$"))
    card = page.locator(".vs-catalog-card").filter(has=title)
    expect(card).to_be_visible(timeout=30_000)
    if card.locator(".vs-catalog-items").count() == 0:
        card.locator(".vs-catalog-toggle").click()
    return card


def test_designer_chips_show_the_database_rule(page: Page, live_server: str, staged) -> None:
    admin_session(page, base=live_server)
    page.goto("/admin/settings")
    body_select = page.locator("select").first
    expect(body_select).to_be_visible(timeout=30_000)
    body_select.select_option(str(staged["body"]))
    card = _card(page, RF)

    # The line whose DRAFT copy differs: the chips show the database rule, and a
    # marker names the draft's copy. Checked FIRST so a regression fails naming the
    # draft's chip ("when JRD7 FRONT EPS = N") rather than a missing marker.
    plate = _row(page, card, ".vs-catalog-item", ".vs-catalog-item-name", f"{MARK} FLOOR PLATE")
    expect(plate.locator(".vs-rule-chip").first).to_be_visible(timeout=T)
    chips = plate.locator(".vs-rule-chip").all_inner_texts()
    assert f"when {MARK} FRONT EPS = N" not in chips, f"the chip shows the draft's copy: {chips}"
    kept = plate.locator(".vs-rule-chip.kept")
    expect(kept).to_have_count(2)
    expect(kept.nth(0)).to_have_text(f"when {MARK} SRD EPS = N · kept")
    expect(kept.nth(1)).to_have_text(f"when {MARK} SRD PU = N · kept")
    # The tooltip carries the rule editor's own words.
    expect(kept.nth(1)).to_have_attribute(
        "title", f"{MARK} SRD PU is not selected — kept (outside this branch). {KEPT_NOTE}")
    marker = plate.locator(".vs-rule-chip.draft-differs")
    expect(marker).to_have_text("draft differs")
    expect(marker).to_have_attribute("title", re.compile(
        rf"different copy of this rule \(when {MARK} FRONT EPS = N\).*from the database"))

    # The line with NO draft copy: the same database rule, no marker.
    rail = _row(page, card, ".vs-catalog-item", ".vs-catalog-item-name", f"{MARK} FRAME RAIL")
    expect(rail.locator(".vs-rule-chip.kept")).to_have_count(2)
    expect(rail.locator(".vs-rule-chip.draft-differs")).to_have_count(0)
    shot(page, "01-designer-rear-frame-chips", journey=JOURNEY)

    # An IN-branch condition keeps its ordinary chip (SRD PU is offered in SRD's
    # branch). The catalog is an accordion: this collapses the REAR FRAME card.
    hinge = _row(page, _card(page, SRD_SEC), ".vs-catalog-item", ".vs-catalog-item-name",
                 f"{MARK} SRD HINGE")
    expect(hinge.locator(".vs-rule-chip")).to_have_text([f"when {MARK} SRD PU = Y"])
    expect(hinge.locator(".vs-rule-chip.kept")).to_have_count(0)

    # The config preview reads the same way.
    page.get_by_title("Toggle config structure preview").click()
    pv = _row(page, page, ".vs-cp-item", ".vs-cp-item-name", f"{MARK} FLOOR PLATE")
    expect(pv).to_be_visible(timeout=T)
    expect(pv.locator(".vs-cp-cond.kept")).to_have_text(
        [f"{MARK} SRD EPS=N · kept", f"{MARK} SRD PU=N · kept"])
    expect(pv.locator(".vs-cp-cond.draft-differs")).to_have_text("draft differs")
    shot(page, "02-config-preview", journey=JOURNEY)

    # Display only: nothing was written.
    assert _stored(staged["plate"]) == staged["rf_rule"]


# ── B. Calculator ───────────────────────────────────────────────────────────────

def _is_calc(resp) -> bool:
    return resp.request.method == "POST" and resp.url.split("?")[0].endswith("/api/calculate")


def _hdr(page: Page, section: str):
    return page.locator(f"tr.calc-grp-hdr[data-cat-name='{section}']").first


def _show_lines(page: Page, section: str, n: int) -> None:
    """Expand via the chevron (never the row centre: it can be the eye), then eye on."""
    hdr = _hdr(page, section)
    expect(hdr).to_be_visible(timeout=T)
    if "collapsed" in (hdr.get_attribute("class") or ""):
        hdr.locator(".grp-chevron").click()
    eye = _hdr(page, section).locator(f"span[title='Show {n} excluded line{'' if n == 1 else 's'}']")
    if eye.count():
        eye.click()


def _switch_door(page: Page, folder_label: str, predicate):
    radio = page.locator("#body-options-list label", has_text=folder_label).locator(
        "input[data-draft-folder]")
    expect(radio).to_be_attached(timeout=T)
    with page.expect_response(lambda r: _is_calc(r) and predicate(r.json()),
                              timeout=30_000) as calc:
        radio.check()
    return calc.value.json()


def test_calculator_badges_read_plain_english(page: Page, live_server: str, staged) -> None:
    ids = staged
    assert _door(ids) == ORIGINAL_DOOR                      # fixture sanity
    admin_session(page, base=live_server)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    with page.expect_response(_is_calc, timeout=30_000) as calc:
        page.select_option("#trailer-select", str(ids["body"]))
    res = calc.value.json()

    # 1. The original door (DRD, PU): REAR FRAME is costed; the door's EPS-side line
    # is out and says what it needs.
    assert res["category_totals"][RF] == pytest.approx(150.0)
    assert res["category_totals"][DRD_SEC] == pytest.approx(20.0)
    by_id = {i["bom_id"]: i for i in res["items"]}
    liner = by_id[ids["drd_eps_liner"]]
    assert liner["excluded_by"] == "condition"
    assert liner["excluded_reason"] == f"{MARK} DRD EPS = Y"     # the API is unchanged
    _show_lines(page, DRD_SEC, 1)
    row = page.locator(f"tr.bom-excluded-row[data-bom-id='{ids['drd_eps_liner']}']")
    # On the row's TEXT first, so a regression fails showing the engine's wording.
    expect(row).to_contain_text(f"needs {MARK} DRD EPS", timeout=T)
    badge = row.locator(".bom-rule-out")
    expect(badge).to_have_text(f"needs {MARK} DRD EPS")
    expect(badge).to_have_attribute("title", f"Rule: {MARK} DRD EPS = Y")
    shot(page, "03-drd-quote-needs", journey=JOURNEY)

    # 2. The single rear door: the rule switches REAR FRAME off. The carry moves the
    # door thickness on THIS QUOTE only (RT2 Part 1): the calc's body_variables carry
    # SRD PU 0.06 / DRD PU 0, while the Body Template still holds the original door.
    res = _switch_door(page, f"{MARK} SRD DOORS",
                       lambda j: RF not in (j.get("category_totals") or {}))
    rf_items = [i for i in res["items"] if i["bom_id"] in (ids["rail"], ids["plate"])]
    assert len(rf_items) == 2
    for it in rf_items:
        assert it["excluded_by"] == "condition"
        assert it["excluded_reason"] == f"{MARK} SRD PU = N"   # the engine's words, unchanged
    bv = res.get("body_variables") or {}
    assert (bv.get(f"{MARK} DRD PU"), bv.get(f"{MARK} SRD PU")) == (0.0, 0.06), bv
    time.sleep(1)                                   # any (wrong) write would have landed
    assert _door(ids) == ORIGINAL_DOOR              # the template is untouched
    expect(_hdr(page, RF).locator(".calc-hdr-not-selected")).to_have_text("NOT SELECTED", timeout=T)
    _show_lines(page, RF, 2)
    for k in ("rail", "plate"):
        row = page.locator(f"tr.calc-grp-row.bom-excluded-row[data-bom-id='{ids[k]}']")
        expect(row).to_be_visible(timeout=T)
        expect(row).to_have_css("text-decoration-line", "line-through")
        expect(row).to_contain_text(f"not used with {MARK} SRD PU")
        badge = row.locator(".bom-rule-out")
        expect(badge).to_have_text(f"not used with {MARK} SRD PU")
        expect(badge).to_have_attribute("title", f"Rule: {MARK} SRD PU = N")
        expect(row).not_to_contain_text(f"excluded · {MARK} SRD PU = N")
    shot(page, "04-srd-quote-not-used-with", journey=JOURNEY)

    # 3. Back to the ORIGINAL door: REAR FRAME is costed again, the quote carries DRD PU
    # 0.06 again, and the template's door thickness never moved (checked in the DB).
    res = _switch_door(page, f"{MARK} DRD DOORS",
                       lambda j: RF in (j.get("category_totals") or {}))
    assert res["category_totals"][RF] == pytest.approx(150.0)
    bv = res.get("body_variables") or {}
    assert (bv.get(f"{MARK} DRD PU"), bv.get(f"{MARK} SRD PU")) == (0.06, 0.0), bv
    assert _door(ids) == ORIGINAL_DOOR
    shot(page, "05-back-on-the-original-door", journey=JOURNEY)
