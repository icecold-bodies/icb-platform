"""v1.59.1 Part B — the rule editor keeps a condition whose flag is outside the branch.

The defect (rear-frame lane discovery, 28 Sep): Admin -> Trailer Designer -> a line's
"Edit rules" offers only the flags in that line's category branch. A saved condition
on a flag from elsewhere in the tree (SRD PU on a REAR FRAME line) was REPLACED by the
first flag on offer when the rule was opened and saved.

Staged tree (the real shape on every drafted v2 body): REAR FRAME is a ROOT category
whose own flag is FRONT EPS; SRD PU lives at DOOR TYPE (folder) / SRD (category), so
the REAR FRAME picker cannot offer it. The line's rule is ``SRD PU = N`` only.

  1. Open -> the condition is listed read-only as kept, with the plain-English note;
     no picker row was injected. Save -> bom_conditions byte-identical.
  2. Open -> Add condition (FRONT EPS) -> Save -> both kept, SRD PU first, as stored.
  3. Open -> the kept condition's ✕ asks first; Keep leaves it; ✕ -> Remove drops it
     (the only way it ever goes). Save -> only FRONT EPS remains.

Marker JRE9; purge at setup AND teardown; admin_session gets base=live_server.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "rule_editor_keeps_rules"
MARK = "JRE9"


def _purge(db) -> None:
    from sqlalchemy import text
    tt_sub = "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"
    db.execute(text(
        f"DELETE FROM icb_costings.configurator_draft_snapshots WHERE trailer_type_id IN {tt_sub}"),
        {"m": f"{MARK}%"})
    db.execute(text(
        f"DELETE FROM icb_costings.configurator_drafts WHERE trailer_type_id IN {tt_sub}"),
        {"m": f"{MARK}%"})
    db.execute(text(
        f"DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN {tt_sub}"),
        {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    from app.database import (
        BOMSection, BillOfMaterial, ConfiguratorDraft, Material, SessionLocal, TrailerType,
    )
    with SessionLocal() as db:
        _purge(db)
        body = TrailerType(name=f"{MARK} BODY", is_active=True, configurator_v2=True)
        sec_rf = BOMSection(name=f"{MARK} REAR FRAME", sort_order=9401)
        sec_srd = BOMSection(name=f"{MARK} SRD", sort_order=9402)
        m_srd = Material(name=f"{MARK} SRD PU", unit_of_measure="each", price_per_unit=0.0)
        m_front = Material(name=f"{MARK} FRONT EPS", unit_of_measure="each", price_per_unit=0.0)
        m_rail = Material(name=f"{MARK} FRAME RAIL", unit_of_measure="each", price_per_unit=5.0)
        m_door = Material(name=f"{MARK} DOOR PANEL", unit_of_measure="each", price_per_unit=7.0)
        db.add_all([body, sec_rf, sec_srd, m_srd, m_front, m_rail, m_door])
        db.flush()

        def bom(material, section=None, master=False, conditions=None, sort=0):
            r = BillOfMaterial(
                trailer_type_id=body.id, material_id=material.id, formula_expression="1",
                sort_order=sort, is_body_option=master,
                bom_section=(section.name if section else "BODY OPTIONS"),
                bom_section_id=(section.id if section else None),
                bom_conditions=conditions)
            db.add(r)
            db.flush()
            return r

        srd = bom(m_srd, master=True, sort=1)
        front = bom(m_front, master=True, sort=2)
        rule = json.dumps([{"option": m_srd.name, "equals": "N", "option_id": srd.id}])
        rail = bom(m_rail, section=sec_rf, conditions=rule, sort=3)
        bom(m_door, section=sec_srd, sort=4)

        draft = {
            "nextId": 7,
            "rootIds": ["1", "3"],
            "nodes": {
                "1": {"id": "1", "type": "category", "label": f"{MARK} REAR FRAME",
                      "sourceCategoryKey": f"{MARK} REAR FRAME", "parentId": None,
                      "childIds": ["2"]},
                "2": {"id": "2", "type": "flag", "label": m_front.name, "flagMode": "tickbox",
                      "flagValue": 0, "parentId": "1", "childIds": [],
                      "flagBindingName": m_front.name, "flagBindingId": front.id},
                "3": {"id": "3", "type": "folder", "label": f"{MARK} DOOR TYPE",
                      "folderMode": "radio", "parentId": None, "childIds": ["4"]},
                "4": {"id": "4", "type": "category", "label": f"{MARK} SRD",
                      "sourceCategoryKey": f"{MARK} SRD", "parentId": "3", "childIds": ["5"]},
                "5": {"id": "5", "type": "flag", "label": m_srd.name, "flagMode": "tickbox",
                      "flagValue": 0, "parentId": "4", "childIds": [],
                      "flagBindingName": m_srd.name, "flagBindingId": srd.id},
            },
            "itemRules": {},
        }
        db.add(ConfiguratorDraft(trailer_type_id=body.id, payload=json.dumps(draft)))
        db.commit()
        ids = {"body": body.id, "rail": rail.id, "srd": srd.id, "rule": rule}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _stored(item_id: int) -> str | None:
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:
        return db.get(BillOfMaterial, item_id).bom_conditions


def _open_rule(page: Page) -> None:
    card = page.locator(".vs-catalog-card", has_text=f"{MARK} REAR FRAME")
    if card.locator(".vs-catalog-items").count() == 0:
        card.locator(".vs-catalog-toggle").click()
    row = card.locator(".vs-catalog-item", has_text=f"{MARK} FRAME RAIL")
    row.get_by_role("button", name="Edit rules").click()
    expect(page.locator(".vs-rule-modal")).to_be_visible(timeout=T)


def _save(page: Page) -> None:
    with page.expect_response(lambda r: "/conditions" in r.url and r.request.method == "PATCH") as resp:
        page.locator(".vs-rule-modal").get_by_role("button", name="Save").click()
    assert resp.value.ok, resp.value.text()
    expect(page.locator(".vs-rule-modal")).to_be_hidden(timeout=T)


def test_rule_editor_keeps_out_of_branch_condition(page: Page, live_server: str, staged) -> None:
    admin_session(page, base=live_server)
    page.goto("/admin/settings")
    body_select = page.locator("select").first
    expect(body_select).to_be_visible(timeout=30_000)
    body_select.select_option(str(staged["body"]))
    expect(page.locator(".vs-catalog-card", has_text=f"{MARK} REAR FRAME")).to_be_visible(timeout=30_000)

    # 1. Out-of-branch only: shown as kept, nothing injected, Save is a no-op.
    _open_rule(page)
    modal = page.locator(".vs-rule-modal")
    kept = modal.locator(".vs-rule-row-kept")
    expect(kept).to_have_count(1)
    expect(kept).to_contain_text(f"{MARK} SRD PU is not selected — kept (outside this branch)")
    expect(kept).to_contain_text("This condition uses a flag from another part of the tree.")
    expect(modal).to_contain_text("were kept")
    # No picker row was injected (the old editor put FRONT EPS here).
    expect(modal.locator(".vs-rule-row select")).to_have_count(0)
    shot(page, "01-kept-condition-shown", journey=JOURNEY)
    _save(page)
    after = _stored(staged["rail"])
    assert after == staged["rule"], f"Save rewrote the rule: {after}"

    # 2. Add an in-branch condition: both kept, stored order preserved.
    _open_rule(page)
    modal.get_by_role("button", name="Add condition").click()
    expect(modal.locator(".vs-rule-row select").first).to_have_value(f"{MARK} FRONT EPS")
    shot(page, "02-in-branch-added", journey=JOURNEY)
    _save(page)
    stored = json.loads(_stored(staged["rail"]))
    assert stored[0] == {"option": f"{MARK} SRD PU", "equals": "N", "option_id": staged["srd"]}
    assert [c["option"] for c in stored] == [f"{MARK} SRD PU", f"{MARK} FRONT EPS"]

    # 3. The kept condition goes only by a deliberate, confirmed click.
    _open_rule(page)
    kept = modal.locator(".vs-rule-row-kept")
    kept.locator(".vs-rule-kept-remove").click()
    expect(kept).to_contain_text("Remove it?")
    shot(page, "03-remove-asks-first", journey=JOURNEY)
    kept.get_by_role("button", name="Keep").click()
    expect(modal.locator(".vs-rule-row-kept")).to_have_count(1)
    modal.locator(".vs-rule-row-kept .vs-rule-kept-remove").click()
    modal.locator(".vs-rule-row-kept").get_by_role("button", name="Remove").click()
    expect(modal.locator(".vs-rule-row-kept")).to_have_count(0)
    _save(page)
    stored = json.loads(_stored(staged["rail"]))
    assert [c["option"] for c in stored] == [f"{MARK} FRONT EPS"]
