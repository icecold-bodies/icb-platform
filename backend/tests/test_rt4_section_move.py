"""RT4 Part A — "Move into existing section" + an honest rename (RT4_RULING_1 Q4–Q6).

A section is ONE global row every body shares. These pin:
  * the move: POST /api/bom-sections/{id}/move-body-lines moves ONLY the chosen body's rows — matched by FK id
    AND by the legacy string — and every other BOM row in the database stays byte-identical;
  * the draft rule (A2): only that body's Settings-page draft is re-keyed, and only when it has no node for the
    new name yet; otherwise it is left exactly as it was and reported;
  * the delete offer: `old_section_unused` is true only when no row on ANY body names the old section any more;
  * the honest rename: the usage the dialog shows (bodies + names), and a global rename (Body Templates PUT and the
    Configurator (preview) PATCH) re-keys every draft naming the old section — except one that already has the
    new name, which is left and reported; draft snapshots are never touched;
  * permissions: no session 401, a non-admin 403.

House pattern (test_bom_section_manage.py): live _test database, marker rows 'RT4SM*', purge on both sides,
real UserSession rows + raw Cookie header.
"""
import hashlib
import json
import uuid

import pytest
from sqlalchemy import text

_MARK = "RT4SM"


def _purge(db) -> None:
    m = {"m": f"{_MARK}%"}
    db.execute(text("DELETE FROM icb_costings.configurator_draft_snapshots WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name ILIKE :m)"), m)
    db.execute(text("DELETE FROM icb_costings.configurator_drafts WHERE trailer_type_id IN "
                    "(SELECT id FROM icb_costings.trailer_types WHERE name ILIKE :m)"), m)
    db.execute(text("DELETE FROM icb_costings.bill_of_materials WHERE material_id IN "
                    "(SELECT id FROM icb_costings.materials WHERE name ILIKE :m)"), m)
    db.execute(text("DELETE FROM icb_costings.materials WHERE name ILIKE :m"), m)
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name ILIKE :m"), m)
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name ILIKE :m"), m)
    db.execute(text("DELETE FROM icb_costings.user_sessions WHERE id LIKE 'rt4sm-%'"))
    db.execute(text("DELETE FROM icb_costings.users WHERE username ILIKE 'rt4sm_%'"))
    db.commit()


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


def _session(user_id: int, role: str) -> dict:
    from app.database import SessionLocal, UserSession
    sid = f"rt4sm-{uuid.uuid4().hex[:12]}"
    with SessionLocal() as db:
        db.add(UserSession(id=sid, user_id=user_id, role=role, expires_at=None, csrf_token=f"csrf-{sid}"))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": f"csrf-{sid}"}


@pytest.fixture
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


def _draft(*keys: str, labels: dict | None = None) -> str:
    nodes = {"f1": {"id": "f1", "type": "folder", "label": "DOOR TYPE", "childIds": []}}
    for i, k in enumerate(keys):
        nid = f"c{i}"
        nodes[nid] = {"id": nid, "type": "category", "sourceCategoryKey": k,
                      "label": (labels or {}).get(k, k), "parentId": "f1"}
        nodes["f1"]["childIds"].append(nid)
    return json.dumps({"rootIds": ["f1"], "nodes": nodes})


