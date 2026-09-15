"""v1.52 — an admin captures a costing FOR another user.

Michael does costings on behalf of the sales staff; until now each one was credited to
whoever was logged in. The attribution already had a column — calculations.
sales_rep_user_id (0017) — that nothing ever wrote. This module pins the lane's rules:

  AUTHORSHIP IS NEVER REWRITTEN  user_id stays the admin who saved it; the selection
                                 lands in sales_rep_user_id.
  ONE RESOLUTION                 every read resolves rep -> creator through
                                 services/costing_attribution (list, detail, legacy
                                 dashboard, Pre-Job Card default, export filename).
  G1: ENFORCED IN CODE           /api/approve (create, overwrite, Replace) and the
                                 re-assign route refuse any change of attribution to a
                                 caller without costings.capture_for_user — the hidden
                                 dropdown is not the control. The refusal tests below are
                                 the lane's NEGATIVE CONTROL: they go red with the
                                 permission checks removed (proven in the PR).
  UNTOUCHED == TODAY             a save whose dropdown was left on "yourself" stores the
                                 same row, byte for byte, as a save with no dropdown.
  FROZEN WHEN DECIDED            re-assign works only while the costing is pending.
  JOURNALED                      every capture and re-assign, with username snapshots
                                 that survive a rename and a delete.

House pattern (test_costing_delete_own_draft.py): live test DB, REAL session rows sent as
raw Cookie headers, marker rows, purge on both sides.
"""
import json
import uuid

import pytest
from sqlalchemy import text

_MARK = "V152CF"
_mark = _MARK.lower()
TT_NAME = f"{_MARK} BODY"
SECTION = f"{_MARK} FLOOR"


