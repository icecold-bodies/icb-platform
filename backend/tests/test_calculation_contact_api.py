"""Customer-contacts WO — calculations contact snapshot (migration 0035) + quote-flow plumbing.

Covers: the _contact_snapshot resolver (fields, cross-customer 422, inactive 422, null
passthrough); snapshot fields serialized on GET /api/calculations/{id} and the list;
FK ondelete=SET NULL keeps the snapshot when a contact row is hard-deleted; contact
CREATE is now require_user (the calculator quick-add for sales users) while UPDATE
stays admin-gated; the report context prefers the contact for the ATTENTION line
(legacy fallback intact); all check-email variants carry "For attention of:".

House pattern (test_customer_contacts_api.py): live test DB, marker rows 'V140CC*',
module-local fixtures (NOT shared via conftest), purge on both sides.
"""
import pytest

_MARK = "V140CC"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.calculations cal USING icb_costings.customers c "
        "WHERE cal.customer_id = c.id AND c.name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text(
        "DELETE FROM icb_costings.customer_contacts cc USING icb_costings.customers c "
        "WHERE cc.customer_id = c.id AND c.name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.users WHERE username LIKE :m"), {"m": f"{_MARK.lower()}%"})
    db.commit()


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


@pytest.fixture
def api(app_mod):
    """Admin client. Dependency overrides cover the Depends-gated customers router; the
    calculator endpoints authenticate via get_current_user(request, db) INSIDE the handler,
    which no override reaches — so also mint a REAL UserSession row and send it as a raw
    Cookie header (the [[testclient-session-cookie]] house pattern: raw header, not the
    httpx jar — dot-less 'testserver' domain; expires_at=None is valid/never-expiring).
    GETs are CSRF-safe methods, so no X-CSRF-Token is needed for the reads."""
    import uuid
    from app.database import SessionLocal, User, UserSession
    from app.deps import require_admin, require_user
    from starlette.testclient import TestClient
    sid = str(uuid.uuid4())            # user_sessions.id is VARCHAR(36) — exactly a bare UUID
    with SessionLocal() as db:
        _purge(db)
        admin = db.query(User).filter_by(username="admin").first()
        db.add(UserSession(id=sid, user_id=admin.id, role=admin.role, expires_at=None))
        db.commit()
    app_mod.app.dependency_overrides[require_user] = lambda: admin
    app_mod.app.dependency_overrides[require_admin] = lambda: admin
    with TestClient(app_mod.app) as c:
        c.headers["Cookie"] = f"session_id={sid}"
        yield c
    app_mod.app.dependency_overrides.pop(require_user, None)
    app_mod.app.dependency_overrides.pop(require_admin, None)
    with SessionLocal() as db:
        db.query(UserSession).filter_by(id=sid).delete()
        db.commit()
        _purge(db)


@pytest.fixture
def cust_with_contacts():
    """Marker customer with two contacts (second one primary) + a zero-contact customer."""
    from app.database import Customer, CustomerContact, SessionLocal
    with SessionLocal() as db:
        _purge(db)
        rich = Customer(name=f"{_MARK} Rich Ltd", bp_code=f"{_MARK}1", is_active=True)
        bare = Customer(name=f"{_MARK} Bare Ltd", bp_code=f"{_MARK}2", is_active=True)
        db.add_all([rich, bare])
        db.flush()
        c1 = CustomerContact(customer_id=rich.id, name=f"{_MARK} Piet", role="Buyer",
                             email="piet@v140cc.co", telephone="011 111", is_active=True)
        c2 = CustomerContact(customer_id=rich.id, name=f"{_MARK} Sannie", role="Owner",
                             email="sannie@v140cc.co", telephone="011 222",
                             is_primary=True, is_active=True)
        dead = CustomerContact(customer_id=rich.id, name=f"{_MARK} Gone", is_active=False)
        db.add_all([c1, c2, dead])
        db.commit()
        ids = {"rich": rich.id, "bare": bare.id, "piet": c1.id, "sannie": c2.id, "dead": dead.id}
    yield ids
    with SessionLocal() as db:
        _purge(db)