@pytest.fixture
def world(app_mod):
    """Bodies A, B (live), C (live, no lines in OLD), D (soft-deleted). Sections OLD, NEW, OTHER.
    A: 2 OLD rows by id + 1 OLD row by STRING only + 1 OTHER row; B: 1 OLD row by id + 2 NEW rows;
    D: 1 NEW row. Drafts: A names OLD (label OLD), B names OLD (custom label), C names NEW."""
    from app.database import (BillOfMaterial, BOMSection, ConfiguratorDraft, Material, SessionLocal, TrailerType,
                              User)
    with SessionLocal() as db:
        _purge(db)
        a = TrailerType(name=f"{_MARK} A", is_active=True)
        b = TrailerType(name=f"{_MARK} B", is_active=False)
        c = TrailerType(name=f"{_MARK} C", is_active=True)
        d = TrailerType(name=f"{_MARK} D [deleted-0]", is_active=False)
        old = BOMSection(name=f"{_MARK} DOOR FITTINGS SRD", sort_order=9201)
        new = BOMSection(name=f"{_MARK} SRD DOOR FITTINGS", sort_order=9202)
        other = BOMSection(name=f"{_MARK} OTHER", sort_order=9203)
        mat = Material(name=f"{_MARK} WIDGET", unit_of_measure="each", price_per_unit=1.0)
        db.add_all([a, b, c, d, old, new, other, mat])
        db.flush()

        def line(t, sec, by_id=True):
            r = BillOfMaterial(trailer_type_id=t.id, material_id=mat.id, formula_expression="1",
                               bom_section=sec.name, bom_section_id=sec.id if by_id else None)
            db.add(r)
            return r
        rows = {"a_id1": line(a, old), "a_id2": line(a, old), "a_str": line(a, old, by_id=False),
                "a_other": line(a, other), "b_old": line(b, old), "b_new1": line(b, new), "b_new2": line(b, new),
                "d_new": line(d, new)}
        db.add(ConfiguratorDraft(trailer_type_id=a.id, payload=_draft(old.name)))
        db.add(ConfiguratorDraft(trailer_type_id=b.id, payload=_draft(old.name, labels={old.name: "B's own label"})))
        db.add(ConfiguratorDraft(trailer_type_id=c.id, payload=_draft(new.name)))
        sales = User(username=f"rt4sm_sales_{uuid.uuid4().hex[:6]}", password_hash="x", role="sales", email="")
        db.add(sales)
        db.commit()
        admin = db.query(User).filter_by(username="admin").first()
        ids = {"a": a.id, "b": b.id, "c": c.id, "d": d.id, "old": old.id, "new": new.id, "other": other.id,
               "old_name": old.name, "new_name": new.name, "rows": {k: r.id for k, r in rows.items()},
               "sales_id": sales.id, "admin_id": admin.id}
    ids["admin"] = _session(ids["admin_id"], "admin")
    ids["sales"] = _session(ids["sales_id"], "sales")
    yield ids
    with SessionLocal() as db:
        _purge(db)


def _bom_hash_except(moved: set[int]) -> str:
    """md5 over EVERY bill_of_materials row in the database except `moved` — all columns, in id order."""
    from app.database import engine
    with engine.connect() as c:
        rows = c.execute(text("SELECT b.* FROM icb_costings.bill_of_materials b ORDER BY b.id")).mappings().all()
    h = hashlib.md5()
    for r in rows:
        if r["id"] not in moved:
            h.update(repr(sorted((k, str(v)) for k, v in r.items())).encode())
    return h.hexdigest()


def _row(bid: int) -> dict:
    from app.database import engine
    with engine.connect() as c:
        return dict(c.execute(text("SELECT bom_section_id, bom_section FROM icb_costings.bill_of_materials "
                                   "WHERE id = :i"), {"i": bid}).mappings().one())


def _draft_of(tid: int) -> str:
    from app.database import engine
    with engine.connect() as c:
        return c.execute(text("SELECT payload FROM icb_costings.configurator_drafts WHERE trailer_type_id = :t"),
                         {"t": tid}).scalar()


def _move(client, w, tid, headers=None):
    return client.post(f"/api/bom-sections/{w['old']}/move-body-lines",
                       json={"trailer_type_id": tid, "to_section_id": w["new"]}, headers=headers or w["admin"])


# ── the move ──────────────────────────────────────────────────────────────────────

def test_the_move_touches_only_the_chosen_body_and_both_match_paths(client, world):
    w = world
    mine = {w["rows"][k] for k in ("a_id1", "a_id2", "a_str")}
    before = _bom_hash_except(mine)
    r = _move(client, w, w["a"])
    assert r.status_code == 200, r.text
    j = r.json()
    assert sorted(j["moved_ids"]) == sorted(mine)                 # by id AND the string-only row
    for bid in mine:                                              # both columns, together
        assert _row(bid) == {"bom_section_id": w["new"], "bom_section": w["new_name"]}
    assert _bom_hash_except(mine) == before                       # every other row in the DB byte-identical
    assert _row(w["rows"]["b_old"]) == {"bom_section_id": w["old"], "bom_section": w["old_name"]}


def test_the_draft_rule_rewrites_only_this_bodys_draft(client, world):
    w = world
    b_before = _draft_of(w["b"])
    c_before = _draft_of(w["c"])
    j = _move(client, w, w["a"]).json()
    assert j["draft"] == "rewritten"
    nodes = json.loads(_draft_of(w["a"]))["nodes"]
    cats = [n for n in nodes.values() if n["type"] == "category"]
    assert [(n["sourceCategoryKey"], n["label"]) for n in cats] == [(w["new_name"], w["new_name"])]
    assert _draft_of(w["b"]) == b_before                         # another body's draft: never touched
    assert _draft_of(w["c"]) == c_before
    assert [d["trailer_type_id"] for d in j["other_drafts_naming_old"]] == [w["b"]]