def _purge(db) -> None:
    owned = ("SELECT cal.id FROM icb_costings.calculations cal "
             "JOIN icb_costings.customers c ON c.id = cal.customer_id WHERE c.name LIKE :m")
    db.execute(text(f"DELETE FROM icb_mes.prejob_cards WHERE calculation_id IN ({owned})"),
               {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_mes.prejob_templates WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text(f"DELETE FROM icb_mes.production_jobs WHERE calculation_record_id IN ({owned})"),
               {"m": f"{_MARK}%"})
    # The journal rows go with their costings (ON DELETE CASCADE, migration 0048).
    db.execute(text(
        "DELETE FROM icb_costings.calculations cal USING icb_costings.customers c "
        "WHERE cal.customer_id = c.id AND c.name LIKE :m"), {"m": f"{_MARK}%"})
    db.commit()


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    # Entering the client runs startup, which is what seeds the new catalogue key.
    with TestClient(m.app):
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


def _session_for(user_id: int, role: str) -> dict:
    from app.database import SessionLocal, UserSession
    sid = f"v152-{uuid.uuid4().hex[:12]}"
    with SessionLocal() as db:
        db.merge(UserSession(id=sid, user_id=user_id, role=role, expires_at=None,
                             csrf_token=f"csrf-{sid}"))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": f"csrf-{sid}"}


@pytest.fixture(scope="module")
def people(app_mod):
    """admin + Nadie ('full') + Lezette ('sales') + a second 'full' colleague."""
    from app.database import SessionLocal, User, UserSession
    roles = {"nadie": "full", "lezette": "sales", "other": "full"}
    out = {}
    with SessionLocal() as db:
        for who, role in roles.items():
            db.add(User(username=f"{_mark}_{who}_{uuid.uuid4().hex[:6]}", password_hash="x",
                        role=role, email=""))
        db.commit()
        for who, role in roles.items():
            u = (db.query(User).filter(User.username.like(f"{_mark}_{who}_%"))
                   .order_by(User.id.desc()).first())
            out[who] = {"id": u.id, "username": u.username, "headers": _session_for(u.id, role)}
        a = db.query(User).filter_by(username="admin").first()
        out["admin"] = {"id": a.id, "username": a.username, "headers": _session_for(a.id, a.role)}
    yield out
    with SessionLocal() as db:
        _purge(db)
        for p in out.values():
            sid = p["headers"]["Cookie"].split("session_id=")[1]
            db.query(UserSession).filter_by(id=sid).delete()
        db.execute(text("DELETE FROM icb_costings.user_permissions WHERE user_id IN "
                        "(SELECT id FROM icb_costings.users WHERE username LIKE :m)"),
                   {"m": f"{_mark}_%"})
        db.execute(text("DELETE FROM icb_costings.users WHERE username LIKE :m"),
                   {"m": f"{_mark}_%"})
        db.commit()


@pytest.fixture(scope="module")
def seeded(app_mod, people):
    """A one-row body (for the BODY save path) and the marker customer."""
    from app.database import (SessionLocal, TrailerType, BillOfMaterial, BOMSection,
                              Material, Customer)
    with SessionLocal() as db:
        mat = Material(name=f"{TT_NAME} PLYWOOD", unit_of_measure="m2",
                       price_per_unit=100.0, is_active=True)
        sec = BOMSection(name=SECTION, sort_order=10, is_optional=False)
        tt = TrailerType(name=TT_NAME, is_active=True, default_length=6.0,
                         default_width=2.5, default_height=2.4)
        cust = Customer(name=f"{_MARK} Carriers", bp_code=f"{_MARK}1", is_active=True)
        db.add_all([mat, sec, tt, cust])
        db.flush()
        row = BillOfMaterial(trailer_type_id=tt.id, material_id=mat.id, formula_expression="10",
                             waste_percentage=0, bom_section=SECTION, bom_section_id=sec.id,
                             sort_order=1)
        db.add(row)
        db.commit()
        ids = {"tt": tt.id, "mat": mat.id, "sec": sec.id, "customer": cust.id, "bom": row.id}
    yield ids
    with SessionLocal() as db:
        _purge(db)
        db.query(BillOfMaterial).filter_by(id=ids["bom"]).delete()
        db.query(TrailerType).filter_by(id=ids["tt"]).delete()
        db.query(BOMSection).filter_by(id=ids["sec"]).delete()
        db.query(Material).filter_by(id=ids["mat"]).delete()
        db.query(Customer).filter_by(id=ids["customer"]).delete()
        db.commit()


@pytest.fixture(autouse=True)
def _clean(app_mod):
    from app.database import SessionLocal
    with SessionLocal() as db:
        _purge(db)
    yield
    with SessionLocal() as db:
        _purge(db)


def _repair(seeded, **over):
    payload = {
        "is_repair": True, "trailer_type_id": None,
        "customer_id": seeded["customer"],
        "repair_type": "Side panel replacement",
        "repair_lines": [{"kind": "free_hand", "key": "f1", "description": "Labour",
                          "qty": 2, "unit": "hour", "unit_price": 300}],
        "icb_contact_name": "Typed Contact", "icb_contact_phone": "011 000 0000",
        "profit_margin": 0, "dimensions": {},
    }
    payload.update(over)
    return payload


def _body(seeded, **over):
    payload = {
        "trailer_type_id": seeded["tt"], "customer_id": seeded["customer"],
        "dimensions": {"length": 6.0, "width": 2.5, "height": 2.4},
        "profit_margin": 0,
        # An independent costing every time, so repeated saves never trip the
        # customer + body duplicate guard.
        "version_action": "save_as_new",
    }
    payload.update(over)
    return payload


def _row(rec_id: int) -> dict:
    from app.database import SessionLocal
    with SessionLocal() as db:
        r = db.execute(text("SELECT * FROM icb_costings.calculations WHERE id = :i"),
                       {"i": rec_id}).mappings().first()
        return dict(r) if r else None


def _journal(rec_id: int) -> list[dict]:
    from app.database import SessionLocal
    with SessionLocal() as db:
        return [dict(r) for r in db.execute(text(
            "SELECT action, from_user_id, from_username, to_user_id, to_username, "
            "actor_user_id, actor_username FROM icb_costings.calculations_sales_rep_audit "
            "WHERE calculation_id = :i ORDER BY created_at, id"), {"i": rec_id}).mappings()]


def _marker_count() -> int:
    from app.database import SessionLocal
    with SessionLocal() as db:
        return db.execute(text(
            "SELECT count(*) FROM icb_costings.calculations cal "
            "JOIN icb_costings.customers c ON c.id = cal.customer_id WHERE c.name LIKE :m"),
            {"m": f"{_MARK}%"}).scalar()


def _save(client, headers, payload) -> dict:
    r = client.post("/api/approve", json=payload, headers=headers)
    assert r.status_code == 200, r.text[:600]
    return r.json()


# ── the key ──────────────────────────────────────────────────────────────────

def test_the_key_is_in_the_catalogue_for_admin_only(app_mod):
    """A gate string that is not a catalogue key is invisible: admin passes on the
    code-level wildcard, so a typo would look like a working feature."""
    from app.database import PERMISSION_CATALOGUE
    row = [r for r in PERMISSION_CATALOGUE if r[0] == "costings.capture_for_user"]
    assert row, "costings.capture_for_user is missing from PERMISSION_CATALOGUE"
    assert row[0][2] == "admin" and row[0][3] == {"admin"}


def test_startup_seeded_the_key_and_granted_it_to_nobody_else(app_mod):
    from app.database import SessionLocal
    with SessionLocal() as db:
        roles = {r[0] for r in db.execute(text(
            "SELECT rp.role FROM icb_costings.role_permissions rp "
            "JOIN icb_costings.permissions p ON p.id = rp.permission_id "
            "WHERE p.name = 'costings.capture_for_user'"))}
    assert roles == {"admin"}, roles


# ── the picker ───────────────────────────────────────────────────────────────

def test_admin_gets_every_user_with_username_and_role(client, people):
    r = client.get("/api/capture-for/users", headers=people["admin"]["headers"])
    assert r.status_code == 200, r.text[:300]
    rows = r.json()
    from app.database import SessionLocal, User
    with SessionLocal() as db:
        expected = [u.username for u in db.query(User).order_by(User.username).all()]
    assert [u["username"] for u in rows] == expected, "must be EVERY user, Manage Users order"
    assert all(set(u) == {"id", "username", "role"} for u in rows)
    nadie = next(u for u in rows if u["id"] == people["nadie"]["id"])
    assert nadie["role"] == "full"


def test_the_picker_is_refused_without_the_key(client, people):
    r = client.get("/api/capture-for/users", headers=people["nadie"]["headers"])
    assert r.status_code == 403


# ── the resolution helper ────────────────────────────────────────────────────

def test_rep_resolves_to_the_creator_until_someone_else_is_chosen(people):
    from types import SimpleNamespace
    from app.services.costing_attribution import rep_user_id, rep_username
    admin = SimpleNamespace(id=people["admin"]["id"], username="admin")
    nadie = SimpleNamespace(id=people["nadie"]["id"], username=people["nadie"]["username"])
    legacy = SimpleNamespace(user_id=admin.id, user=admin, sales_rep_user_id=None, sales_rep=None)
    assert rep_user_id(legacy) == admin.id and rep_username(legacy) == "admin"
    captured = SimpleNamespace(user_id=admin.id, user=admin,
                               sales_rep_user_id=nadie.id, sales_rep=nadie)
    assert rep_user_id(captured) == nadie.id
    assert rep_username(captured) == people["nadie"]["username"]
    orphan = SimpleNamespace(user_id=None, user=None, sales_rep_user_id=None, sales_rep=None)
    assert rep_username(orphan) == "—" and rep_username(orphan, None) is None
    # An id with no user behind it (not reachable through the FK, but never "nobody"):
    # the costing still belongs to its creator.
    dangling = SimpleNamespace(user_id=admin.id, user=admin, sales_rep_user_id=-1, sales_rep=None)
    assert rep_username(dangling) == "admin"


def test_a_stale_relationship_never_names_the_previous_rep(people):
    """Assigning the id in a session leaves `rec.sales_rep` on the old user until a
    refresh — the helper must follow the column, not the stale object."""
    from app.database import CalculationRecord, SessionLocal
    from app.services.costing_attribution import rep_username
    with SessionLocal() as db:
        rec = CalculationRecord(user_id=people["admin"]["id"], dimensions_json="{}",
                                result_json="{}", sales_rep_user_id=people["nadie"]["id"])
        db.add(rec)
        db.flush()
        assert rep_username(rec) == people["nadie"]["username"]
        rec.sales_rep_user_id = people["lezette"]["id"]
        assert rep_username(rec) == people["lezette"]["username"]
        db.rollback()


# ── capture at save: authorship kept, attribution + journal written ──────────

def test_admin_captures_a_repair_for_nadie(client, people, seeded):
    d = _save(client, people["admin"]["headers"],
              _repair(seeded, sales_rep_user_id=people["nadie"]["id"]))
    row = _row(d["record_id"])
    assert row["user_id"] == people["admin"]["id"], "authorship must never be rewritten"
    assert row["sales_rep_user_id"] == people["nadie"]["id"]
    assert d["sales_rep_user_id"] == people["nadie"]["id"]
    assert d["sales_rep_username"] == people["nadie"]["username"]
    assert _journal(d["record_id"]) == [{
        "action": "capture",
        "from_user_id": people["admin"]["id"], "from_username": "admin",
        "to_user_id": people["nadie"]["id"], "to_username": people["nadie"]["username"],
        "actor_user_id": people["admin"]["id"], "actor_username": "admin",
    }]


def test_admin_captures_a_body_costing_for_nadie(client, people, seeded):
    d = _save(client, people["admin"]["headers"],
              _body(seeded, sales_rep_user_id=people["nadie"]["id"]))
    row = _row(d["record_id"])
    assert (row["user_id"], row["sales_rep_user_id"]) == (people["admin"]["id"],
                                                          people["nadie"]["id"])
    assert [j["action"] for j in _journal(d["record_id"])] == ["capture"]


def test_the_board_row_names_the_rep_and_keeps_the_creator(client, people, seeded):
    d = _save(client, people["admin"]["headers"],
              _repair(seeded, sales_rep_user_id=people["nadie"]["id"]))
    rows = client.get("/api/calculations?limit=200", headers=people["nadie"]["headers"]).json()
    row = next(r for r in rows if r["id"] == d["record_id"])
    assert row["sales_rep"] == people["nadie"]["username"]          # the Rep column
    assert row["sales_rep_user_id"] == people["nadie"]["id"]
    assert row["captured_for"] is True
    assert row["user"] == "admin" and row["created_by_user_id"] == people["admin"]["id"]


def test_an_uncaptured_row_reads_exactly_as_before(client, people, seeded):
    d = _save(client, people["nadie"]["headers"], _repair(seeded))
    rows = client.get("/api/calculations?limit=200", headers=people["nadie"]["headers"]).json()
    row = next(r for r in rows if r["id"] == d["record_id"])
    assert row["sales_rep"] == row["user"] == people["nadie"]["username"]
    assert row["sales_rep_user_id"] == people["nadie"]["id"]
    assert row["captured_for"] is False


def test_the_detail_payload_hydrates_the_dropdown_with_the_rep(client, people, seeded):
    d = _save(client, people["admin"]["headers"],
              _body(seeded, sales_rep_user_id=people["nadie"]["id"]))
    g = client.get(f"/api/calculations/{d['record_id']}", headers=people["admin"]["headers"]).json()
    assert g["sales_rep_user_id"] == people["nadie"]["id"]
    assert g["sales_rep_username"] == people["nadie"]["username"]
    assert g["created_by_user_id"] == people["admin"]["id"]
    assert g["created_by_username"] == "admin"
    assert g["captured_for"] is True


# ── untouched dropdown == today ──────────────────────────────────────────────

_VOLATILE = ("id", "created_at", "quote_number")


def test_choosing_yourself_stores_exactly_what_no_dropdown_stores(client, people, seeded):
    """The admin's dropdown defaults to the admin. Sending that must be indistinguishable
    from a save by a calculator that has no dropdown at all: NULL, no journal, same JSON."""
    h = people["admin"]["headers"]
    with_self = _save(client, h, _body(seeded, sales_rep_user_id=people["admin"]["id"]))
    without = _save(client, h, _body(seeded))
    a, b = _row(with_self["record_id"]), _row(without["record_id"])
    assert a["sales_rep_user_id"] is None and b["sales_rep_user_id"] is None
    assert {k: v for k, v in a.items() if k not in _VOLATILE} == \
           {k: v for k, v in b.items() if k not in _VOLATILE}
    assert _journal(with_self["record_id"]) == [] and _journal(without["record_id"]) == []
    stored = json.loads(a["result_json"])
    assert not any("sales_rep" in k for k in stored), "attribution must not leak into result_json"


def test_choosing_yourself_on_a_repair_matches_a_repair_with_no_dropdown(client, people, seeded):
    h = people["admin"]["headers"]
    a = _row(_save(client, h, _repair(seeded, sales_rep_user_id=people["admin"]["id"]))["record_id"])
    b = _row(_save(client, h, _repair(seeded))["record_id"])
    assert a["sales_rep_user_id"] is None and b["sales_rep_user_id"] is None

    def _stable(row):
        res = json.loads(row["result_json"])
        # issued per save, by design (D6)
        res.pop("repair_document_number", None)
        (res.get("input_state") or {}).pop("repair_document_number", None)
        return {**{k: v for k, v in row.items() if k not in _VOLATILE + ("result_json",)},
                "result": res}
    assert _stable(a) == _stable(b)


def test_a_non_admin_naming_themselves_is_fine_and_stores_null(client, people, seeded):
    d = _save(client, people["nadie"]["headers"],
              _repair(seeded, sales_rep_user_id=people["nadie"]["id"]))
    assert _row(d["record_id"])["sales_rep_user_id"] is None
    assert _journal(d["record_id"]) == []


# ── G1: the negative controls ────────────────────────────────────────────────

def test_REFUSED_non_admin_capturing_a_new_repair_for_someone_else(client, people, seeded):
    before = _marker_count()
    r = client.post("/api/approve", headers=people["nadie"]["headers"],
                    json=_repair(seeded, sales_rep_user_id=people["lezette"]["id"]))
    assert r.status_code == 403, r.text[:400]
    assert "administrator" in r.json()["detail"]
    assert _marker_count() == before, "a refused capture must save nothing"


def test_REFUSED_non_admin_capturing_a_new_body_costing_for_someone_else(client, people, seeded):
    before = _marker_count()
    r = client.post("/api/approve", headers=people["nadie"]["headers"],
                    json=_body(seeded, sales_rep_user_id=people["lezette"]["id"]))
    assert r.status_code == 403, r.text[:400]
    assert _marker_count() == before


def test_REFUSED_before_replace_deletes_anything(client, people, seeded):
    """Replace hard-deletes the customer's earlier costings before it saves. The gate
    must run first, or a refused save would still have destroyed them."""
    keep = _save(client, people["nadie"]["headers"], _body(seeded))["record_id"]
    r = client.post("/api/approve", headers=people["nadie"]["headers"],
                    json=_body(seeded, version_action="replace",
                               sales_rep_user_id=people["lezette"]["id"]))
    assert r.status_code == 403, r.text[:400]
    assert _row(keep) is not None, "the refused Replace deleted the earlier costing"


def test_REFUSED_non_admin_reattributing_their_own_costing_by_editing_it(client, people, seeded):
    rec = _save(client, people["nadie"]["headers"], _repair(seeded))["record_id"]
    r = client.post("/api/approve", headers=people["nadie"]["headers"],
                    json=_repair(seeded, version_action="overwrite", edit_record_id=rec,
                                 repair_type="edited", sales_rep_user_id=people["lezette"]["id"]))
    assert r.status_code == 403, r.text[:400]
    row = _row(rec)
    assert row["sales_rep_user_id"] is None
    assert json.loads(row["result_json"])["repair_type"] != "edited", "refused edit was written"


def test_REFUSED_non_admin_taking_or_clearing_an_attribution_by_editing(client, people, seeded):
    """Lezette may not claim a costing captured for Nadie by naming HERSELF on an edit,
    and Nadie may not hand it back to its creator by sending null: both change who the
    costing is for, which is the admin's call."""
    rec = _save(client, people["admin"]["headers"],
                _body(seeded, sales_rep_user_id=people["nadie"]["id"]))["record_id"]
    for who, value in (("lezette", people["lezette"]["id"]), ("nadie", None)):
        r = client.post("/api/approve", headers=people[who]["headers"],
                        json=_body(seeded, version_action="overwrite", edit_record_id=rec,
                                   sales_rep_user_id=value))
        assert r.status_code == 403, (who, r.text[:400])
    assert _row(rec)["sales_rep_user_id"] == people["nadie"]["id"]
    assert [j["action"] for j in _journal(rec)] == ["capture"]


def test_REFUSED_non_admin_using_the_reassign_route(client, people, seeded):
    rec = _save(client, people["admin"]["headers"],
                _repair(seeded, sales_rep_user_id=people["nadie"]["id"]))["record_id"]
    r = client.post(f"/api/calculations/{rec}/sales-rep", headers=people["nadie"]["headers"],
                    json={"sales_rep_user_id": people["lezette"]["id"]})
    assert r.status_code == 403, r.text[:400]
    assert _row(rec)["sales_rep_user_id"] == people["nadie"]["id"]


def test_the_key_not_the_role_opens_the_gate(client, people, seeded):
    """A per-user ALLOW gives a non-admin the capability — proof the check is the
    catalogue key, not a hard-coded role."""
    from app.database import Permission, SessionLocal, UserPermission
    with SessionLocal() as db:
        perm = db.query(Permission).filter_by(name="costings.capture_for_user").first()
        db.add(UserPermission(user_id=people["other"]["id"], permission_id=perm.id,
                              effect="allow"))
        db.commit()
    try:
        d = _save(client, people["other"]["headers"],
                  _repair(seeded, sales_rep_user_id=people["nadie"]["id"]))
        assert _row(d["record_id"])["sales_rep_user_id"] == people["nadie"]["id"]
    finally:
        with SessionLocal() as db:
            db.query(UserPermission).filter_by(user_id=people["other"]["id"]).delete()
            db.commit()


def test_an_unknown_user_is_a_422_for_admin(client, people, seeded):
    r = client.post("/api/approve", headers=people["admin"]["headers"],
                    json=_repair(seeded, sales_rep_user_id=987654321))
    assert r.status_code == 422, r.text[:300]
    for bad in (True, "nadie", 1.5, {"id": 1}):
        r = client.post("/api/approve", headers=people["admin"]["headers"],
                        json=_repair(seeded, sales_rep_user_id=bad))
        assert r.status_code == 422, (bad, r.text[:300])


# ── edits keep what they don't mention ───────────────────────────────────────

def test_an_edit_without_the_field_keeps_the_attribution(client, people, seeded):
    """Calculator 2 and every non-admin calculator send no sales_rep_user_id. An edit
    through either — including by the rep herself — must leave the attribution alone."""
    rec = _save(client, people["admin"]["headers"],
                _body(seeded, sales_rep_user_id=people["nadie"]["id"]))["record_id"]
    for who in ("admin", "nadie"):
        _save(client, people[who]["headers"],
              _body(seeded, version_action="overwrite", edit_record_id=rec))
        row = _row(rec)
        assert row["sales_rep_user_id"] == people["nadie"]["id"], who
        assert row["user_id"] == people["admin"]["id"]
    assert [j["action"] for j in _journal(rec)] == ["capture"]


def test_admin_changing_the_dropdown_on_an_edit_journals_a_reassign(client, people, seeded):
    rec = _save(client, people["admin"]["headers"],
                _repair(seeded, sales_rep_user_id=people["nadie"]["id"]))["record_id"]
    _save(client, people["admin"]["headers"],
          _repair(seeded, version_action="overwrite", edit_record_id=rec,
                  sales_rep_user_id=people["lezette"]["id"]))
    assert _row(rec)["sales_rep_user_id"] == people["lezette"]["id"]
    j = _journal(rec)
    assert [x["action"] for x in j] == ["capture", "reassign"]
    assert (j[1]["from_username"], j[1]["to_username"]) == (people["nadie"]["username"],
                                                            people["lezette"]["username"])


# ── re-assign from the detail page ───────────────────────────────────────────

def test_reassign_while_pending_then_frozen_once_accepted(client, people, seeded):
    h = people["admin"]["headers"]
    rec = _save(client, h, _repair(seeded, sales_rep_user_id=people["nadie"]["id"]))["record_id"]

    g = client.get(f"/api/calculations/{rec}/sales-rep", headers=h).json()
    assert g["can_reassign"] is True and g["captured_for"] is True
    assert g["sales_rep"]["username"] == people["nadie"]["username"]
    assert g["creator"]["username"] == "admin"

    r = client.post(f"/api/calculations/{rec}/sales-rep", headers=h,
                    json={"sales_rep_user_id": people["lezette"]["id"]})
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["changed"] is True
    assert body["sales_rep"]["id"] == people["lezette"]["id"]
    assert [(x["action"], x["from_username"], x["to_username"]) for x in body["journal"]] == [
        ("capture", "admin", people["nadie"]["username"]),
        ("reassign", people["nadie"]["username"], people["lezette"]["username"]),
    ]
    # Re-choosing the current rep is not a change and journals nothing.
    again = client.post(f"/api/calculations/{rec}/sales-rep", headers=h,
                        json={"sales_rep_user_id": people["lezette"]["id"]}).json()
    assert again["changed"] is False and len(again["journal"]) == 2
    # The non-admin view offers no control.
    assert client.get(f"/api/calculations/{rec}/sales-rep",
                      headers=people["nadie"]["headers"]).json()["can_reassign"] is False

    assert client.post(f"/api/calculations/{rec}/accept", headers=h).status_code == 200
    frozen = client.post(f"/api/calculations/{rec}/sales-rep", headers=h,
                         json={"sales_rep_user_id": people["nadie"]["id"]})
    assert frozen.status_code == 409, frozen.text[:300]
    assert "frozen" in frozen.json()["detail"]
    assert _row(rec)["sales_rep_user_id"] == people["lezette"]["id"]
    assert client.get(f"/api/calculations/{rec}/sales-rep", headers=h).json()["can_reassign"] is False


def test_a_declined_costing_is_frozen_too(client, people, seeded):
    h = people["admin"]["headers"]
    rec = _save(client, h, _repair(seeded, sales_rep_user_id=people["nadie"]["id"]))["record_id"]
    assert client.post(f"/api/calculations/{rec}/decline", headers=h,
                       json={"reason": "price"}).status_code == 200
    r = client.post(f"/api/calculations/{rec}/sales-rep", headers=h,
                    json={"sales_rep_user_id": people["lezette"]["id"]})
    assert r.status_code == 409


def test_reassigning_back_to_the_creator_stores_null(client, people, seeded):
    h = people["admin"]["headers"]
    rec = _save(client, h, _repair(seeded, sales_rep_user_id=people["nadie"]["id"]))["record_id"]
    body = client.post(f"/api/calculations/{rec}/sales-rep", headers=h,
                       json={"sales_rep_user_id": None}).json()
    assert body["changed"] is True and body["captured_for"] is False
    assert body["sales_rep"]["username"] == "admin"
    assert _row(rec)["sales_rep_user_id"] is None
    assert body["journal"][-1]["to_username"] == "admin"


def test_reassign_refuses_a_deleted_costing_and_a_missing_body(client, people, seeded):
    h = people["admin"]["headers"]
    rec = _save(client, h, _repair(seeded))["record_id"]
    assert client.post(f"/api/calculations/{rec}/sales-rep", headers=h,
                       json={}).status_code == 422
    assert client.delete(f"/api/calculations/{rec}", headers=h).status_code == 200
    r = client.post(f"/api/calculations/{rec}/sales-rep", headers=h,
                    json={"sales_rep_user_id": people["nadie"]["id"]})
    assert r.status_code == 409 and "deleted" in r.json()["detail"]


def test_the_journal_survives_a_rename_and_a_deleted_user(client, people, seeded):
    """Snapshots, not joins: the line still says who it was. And a deleted rep hands the
    costing back to its creator (FK ON DELETE SET NULL), never to nobody."""
    from app.database import SessionLocal, User
    h = people["admin"]["headers"]
    temp_name = f"{_mark}_temp_{uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        temp = User(username=temp_name, password_hash="x", role="sales", email="")
        db.add(temp)
        db.commit()
        temp_id = temp.id
    rec = _save(client, h, _repair(seeded, sales_rep_user_id=temp_id))["record_id"]
    with SessionLocal() as db:
        db.get(User, temp_id).username = temp_name + "_renamed"
        db.commit()
    rows = client.get("/api/calculations?limit=200", headers=h).json()
    assert next(r for r in rows if r["id"] == rec)["sales_rep"] == temp_name + "_renamed"
    assert _journal(rec)[0]["to_username"] == temp_name        # the snapshot, unrenamed
    # Through the real Manage Users delete, which must not be refused by the costing
    # captured for this user on ANY database shape (see routers/users.delete_user).
    r = client.delete(f"/api/users/{temp_id}", headers=h)
    assert r.status_code == 200, r.text[:300]
    assert _row(rec)["user_id"] == people["admin"]["id"], "authorship must survive the delete"
    g = client.get(f"/api/calculations/{rec}/sales-rep", headers=h).json()
    assert g["captured_for"] is False and g["sales_rep"]["username"] == "admin"
    assert g["journal"][0]["to_user_id"] is None
    assert g["journal"][0]["to_username"] == temp_name


# ── the downstream reads ─────────────────────────────────────────────────────

def test_the_prejob_card_defaults_its_sales_rep_to_the_captured_for_user(people, seeded, client):
    from app.database import SessionLocal, User
    from app.models.mes import PrejobTemplate
    from app.services.prejob_cards import create_card
    rec = _save(client, people["admin"]["headers"],
                _body(seeded, sales_rep_user_id=people["nadie"]["id"]))["record_id"]
    plain = _save(client, people["lezette"]["headers"], _body(seeded))["record_id"]
    with SessionLocal() as db:
        tpl = PrejobTemplate(name=f"{_MARK} template", body_type="freezer", size_category="big",
                             product_line="standard", header_format=f"{_MARK} header",
                             sections=[{"name": "GRP SECTION", "items": [{"text": "x"}]}],
                             is_active=True, created_by="t")
        db.add(tpl)
        db.commit()
        admin = db.get(User, people["admin"]["id"])
        assert create_card(db, rec, tpl.id, admin).sales_rep_user_id == people["nadie"]["id"]
        # ...and an uncaptured costing still defaults to its creator, as before.
        assert create_card(db, plain, tpl.id, admin).sales_rep_user_id == people["lezette"]["id"]


def test_the_export_filename_names_the_rep(client, people, seeded):
    from app.database import CalculationRecord, SessionLocal
    from app.routers.exports import _doc_ctx_for_record
    rec = _save(client, people["admin"]["headers"],
                _body(seeded, sales_rep_user_id=people["nadie"]["id"]))["record_id"]
    with SessionLocal() as db:
        _ctx, stem = _doc_ctx_for_record(db.get(CalculationRecord, rec), db,
                                         detail=None, ratios_raw=None)
    assert stem.endswith("_" + people["nadie"]["username"]), stem


def test_the_legacy_dashboard_person_column_names_the_rep(client, people, seeded):
    _save(client, people["admin"]["headers"],
          _repair(seeded, sales_rep_user_id=people["nadie"]["id"]))
    html = client.get("/mes/dashboard", headers=people["admin"]["headers"]).text
    assert f"<td>{people['nadie']['username']}</td>" in html
