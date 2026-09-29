"""v1.59.1 Part A — a section whose rules switch every line off reads NOT SELECTED.

Michael (28 Sep): when a rule switches a whole section off (the SRD rear-frame rule is
the first), its header must not read R0.00 — sales users would wonder why a section is
free. The header says NOT SELECTED. Decided by mechanism, not by section name.

Fixture body (configurator v2, no dependency on the rear-frame data lane):
  * RULED  — two lines, each ruled ``SWITCH = Y``; SWITCH is off -> every line out
  * MIXED  — one ruled line + one plain line -> keeps its real subtotal

  1. RULED's header reads NOT SELECTED (muted, with the plain-English tooltip), and
     no R0.00; MIXED's header shows its subtotal. The money on the wire is untouched:
     RULED has no category total, MIXED's is its plain line.
  2. The eye shows the 2 hidden lines; toggled on, they render struck through.
  3. SWITCH on -> RULED shows its subtotal and the label is gone.

Assertions ride the DOM and the real /api/calculate wire (CSP forbids page-JS
evaluation in journeys). Marker JNS9; purge at setup AND teardown; base-aware.
"""
from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "section_not_selected"
MARK = "JNS9"
RULED = f"{MARK} RULED"
MIXED = f"{MARK} MIXED"
SWITCH = f"{MARK} SWITCH"
TIP = "Nothing in this section is costed with the options chosen. Click the eye to see the lines."