def test_a_draft_that_already_has_the_new_name_is_left_and_reported(client, world):
    from app.database import ConfiguratorDraft, SessionLocal
    w = world
    with SessionLocal() as db:
        db.query(ConfiguratorDraft).filter_by(trailer_type_id=w["a"]).update(
            {"payload": _draft(w["old_name"], w["new_name"])})
        db.commit()
    before = _draft_of(w["a"])
    j = _move(client, w, w["a"]).json()
    assert j["draft"] == "node_exists"
    assert _draft_of(w["a"]) == before


def test_the_delete_offer_appears_only_when_the_old_section_is_unused_everywhere(client, world):
    w = world
    assert _move(client, w, w["a"]).json()["old_section_unused"] is False      # B still uses it
    j = client.post(f"/api/bom-sections/{w['old']}/move-body-lines",
                    json={"trailer_type_id": w["b"], "to_section_id": w["new"]}, headers=w["admin"]).json()
    assert j["old_section_unused"] is True
    r = client.delete(f"/api/bom-sections/{w['old']}", headers=w["admin"])
    assert r.status_code == 200, r.text


def test_a_string_only_row_on_another_body_keeps_the_section_in_use(client, world):
    from app.database import BillOfMaterial, SessionLocal
    w = world
    with SessionLocal() as db:       # B's OLD row loses its FK id: it names OLD by the legacy string only
        db.query(BillOfMaterial).filter_by(id=w["rows"]["b_old"]).update({"bom_section_id": None})
        db.commit()
    assert _move(client, w, w["a"]).json()["old_section_unused"] is False


def test_the_move_refuses_what_it_should(client, world):
    w = world
    same = client.post(f"/api/bom-sections/{w['old']}/move-body-lines",
                       json={"trailer_type_id": w["a"], "to_section_id": w["old"]}, headers=w["admin"])
    assert same.status_code == 400
    none_here = _move(client, w, w["c"])
    assert none_here.status_code == 400 and "no lines" in none_here.json()["detail"]
    missing = client.post("/api/bom-sections/99999999/move-body-lines",
                          json={"trailer_type_id": w["a"], "to_section_id": w["new"]}, headers=w["admin"])
    assert missing.status_code == 404
    from app.database import BOMSection, SessionLocal
    from datetime import datetime
    with SessionLocal() as db:
        db.query(BOMSection).filter_by(id=w["new"]).update({"archived_at": datetime.utcnow()})
        db.commit()
    archived = _move(client, w, w["a"])
    assert archived.status_code == 400 and "Unassigned" in archived.json()["detail"]


def test_permissions_no_session_401_non_admin_403(client, world):
    w = world
    assert _move(client, w, w["a"], headers={"X-Unused": "1"}).status_code == 401
    assert _move(client, w, w["a"], headers=w["sales"]).status_code == 403
    for url in (f"/api/bom-sections/{w['old']}/usage", "/api/bom-sections/usage"):
        assert client.get(url).status_code == 401
        assert client.get(url, headers=w["sales"]).status_code == 403
    assert _row(w["rows"]["a_id1"])["bom_section_id"] == w["old"]                # nothing moved


# ── the honest rename ─────────────────────────────────────────────────────────────

def test_the_usage_the_dialog_shows(client, world):
    w = world
    u = client.get(f"/api/bom-sections/{w['old']}/usage", headers=w["admin"]).json()
    assert u["lines"] == 4                                                    # A: 2 by id + 1 by string; B: 1
    assert {(b["name"], b["lines"], b["deleted"]) for b in u["bodies"]} == {
        (f"{_MARK} A", 3, False), (f"{_MARK} B", 1, False)}
    assert u["live_bodies"] == 2
    n = client.get(f"/api/bom-sections/{w['new']}/usage", headers=w["admin"]).json()
    assert {(b["name"], b["deleted"]) for b in n["bodies"]} == {(f"{_MARK} B", False), (f"{_MARK} D [deleted-0]", True)}
    assert n["live_bodies"] == 1                                              # a deleted body is not counted
    assert n["door_prefix"] is None and u["door_prefix"] is None              # marker names start with RT4SM
    summary = {s["id"]: s for s in client.get("/api/bom-sections/usage", headers=w["admin"]).json()}
    assert (summary[w["old"]]["lines"], summary[w["old"]]["live_bodies"]) == (4, 2)
    assert (summary[w["other"]]["lines"], summary[w["other"]]["live_bodies"]) == (1, 1)


