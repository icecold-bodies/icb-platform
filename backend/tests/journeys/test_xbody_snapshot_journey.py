"""v1.53 — cross-body Explorer snapshot restore, driven through the real UI.

Flow under test (the whole reason the feature exists): a known-good config
captured on body A becomes body B's starting point, with the BOM-reference
audit shown BEFORE anything is written. The journey stages two similar bodies
(shared option + section, plus an A-only option and an A-only section), a
snapshot on A, then on B's Settings page: Snapshots modal → pick A as source →
"Audit & restore…" → the audit must show the remap/unbound/dropped buckets and
the never-carried item-rules note → confirm → B's Explorer shows A's tree with
B-local bindings, and the DB holds the remapped draft + the auto-backup.

Marker JXBJ; purge at setup AND teardown; admin_session gets base=live_server.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "xbody_snapshot"
MARK = "JXBJ"


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
        BOMSection, BillOfMaterial, ConfiguratorDraftSnapshot, Material,
        SessionLocal, TrailerType,
    )
    with SessionLocal() as db:
        _purge(db)
        src = TrailerType(name=f"{MARK} SOURCE BODY", is_active=True)
        tgt = TrailerType(name=f"{MARK} TARGET BODY", is_active=True)
        sec_shared = BOMSection(name=f"{MARK} SIDES", sort_order=9301)
        sec_only_a = BOMSection(name=f"{MARK} ONLY A SEC", sort_order=9302)
        m_opt_shared = Material(name=f"{MARK} OPT SHARED", unit_of_measure="each", price_per_unit=1.0)
        m_opt_only_a = Material(name=f"{MARK} OPT ONLY A", unit_of_measure="each", price_per_unit=1.0)
        m_item = Material(name=f"{MARK} PANEL ITEM", unit_of_measure="each", price_per_unit=2.0)
        db.add_all([src, tgt, sec_shared, sec_only_a, m_opt_shared, m_opt_only_a, m_item])
        db.flush()

        def bom(trailer, material, section=None, master=False, sort=0):
            row = BillOfMaterial(
                trailer_type_id=trailer.id, material_id=material.id,
                formula_expression="1", sort_order=sort,
                is_body_option=master,
                bom_section=(section.name if section else ("BODY OPTIONS" if master else None)),
                bom_section_id=(section.id if section else None),
            )
            db.add(row)
            return row

        a_master_shared = bom(src, m_opt_shared, master=True, sort=1)
        a_master_only = bom(src, m_opt_only_a, master=True, sort=2)
        a_item = bom(src, m_item, section=sec_shared, sort=3)
        bom(src, m_item, section=sec_only_a, sort=4)

        b_master_shared = bom(tgt, m_opt_shared, master=True, sort=1)
        bom(tgt, m_item, section=sec_shared, sort=2)
        db.flush()

        snap_payload = {
            "nextId": 9,
            "rootIds": ["1", "2"],
            "nodes": {
                "1": {"id": "1", "type": "category", "label": f"{MARK} SIDES",
                      "sourceCategoryKey": f"{MARK} SIDES", "parentId": None,
                      "childIds": ["3", "4"]},
                "2": {"id": "2", "type": "category", "label": "GONE ON TARGET",
                      "sourceCategoryKey": f"{MARK} ONLY A SEC", "parentId": None,
                      "childIds": []},
                "3": {"id": "3", "type": "flag", "label": f"{MARK} OPT SHARED",
                      "flagMode": "tickbox", "flagValue": 1, "parentId": "1", "childIds": [],
                      "flagBindingName": f"{MARK} OPT SHARED",
                      "flagBindingId": a_master_shared.id},
                "4": {"id": "4", "type": "flag", "label": f"{MARK} OPT ONLY A",
                      "flagMode": "tickbox", "flagValue": 0, "parentId": "1", "childIds": [],
                      "flagBindingName": f"{MARK} OPT ONLY A",
                      "flagBindingId": a_master_only.id},
            },
            "itemRules": {
                str(a_item.id): {"mode": "include",
                                 "conditions": [{"option": f"{MARK} OPT SHARED", "equals": "Y"}]},
            },
        }
        snap = ConfiguratorDraftSnapshot(
            trailer_type_id=src.id, label=f"{MARK} golden config",
            payload=json.dumps(snap_payload), created_by="admin")
        db.add(snap)
        db.commit()
        ids = {"src_id": src.id, "tgt_id": tgt.id, "snap_id": snap.id,
               "b_master_shared": b_master_shared.id}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def test_cross_body_restore_via_audit_modal(page: Page, live_server: str, staged) -> None:
    admin_session(page, base=live_server)
    page.goto("/admin/settings")

    body_select = page.locator("select").first
    expect(body_select).to_be_visible(timeout=30_000)
    body_select.select_option(str(staged["tgt_id"]))
    # Categories for the TARGET must be live before restoring (the client-side
    # ghost-strip keys off them), and this also proves the page loaded B.
    expect(page.get_by_text(f"{MARK} SIDES").first).to_be_visible(timeout=30_000)

    # Open the snapshots modal → the cross-body section is there.
    page.locator("button[title^='Snapshots']").click()
    expect(page.get_by_text("Restore from another body type")).to_be_visible(timeout=T)
    shot(page, "01-snapshots-modal-with-xbody-section", journey=JOURNEY)

    # Pick the SOURCE body → its snapshot list loads.
    modal_select = page.locator(".vs-modal select")
    modal_select.select_option(str(staged["src_id"]))
    expect(page.get_by_text(f"{MARK} golden config")).to_be_visible(timeout=T)

    # Audit before restore — every bucket the feature promises.
    page.get_by_title("Audit this snapshot against the current body, then restore it here").click()
    expect(page.get_by_text("Cross-body restore audit")).to_be_visible(timeout=T)
    expect(page.get_by_text("remaps to this body's \"" + f"{MARK} OPT SHARED" + "\"")).to_be_visible()
    expect(page.get_by_text(f'no option named "{MARK} OPT ONLY A" here')).to_be_visible()
    expect(page.get_by_text(f'no "{MARK} ONLY A SEC" section here')).to_be_visible()
    expect(page.get_by_text("never carried across")).to_be_visible()
    shot(page, "02-audit-buckets", journey=JOURNEY)

    # Restore → the in-page danger confirm names source AND target.
    page.get_by_text(f"↺ Restore onto {MARK} TARGET BODY").click()
    expect(page.locator("#modal-confirm")).to_be_visible(timeout=T)
    expect(page.locator("#confirm-message")).to_contain_text(f"{MARK} SOURCE BODY")
    expect(page.locator("#confirm-message")).to_contain_text(f"{MARK} TARGET BODY")
    shot(page, "03-danger-confirm", journey=JOURNEY)
    page.locator("#confirm-ok").click()

    # Post-restore: modals gone, notice up, and the Explorer tree shows A's
    # structure minus the section B doesn't have.
    expect(page.locator("#modal-confirm")).to_be_hidden(timeout=T)
    expect(page.get_by_text(f'Restored "{MARK} golden config" from {MARK} SOURCE BODY')).to_be_visible(timeout=T)
    expect(page.get_by_text(f"{MARK} OPT SHARED").first).to_be_visible(timeout=T)
    expect(page.get_by_text(f"{MARK} OPT ONLY A").first).to_be_visible()
    expect(page.get_by_text("GONE ON TARGET")).to_have_count(0)
    shot(page, "04-restored-tree-on-target", journey=JOURNEY)

    # DB truth: the target's draft is the REMAPPED tree (B-local binding id,
    # no carried item rules) and the auto-backup landed on the TARGET.
    from app.database import ConfiguratorDraft, ConfiguratorDraftSnapshot, SessionLocal
    with SessionLocal() as db:
        draft_row = db.query(ConfiguratorDraft).filter_by(trailer_type_id=staged["tgt_id"]).first()
        assert draft_row is not None
        stored = json.loads(draft_row.payload)
        assert stored["nodes"]["3"]["flagBindingId"] == staged["b_master_shared"]
        assert stored["nodes"]["4"]["flagBindingId"] is None
        assert "2" not in stored["nodes"] and stored["rootIds"] == ["1"]
        assert stored["itemRules"] == {}
        backup = (db.query(ConfiguratorDraftSnapshot)
                  .filter_by(trailer_type_id=staged["tgt_id"])
                  .order_by(ConfiguratorDraftSnapshot.id.desc()).first())
        assert backup is not None and "cross-body" in backup.label
