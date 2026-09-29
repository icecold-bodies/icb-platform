"""v1.59.1 Part B — the Trailer Designer's rule editor never rewrites a rule it can't show.

Found by the rear-frame lane (28 Sep): the item inclusion-rule editor offers only the
flags in the item's category branch. A saved condition naming a flag from elsewhere in
the tree (SRD PU on a REAR FRAME line) was REPLACED with the first flag on offer when
the rule was opened and saved — silently changing what gets costed.

The fix is client-side (the editor keeps and shows such conditions; the browser proof
is tests/journeys/test_rule_editor_keeps_rules_journey.py). This module pins the
server half of the round trip the editor now relies on:

  * the categories endpoint hands the editor each condition's stored ``option_id``
    (it used to drop it, so no client could send a condition back as stored);
  * sending those conditions straight back through the unchanged PATCH writes
    ``bom_conditions`` back BYTE-IDENTICAL, in both stored shapes (include list,
    exclude object), including a condition whose option_id is NOT the one the
    server would auto-resolve by name.

Marker 'J1591RE'; purge on both sides; raw Cookie header ([[testclient-session-cookie]]).
"""
import json

import pytest

_MARK = "J1591RE"


def _purge(db) -> None:
    from sqlalchemy import text
    tt = "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"
    db.execute(text(f"DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN {tt}"),
               {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE :m"), {"m": f"{_MARK}%"})
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
def staged(app_mod):
    """A v2 marker body: two flag masters (SRD PU, FRONT EPS) and a REAR FRAME
    section with three lines, their rules stored the way the rear-frame tool
    writes them (json.dumps of [{option, equals, option_id}])."""
    from app.database import (BillOfMaterial, BOMSection, Material, SessionLocal,
                              TrailerType)
    with SessionLocal() as db:
        _purge(db)
        body = TrailerType(name=f"{_MARK} BODY", is_active=True, configurator_v2=True)
        sec = BOMSection(name=f"{_MARK} REAR FRAME", sort_order=9201)
        m_srd = Material(name=f"{_MARK} SRD PU", unit_of_measure="each", price_per_unit=0.0)
        m_front = Material(name=f"{_MARK} FRONT EPS", unit_of_measure="each", price_per_unit=0.0)
        m_item = Material(name=f"{_MARK} FRAME RAIL", unit_of_measure="each", price_per_unit=5.0)
        db.add_all([body, sec, m_srd, m_front, m_item])
        db.flush()

        def bom(material, master=False, conditions=None):
            r = BillOfMaterial(trailer_type_id=body.id, material_id=material.id,
                               formula_expression="1", is_body_option=master,
                               bom_section=("BODY OPTIONS" if master else sec.name),
                               bom_section_id=(None if master else sec.id),
                               bom_conditions=conditions)
            db.add(r)
            db.flush()
            return r

        srd = bom(m_srd, master=True)
        front = bom(m_front, master=True)
        include_rule = json.dumps([{"option": m_srd.name, "equals": "N", "option_id": srd.id}])
        exclude_rule = json.dumps({"mode": "exclude", "all": [
            {"option": m_srd.name, "equals": "Y", "option_id": srd.id},
            {"option": m_front.name, "equals": "N", "option_id": front.id}]})
        # option_id deliberately NOT the one the server would auto-resolve by
        # name: a Save must still keep what is stored.
        odd_rule = json.dumps([{"option": m_srd.name, "equals": "N", "option_id": front.id}])
        inc = bom(m_item, conditions=include_rule)
        exc = bom(m_item, conditions=exclude_rule)
        odd = bom(m_item, conditions=odd_rule)
        db.commit()
        ids = {"body": body.id, "srd": srd.id, "front": front.id,
               "inc": inc.id, "exc": exc.id, "odd": odd.id,
               "raw": {inc.id: include_rule, exc.id: exclude_rule, odd.id: odd_rule}}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _stored(item_id):
    from app.database import BillOfMaterial, SessionLocal
    with SessionLocal() as db:
        return db.get(BillOfMaterial, item_id).bom_conditions


def _categories_items(api, body_id):
    r = api.get(f"/api/admin/settings/body-types/{body_id}/categories")
    assert r.status_code == 200, r.text
    payload = r.json()
    cats = payload["categories"] if isinstance(payload, dict) else payload
    return {it["id"]: it for c in cats for it in c.get("items", [])}


def test_categories_endpoint_carries_stored_option_id(api, staged):
    items = _categories_items(api, staged["body"])
    assert items[staged["inc"]]["conditions"] == [
        {"option": f"{_MARK} SRD PU", "equals": "N", "option_id": staged["srd"]}]
    assert items[staged["exc"]]["conditionMode"] == "exclude"
    assert [c["option_id"] for c in items[staged["exc"]]["conditions"]] == [
        staged["srd"], staged["front"]]


@pytest.mark.parametrize("key", ["inc", "exc", "odd"])
def test_unchanged_save_round_trips_byte_identical(api, staged, key):
    """What the editor sends on an unchanged Save = the conditions + mode the
    categories endpoint gave it. The stored JSON must come back identical."""
    item_id = staged[key]
    before = _stored(item_id)
    assert before == staged["raw"][item_id]
    it = _categories_items(api, staged["body"])[item_id]
    r = api.patch(f"/api/configurator/items/{item_id}/conditions",
                  json={"conditions": it["conditions"], "mode": it["conditionMode"]})
    assert r.status_code == 200, r.text
    after = _stored(item_id)
    assert json.loads(after) == json.loads(before)          # canonical
    assert after == before                                  # and byte for byte


def test_adding_an_in_branch_condition_keeps_the_out_of_branch_one(api, staged):
    item_id = staged["inc"]
    it = _categories_items(api, staged["body"])[item_id]
    conditions = it["conditions"] + [{"option": f"{_MARK} FRONT EPS", "equals": "Y"}]
    r = api.patch(f"/api/configurator/items/{item_id}/conditions",
                  json={"conditions": conditions, "mode": "include"})
    assert r.status_code == 200, r.text
    stored = json.loads(_stored(item_id))
    assert stored[0] == {"option": f"{_MARK} SRD PU", "equals": "N", "option_id": staged["srd"]}
    assert stored[1]["option"] == f"{_MARK} FRONT EPS"
    assert len(stored) == 2