def _purge(db) -> None:
    from sqlalchemy import text
    tt_sub = "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"
    for sql in (
        f"DELETE FROM icb_costings.configurator_drafts WHERE trailer_type_id IN {tt_sub}",
        f"DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN {tt_sub}",
        "DELETE FROM icb_costings.materials WHERE name LIKE :m",
        "DELETE FROM icb_costings.bom_sections WHERE name LIKE :m",
        "DELETE FROM icb_costings.trailer_types WHERE name LIKE :m",
    ):
        db.execute(text(sql), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    from app.database import (
        BillOfMaterial, BOMSection, ConfiguratorDraft, Material, SessionLocal, TrailerType,
    )
    with SessionLocal() as db:
        _purge(db)
        tt = TrailerType(name=f"{MARK} BODY", is_active=True, configurator_v2=True,
                         default_length=4.0, default_width=2.0, default_height=2.0)
        s_ruled = BOMSection(name=RULED, sort_order=9501)
        s_mixed = BOMSection(name=MIXED, sort_order=9502)
        m_switch = Material(name=SWITCH, unit_of_measure="each", price_per_unit=0.0)
        m_a = Material(name=f"{MARK} RAIL", unit_of_measure="each", price_per_unit=100.0)
        m_b = Material(name=f"{MARK} PLATE", unit_of_measure="each", price_per_unit=50.0)
        m_c = Material(name=f"{MARK} BOLT", unit_of_measure="each", price_per_unit=25.0)
        db.add_all([tt, s_ruled, s_mixed, m_switch, m_a, m_b, m_c])
        db.flush()
        switch = BillOfMaterial(trailer_type_id=tt.id, material_id=m_switch.id,
                                formula_expression="1", is_body_option=True,
                                body_option_group=f"{MARK} GROUP", body_option_default=False,
                                bom_section="BODY OPTIONS")
        db.add(switch)
        db.flush()
        rule = json.dumps([{"option": SWITCH, "equals": "Y", "option_id": switch.id}])

        def line(m, sec, conditions=None, sort=0):
            r = BillOfMaterial(trailer_type_id=tt.id, material_id=m.id, formula_expression="1",
                               bom_section=sec.name, bom_section_id=sec.id,
                               bom_conditions=conditions, sort_order=sort)
            db.add(r)
            db.flush()
            return r.id

        ids = {"tt": tt.id, "switch": switch.id,
               "ruled_a": line(m_a, s_ruled, rule, 1), "ruled_b": line(m_b, s_ruled, rule, 2),
               "mixed_ruled": line(m_a, s_mixed, rule, 3), "mixed_plain": line(m_c, s_mixed, None, 4)}
        db.add(ConfiguratorDraft(trailer_type_id=tt.id, payload=json.dumps({
            "nextId": 4, "rootIds": ["1", "3"], "itemRules": {}, "nodes": {
                "1": {"id": "1", "type": "category", "label": RULED, "sourceCategoryKey": RULED,
                      "parentId": None, "childIds": ["2"]},
                "2": {"id": "2", "type": "flag", "label": SWITCH, "parentId": "1", "childIds": [],
                      "flagMode": "tickbox", "flagValue": 0, "flagBindingName": SWITCH,
                      "flagBindingId": switch.id},
                "3": {"id": "3", "type": "category", "label": MIXED, "sourceCategoryKey": MIXED,
                      "parentId": None, "childIds": []},
            }})))
        db.commit()
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _is_calc(resp) -> bool:
    return resp.request.method == "POST" and resp.url.split("?")[0].endswith("/api/calculate")


def _hdr(page: Page, section: str):
    return page.locator(f"tr.calc-grp-hdr[data-cat-name='{section}']").first


def test_all_ruled_out_section_reads_not_selected(page: Page, live_server: str, staged) -> None:
    admin_session(page, base=live_server)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    with page.expect_response(_is_calc, timeout=30_000) as calc:
        page.select_option("#trailer-select", str(staged["tt"]))
    res = calc.value.json()

    # The money is untouched: the ruled-out section has no total (it never had
    # one), MIXED carries its plain line only, and every ruled line is excluded
    # BY A CONDITION.
    assert RULED not in res["category_totals"]
    assert res["category_totals"][MIXED] == pytest.approx(25.0)
    by_id = {i["bom_id"]: i for i in res["items"]}
    for k in ("ruled_a", "ruled_b", "mixed_ruled"):
        assert by_id[staged[k]]["excluded"] is True
        assert by_id[staged[k]]["excluded_by"] == "condition"
    assert "excluded_by" not in by_id[staged["mixed_plain"]]

    # 1. Header: NOT SELECTED in place of R0.00; MIXED keeps its subtotal.
    ruled = _hdr(page, RULED)
    expect(ruled).to_be_visible(timeout=T)
    label = ruled.locator(".calc-hdr-not-selected")
    expect(label).to_have_text("NOT SELECTED")
    expect(label).to_have_attribute("title", TIP)
    expect(ruled.locator(".calc-hdr-sub")).to_have_text("")
    expect(ruled).not_to_contain_text(re.compile(r"0[.,]00"))   # en-ZA: "R 0,00"
    mixed = _hdr(page, MIXED)
    expect(mixed.locator(".calc-hdr-not-selected")).to_have_count(0)
    expect(mixed.locator(".calc-hdr-sub")).to_contain_text(re.compile(r"25[.,]00"))
    shot(page, "01-not-selected-header", journey=JOURNEY)

    # 2. The eye still shows the hidden lines, struck through. Expand first
    # (collapsed sections hide every row), then switch the eye on.
    ruled.click()
    expect(page.locator(f"tr.calc-grp-row[data-bom-id='{staged['ruled_a']}']")).to_have_count(0)
    eye = ruled.locator("span[title='Show 2 excluded lines']")
    expect(eye).to_be_visible()
    eye.click()
    ruled = _hdr(page, RULED)
    expect(ruled.locator(".calc-hdr-not-selected")).to_have_text("NOT SELECTED")
    for k in ("ruled_a", "ruled_b"):
        row = page.locator(f"tr.calc-grp-row.bom-excluded-row[data-bom-id='{staged[k]}']")
        expect(row).to_be_visible(timeout=T)
        expect(row).to_have_css("text-decoration-line", "line-through")
    shot(page, "02-eye-shows-struck-through-lines", journey=JOURNEY)

    # 3. Switch the flag on -> the section is costed again and shows its subtotal.
    flag = page.locator(f"input[data-draft-flag-mids='{staged['switch']}'][data-draft-flag-name='{SWITCH}']")
    expect(flag).to_be_attached(timeout=T)
    with page.expect_response(
            lambda r: _is_calc(r) and RULED in (r.json().get("category_totals") or {}),
            timeout=30_000) as calc_on:
        flag.check()
    assert calc_on.value.json()["category_totals"][RULED] == pytest.approx(150.0)
    ruled = _hdr(page, RULED)
    expect(ruled.locator(".calc-hdr-not-selected")).to_have_count(0, timeout=T)
    if "collapsed" not in (ruled.get_attribute("class") or ""):
        ruled.click()
    expect(ruled.locator(".calc-hdr-sub")).to_contain_text(re.compile(r"150[.,]00"))
    shot(page, "03-switched-on-shows-subtotal", journey=JOURNEY)