def test_the_rename_preview_names_the_drafts_that_change_and_the_one_left(client, world):
    w = world
    renamed = f"{_MARK} SRD DOOR FITTINGS"          # = NEW's name: C's draft already has it
    u = client.get(f"/api/bom-sections/{w['other']}/usage", params={"rename_to": renamed},
                   headers=w["admin"]).json()
    assert u["rename_drafts"] == {"rewritten": [], "left": []}                 # nobody's draft names OTHER
    u = client.get(f"/api/bom-sections/{w['old']}/usage", params={"rename_to": f"{_MARK} RENAMED"},
                   headers=w["admin"]).json()
    assert sorted(d["trailer_type_id"] for d in u["rename_drafts"]["rewritten"]) == sorted([w["a"], w["b"]])
    assert _draft_of(w["a"]) == _draft(w["old_name"])                         # a preview writes nothing


def test_a_global_rename_rekeys_every_draft_but_leaves_one_that_has_the_new_name(client, world):
    from app.database import ConfiguratorDraft, ConfiguratorDraftSnapshot, SessionLocal
    w = world
    target = f"{_MARK} RENAMED"
    with SessionLocal() as db:
        db.query(ConfiguratorDraft).filter_by(trailer_type_id=w["c"]).update(
            {"payload": _draft(w["old_name"], target)})
        db.add(ConfiguratorDraftSnapshot(trailer_type_id=w["a"], label="before", payload=_draft(w["old_name"])))
        db.commit()
    c_before = _draft_of(w["c"])
    r = client.put(f"/api/bom-sections/{w['old']}", json={"name": target}, headers=w["admin"])
    assert r.status_code == 200, r.text
    j = r.json()
    assert sorted(d["trailer_type_id"] for d in j["drafts_rewritten"]) == sorted([w["a"], w["b"]])
    assert [d["trailer_type_id"] for d in j["drafts_left"]] == [w["c"]]
    assert _draft_of(w["c"]) == c_before                                       # left exactly as it was
    b_cat = [n for n in json.loads(_draft_of(w["b"]))["nodes"].values() if n["type"] == "category"][0]
    assert (b_cat["sourceCategoryKey"], b_cat["label"]) == (target, "B's own label")   # custom label kept
    with SessionLocal() as db:                                                  # snapshots: never touched
        snap = db.query(ConfiguratorDraftSnapshot).filter_by(trailer_type_id=w["a"]).one()
        assert snap.payload == _draft(w["old_name"])


def test_the_configurator_rename_rekeys_the_drafts_too(client, world):
    w = world
    target = f"{_MARK} VIA CONFIGURATOR"
    r = client.patch(f"/api/configurator/sections/{w['old']}", json={"name": target}, headers=w["admin"])
    assert r.status_code == 200, r.text
    assert sorted(d["trailer_type_id"] for d in r.json()["drafts_rewritten"]) == sorted([w["a"], w["b"]])
    keys = [n["sourceCategoryKey"] for n in json.loads(_draft_of(w["a"]))["nodes"].values() if n["type"] == "category"]
    assert keys == [target]


def test_a_taken_name_is_refused_honestly_in_any_case(client, world):
    w = world
    for name in (w["new_name"], w["new_name"].lower()):          # never a near-twin that differs by case
        r = client.put(f"/api/bom-sections/{w['old']}", json={"name": name}, headers=w["admin"])
        assert r.status_code == 400 and "shared" in r.json()["detail"], (name, r.text)
        p = client.patch(f"/api/configurator/sections/{w['old']}", json={"name": name}, headers=w["admin"])
        assert p.status_code == 409, (name, p.text)
    assert _row(w["rows"]["a_id1"]) == {"bom_section_id": w["old"], "bom_section": w["old_name"]}


def test_move_items_uses_the_shared_move(client, world):
    w = world
    rid = w["rows"]["a_other"]
    r = client.post(f"/api/configurator/sections/{w['new']}/move-items", json={"itemIds": [rid]},
                    headers=w["admin"])
    assert r.status_code == 200, r.text
    assert _row(rid) == {"bom_section_id": w["new"], "bom_section": w["new_name"]}


# ── the A2 rule itself ──────────────────────────────────────────────────────────

def test_rewrite_draft_key_unit():
    from app.services.sections import rewrite_draft_key
    st, p, n = rewrite_draft_key(_draft("door fittings srd", "FRONT"), "DOOR FITTINGS SRD", "SRD DOOR FITTINGS")
    assert (st, n) == ("rewritten", 1)
    cats = {n["sourceCategoryKey"]: n["label"] for n in json.loads(p)["nodes"].values() if n["type"] == "category"}
    assert cats == {"SRD DOOR FITTINGS": "SRD DOOR FITTINGS", "FRONT": "FRONT"}
    assert rewrite_draft_key(_draft("A", "B"), "A", "b")[0] == "node_exists"
    assert rewrite_draft_key(_draft("A"), "Z", "Y")[0] == "no_node"
    assert rewrite_draft_key("not json", "A", "B")[0] == "unparseable"
