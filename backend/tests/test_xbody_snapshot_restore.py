"""Cross-body Explorer snapshot restore (v1.53).

A draft snapshot captured on body A seeds body B's Explorer config through a
BOM-reference audit: flag bindings remap by NAME to B's masters, category
nodes whose section doesn't exist on B are dropped with their subtree, and
itemRules are audited (matched by section+item name) but never carried — B's
rows' bom_conditions are untouched.

Endpoints under test:
  GET  /api/configurator/draft-snapshots/{id}/cross-audit?target={tid}  (dry run)
  POST /api/configurator/draft-snapshots/{id}/restore-to/{tid}          (apply)

House pattern (test_bom_section_manage.py): live test DB, marker rows
'JXBDY*', module-local fixtures, purge on both sides, real UserSession row +
raw Cookie header ([[testclient-session-cookie]]).
"""
import json

import pytest

_MARK = "JXBDY"
_GHOST_RULE_ID = "999999999"  # never a real bill_of_materials id in the fixture


def _purge(db) -> None:
    from sqlalchemy import text
    tt_sub = "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"
    db.execute(text(
        f"DELETE FROM icb_costings.configurator_draft_snapshots WHERE trailer_type_id IN {tt_sub}"),
        {"m": f"{_MARK}%"})
    db.execute(text(
        f"DELETE FROM icb_costings.configurator_drafts WHERE trailer_type_id IN {tt_sub}"),
        {"m": f"{_MARK}%"})
    db.execute(text(
        f"DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN {tt_sub}"),
        {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


@pytest.fixture
def api(app_mod):
    import uuid
    from app.database import SessionLocal, User, UserSession
    from starlette.testclient import TestClient
    sid = str(uuid.uuid4())
    with SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").first()
        db.add(UserSession(id=sid, user_id=admin.id, role=admin.role, expires_at=None))
        db.commit()
    with TestClient(app_mod.app) as c:
        c.headers["Cookie"] = f"session_id={sid}"
        yield c
    with SessionLocal() as db:
        db.query(UserSession).filter_by(id=sid).delete()
        db.commit()


@pytest.fixture
def anon(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


@pytest.fixture
def staged():
    """Two bodies with overlapping structure, a pre-existing draft on the
    target, and a snapshot on the source whose payload references the source's
    own row ids in every cross-body-sensitive place."""
    from app.database import (
        BOMSection, BillOfMaterial, ConfiguratorDraft, ConfiguratorDraftSnapshot,
        Material, SessionLocal, TrailerType,
    )
    with SessionLocal() as db:
        _purge(db)
        src = TrailerType(name=f"{_MARK} SOURCE BODY", is_active=True)
        tgt = TrailerType(name=f"{_MARK} TARGET BODY", is_active=True)
        parked = TrailerType(name=f"{_MARK} INACTIVE BODY", is_active=False)
        sec_shared = BOMSection(name=f"{_MARK} SIDES", sort_order=9201)
        sec_only_a = BOMSection(name=f"{_MARK} ONLY A SEC", sort_order=9202)
        m_opt_shared = Material(name=f"{_MARK} OPT SHARED", unit_of_measure="each", price_per_unit=1.0)
        m_opt_only_a = Material(name=f"{_MARK} OPT ONLY A", unit_of_measure="each", price_per_unit=1.0)
        m_item_shared = Material(name=f"{_MARK} ITEM SHARED", unit_of_measure="each", price_per_unit=2.0)
        m_item_only_a = Material(name=f"{_MARK} ITEM ONLY A", unit_of_measure="each", price_per_unit=2.0)
        m_item_sec_a = Material(name=f"{_MARK} ITEM SEC A", unit_of_measure="each", price_per_unit=2.0)
        db.add_all([src, tgt, parked, sec_shared, sec_only_a,
                    m_opt_shared, m_opt_only_a, m_item_shared, m_item_only_a, m_item_sec_a])
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
        a_item_shared = bom(src, m_item_shared, section=sec_shared, sort=3)
        a_item_only = bom(src, m_item_only_a, section=sec_shared, sort=4)
        bom(src, m_item_sec_a, section=sec_only_a, sort=5)

        b_master_shared = bom(tgt, m_opt_shared, master=True, sort=1)
        b_item_shared = bom(tgt, m_item_shared, section=sec_shared, sort=2)
        db.flush()

        snap_payload = {
            "nextId": 9,
            "rootIds": ["1", "2"],
            "nodes": {
                "1": {"id": "1", "type": "category", "label": f"{_MARK} SIDES",
                      "sourceCategoryKey": f"{_MARK} SIDES", "parentId": None,
                      "childIds": ["3", "4"]},
                "2": {"id": "2", "type": "category", "label": "GONE ON TARGET",
                      "sourceCategoryKey": f"{_MARK} ONLY A SEC", "parentId": None,
                      "childIds": ["6"]},
                "3": {"id": "3", "type": "flag", "label": f"{_MARK} OPT SHARED",
                      "flagMode": "tickbox", "flagValue": 1, "parentId": "1", "childIds": [],
                      "flagBindingName": f"{_MARK} OPT SHARED",
                      "flagBindingId": a_master_shared.id},
                "4": {"id": "4", "type": "flag", "label": f"{_MARK} OPT ONLY A",
                      "flagMode": "tickbox", "flagValue": 0, "parentId": "1", "childIds": [],
                      "flagBindingName": f"{_MARK} OPT ONLY A",
                      "flagBindingId": a_master_only.id},
                "6": {"id": "6", "type": "flag", "label": f"{_MARK} OPT SHARED",
                      "flagMode": "tickbox", "flagValue": 0, "parentId": "2", "childIds": [],
                      "flagBindingName": f"{_MARK} OPT SHARED",
                      "flagBindingId": a_master_shared.id},
            },
            "itemRules": {
                str(a_item_shared.id): {"mode": "include",
                                        "conditions": [{"option": f"{_MARK} OPT SHARED", "equals": "Y"}]},
                str(a_item_only.id): {"mode": "exclude",
                                      "conditions": [{"option": f"{_MARK} OPT SHARED", "equals": "N"}]},
                _GHOST_RULE_ID: {"mode": "include", "conditions": []},
            },
        }
        snap = ConfiguratorDraftSnapshot(
            trailer_type_id=src.id, label=f"{_MARK} golden config",
            payload=json.dumps(snap_payload), created_by="admin")
        target_prior_draft = {"nextId": 2, "rootIds": [], "nodes": {},
                              "itemRules": {}, "marker": f"{_MARK}-PRIOR-TARGET-DRAFT"}
        db.add_all([snap, ConfiguratorDraft(trailer_type_id=tgt.id,
                                            payload=json.dumps(target_prior_draft))])
        db.commit()

        ids = {
            "src_id": src.id, "tgt_id": tgt.id, "parked_id": parked.id,
            "snap_id": snap.id,
            "a_master_shared": a_master_shared.id, "a_master_only": a_master_only.id,
            "a_item_shared": a_item_shared.id, "a_item_only": a_item_only.id,
            "b_master_shared": b_master_shared.id, "b_item_shared": b_item_shared.id,
        }
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


# ─── Audit (dry run) ─────────────────────────────────────────────────────────

def test_cross_audit_buckets_and_no_writes(api, staged):
    from app.database import ConfiguratorDraft, ConfiguratorDraftSnapshot, SessionLocal

    r = api.get(f"/api/configurator/draft-snapshots/{staged['snap_id']}/cross-audit",
                params={"target": staged["tgt_id"]})
    assert r.status_code == 200, r.text
    audit = r.json()

    assert audit["source"]["trailer_id"] == staged["src_id"]
    assert audit["target"]["trailer_id"] == staged["tgt_id"]

    # Flag bindings: the shared option remaps to the TARGET's master id; the
    # source-only option stays unbound; the flag inside the dropped section's
    # subtree ("6") never reaches the flag audit.
    matched = {f["node_id"]: f for f in audit["flags"]["matched"]}
    assert set(matched) == {"3"}
    assert matched["3"]["target_master_id"] == staged["b_master_shared"]
    assert [f["node_id"] for f in audit["flags"]["unmatched"]] == ["4"]

    # Sections: shared carries over, source-only drops.
    assert [c["node_id"] for c in audit["categories"]["matched"]] == ["1"]
    assert [c["node_id"] for c in audit["categories"]["dropped"]] == ["2"]

    # Item rules: never carried; matched names the target's same-named item.
    assert audit["item_rules"]["carried"] is False
    rules_matched = audit["item_rules"]["matched"]
    assert len(rules_matched) == 1
    assert rules_matched[0]["item_id"] == str(staged["a_item_shared"])
    assert rules_matched[0]["target_item_ids"] == [staged["b_item_shared"]]
    assert [x["item_id"] for x in audit["item_rules"]["unmatched"]] == [str(staged["a_item_only"])]
    assert [x["item_id"] for x in audit["item_rules"]["unresolvable"]] == [_GHOST_RULE_ID]

    s = audit["summary"]
    assert (s["flags_matched"], s["flags_unmatched"]) == (1, 1)
    assert (s["categories_matched"], s["categories_dropped"]) == (1, 1)
    assert s["item_rules_total"] == 3 and s["item_rules_matched"] == 1
    assert s["dropped_node_count"] == 2  # category "2" + its child flag "6"

    # Dry run: target draft untouched, no snapshot rows appeared anywhere.
    with SessionLocal() as db:
        draft = db.query(ConfiguratorDraft).filter_by(trailer_type_id=staged["tgt_id"]).first()
        assert f"{_MARK}-PRIOR-TARGET-DRAFT" in (draft.payload or "")
        n_snaps = (db.query(ConfiguratorDraftSnapshot)
                   .filter(ConfiguratorDraftSnapshot.trailer_type_id.in_(
                       [staged["src_id"], staged["tgt_id"]])).count())
        assert n_snaps == 1  # just the staged source snapshot


# ─── Apply ───────────────────────────────────────────────────────────────────

def test_restore_to_writes_remapped_draft_and_auto_backup(api, staged):
    from app.database import ConfiguratorDraft, ConfiguratorDraftSnapshot, SessionLocal

    r = api.post(
        f"/api/configurator/draft-snapshots/{staged['snap_id']}/restore-to/{staged['tgt_id']}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["restored_label"] == f"{_MARK} golden config"

    with SessionLocal() as db:
        # Target draft is the REMAPPED tree.
        draft_row = db.query(ConfiguratorDraft).filter_by(trailer_type_id=staged["tgt_id"]).first()
        stored = json.loads(draft_row.payload)
        assert stored == data["draft"]
        nodes = stored["nodes"]
        assert set(nodes) == {"1", "3", "4"}          # "2" and its child "6" dropped
        assert stored["rootIds"] == ["1"]
        assert nodes["3"]["flagBindingId"] == staged["b_master_shared"]  # remapped by name
        assert nodes["4"]["flagBindingId"] is None                       # unbound, name kept
        assert nodes["4"]["flagBindingName"] == f"{_MARK} OPT ONLY A"
        assert stored["itemRules"] == {}                                 # never carried

        # Auto-backup captured the target's PRIOR draft, on the TARGET.
        backup = db.query(ConfiguratorDraftSnapshot).filter_by(
            id=data["pre_restore_snapshot_id"]).first()
        assert backup is not None
        assert backup.trailer_type_id == staged["tgt_id"]
        assert f"{_MARK}-PRIOR-TARGET-DRAFT" in backup.payload
        assert "cross-body" in backup.label

        # Source snapshot untouched — still carries the SOURCE's row ids.
        snap = db.query(ConfiguratorDraftSnapshot).filter_by(id=staged["snap_id"]).first()
        assert snap.trailer_type_id == staged["src_id"]
        src_payload = json.loads(snap.payload)
        assert src_payload["nodes"]["3"]["flagBindingId"] == staged["a_master_shared"]
        assert str(staged["a_item_shared"]) in src_payload["itemRules"]


def test_restore_to_target_without_prior_draft_creates_one(api, staged):
    from app.database import ConfiguratorDraft, SessionLocal
    with SessionLocal() as db:
        db.query(ConfiguratorDraft).filter_by(trailer_type_id=staged["tgt_id"]).delete()
        db.commit()

    r = api.post(
        f"/api/configurator/draft-snapshots/{staged['snap_id']}/restore-to/{staged['tgt_id']}")
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        row = db.query(ConfiguratorDraft).filter_by(trailer_type_id=staged["tgt_id"]).first()
        assert row is not None
        assert json.loads(row.payload)["rootIds"] == ["1"]


# ─── Guards ──────────────────────────────────────────────────────────────────

def test_restore_to_same_body_is_rejected(api, staged):
    r = api.post(
        f"/api/configurator/draft-snapshots/{staged['snap_id']}/restore-to/{staged['src_id']}")
    assert r.status_code == 400
    assert "normal restore" in r.json()["detail"]


def test_missing_snapshot_and_target_are_404(api, staged):
    assert api.get("/api/configurator/draft-snapshots/999999999/cross-audit",
                   params={"target": staged["tgt_id"]}).status_code == 404
    assert api.get(f"/api/configurator/draft-snapshots/{staged['snap_id']}/cross-audit",
                   params={"target": 999999999}).status_code == 404
    # Inactive body types are not restore targets.
    assert api.get(f"/api/configurator/draft-snapshots/{staged['snap_id']}/cross-audit",
                   params={"target": staged["parked_id"]}).status_code == 404
    assert api.post(
        f"/api/configurator/draft-snapshots/{staged['snap_id']}/restore-to/{staged['parked_id']}"
    ).status_code == 404


def test_cross_endpoints_are_admin_gated(anon, staged):
    assert anon.get(
        f"/api/configurator/draft-snapshots/{staged['snap_id']}/cross-audit",
        params={"target": staged["tgt_id"]}).status_code == 401
    assert anon.post(
        f"/api/configurator/draft-snapshots/{staged['snap_id']}/restore-to/{staged['tgt_id']}"
    ).status_code == 401