def _mk_calc(db, cust_id, contact=None):
    """A minimal saved costing row (the /api/approve pipeline needs a full BOM universe the
    test DB doesn't have — persistence/serialization is exercised at the record level, the
    resolver at unit level, and the full pipeline in the live click-through)."""
    from app.database import CalculationRecord
    rec = CalculationRecord(
        customer_id=cust_id,
        dimensions_json="{}", result_json='{"items": []}', status="pending",
        contact_id=contact.id if contact is not None else None,
        contact_name=contact.name if contact is not None else None,
        contact_email=contact.email if contact is not None else None,
        contact_telephone=contact.telephone if contact is not None else None,
        contact_role=contact.role if contact is not None else None,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


# ── _contact_snapshot resolver ────────────────────────────────────────────────

def test_contact_snapshot_resolves_fields(api, cust_with_contacts):
    from app.database import SessionLocal
    from app.routers.calculator import _contact_snapshot
    ids = cust_with_contacts
    with SessionLocal() as db:
        snap = _contact_snapshot(db, ids["rich"], ids["sannie"])
    assert snap == {"contact_id": ids["sannie"], "contact_name": f"{_MARK} Sannie",
                    "contact_email": "sannie@v140cc.co", "contact_telephone": "011 222",
                    "contact_role": "Owner"}


def test_contact_snapshot_null_passthrough(api, cust_with_contacts):
    from app.database import SessionLocal
    from app.routers.calculator import _contact_snapshot
    ids = cust_with_contacts
    empty = {"contact_id": None, "contact_name": None, "contact_email": None,
             "contact_telephone": None, "contact_role": None}
    with SessionLocal() as db:
        assert _contact_snapshot(db, ids["rich"], None) == empty        # no contact picked
        assert _contact_snapshot(db, None, ids["sannie"]) == empty      # contact without customer
        assert _contact_snapshot(db, None, None) == empty


def test_contact_snapshot_guards_422(api, cust_with_contacts):
    from fastapi import HTTPException
    from app.database import SessionLocal
    from app.routers.calculator import _contact_snapshot
    ids = cust_with_contacts
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as e1:                        # someone else's contact
            _contact_snapshot(db, ids["bare"], ids["sannie"])
        assert e1.value.status_code == 422
        with pytest.raises(HTTPException) as e2:                        # soft-deleted contact
            _contact_snapshot(db, ids["rich"], ids["dead"])
        assert e2.value.status_code == 422
        with pytest.raises(HTTPException) as e3:                        # nonexistent contact
            _contact_snapshot(db, ids["rich"], 99999999)
        assert e3.value.status_code == 422


# ── Persistence + serialization ───────────────────────────────────────────────

def test_snapshot_serialized_on_get_and_list(api, cust_with_contacts):
    from app.database import CustomerContact, SessionLocal
    ids = cust_with_contacts
    with SessionLocal() as db:
        sannie = db.get(CustomerContact, ids["sannie"])
        rec = _mk_calc(db, ids["rich"], contact=sannie)
        rec_id = rec.id

    got = api.get(f"/api/calculations/{rec_id}").json()
    assert got["contact_id"] == ids["sannie"]
    assert got["contact_name"] == f"{_MARK} Sannie"
    assert got["contact_email"] == "sannie@v140cc.co"
    assert got["contact_telephone"] == "011 222"
    assert got["contact_role"] == "Owner"

    rows = api.get("/api/calculations", params={"limit": 50}).json()
    mine = next((r for r in rows if r["id"] == rec_id), None)
    assert mine is not None, "fresh record missing from the list"
    assert mine["contact_name"] == f"{_MARK} Sannie"


def test_snapshot_survives_contact_edit(api, cust_with_contacts):
    """The record keeps the WRITE-TIME values — a later rename must not rewrite history."""
    from app.database import CustomerContact, SessionLocal
    ids = cust_with_contacts
    with SessionLocal() as db:
        piet = db.get(CustomerContact, ids["piet"])
        rec = _mk_calc(db, ids["rich"], contact=piet)
        rec_id = rec.id
        piet.name = f"{_MARK} Piet RENAMED"
        piet.email = "renamed@v140cc.co"
        db.commit()

    got = api.get(f"/api/calculations/{rec_id}").json()
    assert got["contact_name"] == f"{_MARK} Piet"            # snapshot, not the live row
    assert got["contact_email"] == "piet@v140cc.co"
    assert got["contact_id"] == ids["piet"]                   # FK still points at the row


def test_contact_hard_delete_sets_null_keeps_snapshot(api, cust_with_contacts):
    """ondelete=SET NULL — a hard DELETE of the contact row nulls the FK but the
    snapshot columns keep the quote's history intact."""
    from sqlalchemy import text
    from app.database import CustomerContact, SessionLocal
    ids = cust_with_contacts
    with SessionLocal() as db:
        piet = db.get(CustomerContact, ids["piet"])
        rec = _mk_calc(db, ids["rich"], contact=piet)
        rec_id = rec.id
        db.execute(text("DELETE FROM icb_costings.customer_contacts WHERE id = :i"),
                   {"i": ids["piet"]})
        db.commit()

    got = api.get(f"/api/calculations/{rec_id}").json()
    assert got["contact_id"] is None                          # FK went NULL, no cascade
    assert got["contact_name"] == f"{_MARK} Piet"             # history preserved
    assert got["contact_email"] == "piet@v140cc.co"


# ── Contact CREATE is require_user; mutations stay admin ─────────────────────

def test_sales_user_can_quick_add_contact_but_not_edit(app_mod, cust_with_contacts):
    """The calculator's inline "+ Add now" runs as whoever is quoting (Nadie = sales).
    CREATE passes for a non-admin; UPDATE still requires admin (require_admin resolves
    the session itself — no cookie here → 401; either 401/403 proves the gate held)."""
    from app.database import SessionLocal, User
    from app.deps import require_user
    from starlette.testclient import TestClient
    ids = cust_with_contacts
    with SessionLocal() as db:
        sales = User(username=f"{_MARK.lower()}_sales", password_hash="x", role="sales")
        db.add(sales)
        db.commit()
        db.refresh(sales)
    app_mod.app.dependency_overrides[require_user] = lambda: sales
    try:
        with TestClient(app_mod.app) as c:
            created = c.post(f"/api/customers/{ids['bare']}/contacts",
                             json={"name": f"{_MARK} QuickAdd", "role": "Buyer",
                                   "email": "qa@v140cc.co", "is_primary": True})
            assert created.status_code == 200, created.text
            body = created.json()
            assert body["name"] == f"{_MARK} QuickAdd" and body["is_primary"] is True

            resp = c.put(f"/api/customers/{ids['bare']}/contacts/{body['id']}",
                         json={"name": "nope"})
            assert resp.status_code in (401, 403), "contact UPDATE must stay admin-gated"
    finally:
        app_mod.app.dependency_overrides.pop(require_user, None)


# ── PDF report context ────────────────────────────────────────────────────────

def test_report_attention_prefers_contact_with_fallback():
    from app.report_engine import build_explosive_quote_context
    base = dict(record_id=1, dimensions={}, result={}, quote_number="Q-1")

    with_contact = build_explosive_quote_context(
        customer={"name": "Rich Ltd", "email": "info@rich.co", "telephone": "011 000",
                  "contact_name": "Sannie", "contact_email": "sannie@rich.co",
                  "contact_telephone": "011 222"}, **base)
    assert with_contact["attention"] == "Sannie"
    assert with_contact["email"] == "sannie@rich.co"
    assert with_contact["tel_no"] == "011 222"

    partial = build_explosive_quote_context(
        customer={"name": "Rich Ltd", "email": "info@rich.co", "telephone": "011 000",
                  "contact_name": "Sannie", "contact_email": "", "contact_telephone": ""},
        **base)
    assert partial["attention"] == "Sannie"
    assert partial["email"] == "info@rich.co"                 # per-field fallback
    assert partial["tel_no"] == "011 000"

    legacy = build_explosive_quote_context(
        customer={"name": "Rich Ltd", "email": "info@rich.co", "telephone": "011 000"},
        **base)
    assert legacy["attention"] == "Rich Ltd"                  # pre-WO behaviour unchanged
    assert legacy["email"] == "info@rich.co"
    assert legacy["tel_no"] == "011 000"


# ── Check-email variants ──────────────────────────────────────────────────────

def _unsaved_card(calc_id: int):
    from app.models.mes import PrejobCard
    card = PrejobCard(calculation_id=calc_id)
    card.id = 999999                       # unpersisted — links only need a printable id
    return card


def test_check_emails_carry_attention_line(api, cust_with_contacts):
    from app.database import CustomerContact, SessionLocal
    from app.services.prejob_cards import build_cc_email, build_email, build_signer_email
    ids = cust_with_contacts
    with SessionLocal() as db:
        sannie = db.get(CustomerContact, ids["sannie"])
        with_c = _mk_calc(db, ids["rich"], contact=sannie)
        without = _mk_calc(db, ids["rich"], contact=None)

        line = f"For attention of: {_MARK} Sannie"
        for role in ("sales", "planner"):
            assert line in build_signer_email(db, _unsaved_card(with_c.id), "http://x", role)["body"]
        assert line in build_cc_email(db, _unsaved_card(with_c.id), "http://x")["body"]
        assert line in build_email(db, _unsaved_card(with_c.id), "http://x")["body"]

        for role in ("sales", "planner"):
            assert "For attention of" not in build_signer_email(db, _unsaved_card(without.id), "http://x", role)["body"]
        assert "For attention of" not in build_cc_email(db, _unsaved_card(without.id), "http://x")["body"]
        assert "For attention of" not in build_email(db, _unsaved_card(without.id), "http://x")["body"]
