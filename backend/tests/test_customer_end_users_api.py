"""WO v1.47 lane B — customer end-users CRUD (migration 0040).

The END USER is ICB's customer's customer: the body is often sold through a reseller or
middleman and is actually FOR someone else. One row = the end-user COMPANY plus its
contact PERSON.

Covers: list (active only, primary first); create (require_user — the calculator's inline
quick-add) with company_name required; update / set-primary / delete admin-gated; the
one-primary-per-customer partial unique index surviving a demote+promote in one request;
soft-delete freeing the primary slot; and CASCADE when the customer row is hard-deleted.

House pattern (test_customer_contacts_api.py): live test DB, marker rows 'V147EU*',
module-local fixtures (NOT shared via conftest), purge on both sides.
"""
import pytest

_MARK = "V147EU"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.calculations cal USING icb_costings.customers c "
        "WHERE cal.customer_id = c.id AND c.name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text(
        "DELETE FROM icb_costings.customer_end_users eu USING icb_costings.customers c "
        "WHERE eu.customer_id = c.id AND c.name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.users WHERE username LIKE :m"),
               {"m": f"{_MARK.lower()}%"})
    db.commit()


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


@pytest.fixture
def api(app_mod):
    """Admin client — dependency overrides cover the Depends-gated customers router."""
    from app.database import SessionLocal, User
    from app.deps import require_admin, require_user
    from starlette.testclient import TestClient
    with SessionLocal() as db:
        _purge(db)
        admin = db.query(User).filter_by(username="admin").first()
    app_mod.app.dependency_overrides[require_user] = lambda: admin
    app_mod.app.dependency_overrides[require_admin] = lambda: admin
    with TestClient(app_mod.app) as c:
        yield c
    app_mod.app.dependency_overrides.pop(require_user, None)
    app_mod.app.dependency_overrides.pop(require_admin, None)
    with SessionLocal() as db:
        _purge(db)


@pytest.fixture
def cust():
    from app.database import Customer, SessionLocal
    with SessionLocal() as db:
        _purge(db)
        c = Customer(name=f"{_MARK} Reseller Ltd", bp_code=f"{_MARK}1", is_active=True)
        db.add(c)
        db.commit()
        cid = c.id
    yield cid
    with SessionLocal() as db:
        _purge(db)


# ── create ────────────────────────────────────────────────────────────────────

def test_create_requires_company_name(api, cust):
    r = api.post(f"/api/customers/{cust}/end-users", json={"contact_name": "Nobody"})
    assert r.status_code == 400, r.text


def test_create_returns_the_company_and_its_person(api, cust):
    r = api.post(f"/api/customers/{cust}/end-users", json={
        "company_name": f"{_MARK} ACME Foods", "contact_name": "Thabo",
        "contact_role": "Fleet", "contact_email": "thabo@acme.co",
        "contact_telephone": "011 999", "is_primary": True})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["company_name"] == f"{_MARK} ACME Foods"
    assert b["contact_name"] == "Thabo" and b["contact_role"] == "Fleet"
    assert b["contact_email"] == "thabo@acme.co" and b["contact_telephone"] == "011 999"
    assert b["is_primary"] is True and b["active"] is True


def test_unknown_customer_404s(api):
    r = api.post("/api/customers/99999999/end-users", json={"company_name": "X"})
    assert r.status_code == 404


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_is_active_only_primary_first(api, cust):
    api.post(f"/api/customers/{cust}/end-users", json={"company_name": f"{_MARK} Bravo"})
    prim = api.post(f"/api/customers/{cust}/end-users",
                    json={"company_name": f"{_MARK} Alpha", "is_primary": True}).json()
    gone = api.post(f"/api/customers/{cust}/end-users",
                    json={"company_name": f"{_MARK} Deleted"}).json()
    assert api.delete(f"/api/customers/{cust}/end-users/{gone['id']}").status_code == 200

    rows = api.get(f"/api/customers/{cust}/end-users").json()
    names = [r["company_name"] for r in rows]
    assert names == [f"{_MARK} Alpha", f"{_MARK} Bravo"], names   # primary first, then by name
    assert rows[0]["id"] == prim["id"]


# ── one primary per customer (the partial unique index) ───────────────────────

def test_second_create_as_primary_demotes_the_first(api, cust):
    """Demote-then-promote inside ONE request: without the flush in
    _clear_primary_end_user the INSERT would race the UPDATE and hit
    uq_customer_end_users_one_primary."""
    a = api.post(f"/api/customers/{cust}/end-users",
                 json={"company_name": f"{_MARK} First", "is_primary": True}).json()
    b = api.post(f"/api/customers/{cust}/end-users",
                 json={"company_name": f"{_MARK} Second", "is_primary": True})
    assert b.status_code == 200, b.text
    rows = {r["id"]: r for r in api.get(f"/api/customers/{cust}/end-users").json()}
    assert rows[a["id"]]["is_primary"] is False
    assert rows[b.json()["id"]]["is_primary"] is True


def test_set_primary_moves_the_flag(api, cust):
    a = api.post(f"/api/customers/{cust}/end-users",
                 json={"company_name": f"{_MARK} A", "is_primary": True}).json()
    b = api.post(f"/api/customers/{cust}/end-users",
                 json={"company_name": f"{_MARK} B"}).json()
    assert api.post(f"/api/customers/{cust}/end-users/{b['id']}/set-primary",
                    json={}).status_code == 200
    rows = {r["id"]: r for r in api.get(f"/api/customers/{cust}/end-users").json()}
    assert rows[a["id"]]["is_primary"] is False and rows[b["id"]]["is_primary"] is True


def test_update_to_primary_demotes_the_other(api, cust):
    a = api.post(f"/api/customers/{cust}/end-users",
                 json={"company_name": f"{_MARK} A", "is_primary": True}).json()
    b = api.post(f"/api/customers/{cust}/end-users",
                 json={"company_name": f"{_MARK} B"}).json()
    r = api.put(f"/api/customers/{cust}/end-users/{b['id']}", json={"is_primary": True})
    assert r.status_code == 200, r.text
    rows = {x["id"]: x for x in api.get(f"/api/customers/{cust}/end-users").json()}
    assert rows[a["id"]]["is_primary"] is False and rows[b["id"]]["is_primary"] is True


# ── update / delete ───────────────────────────────────────────────────────────

def test_update_edits_fields_and_rejects_blank_company(api, cust):
    e = api.post(f"/api/customers/{cust}/end-users",
                 json={"company_name": f"{_MARK} Old", "contact_name": "Old Person"}).json()
    r = api.put(f"/api/customers/{cust}/end-users/{e['id']}",
                json={"company_name": f"{_MARK} New", "contact_name": "New Person",
                      "contact_email": "new@x.co"})
    assert r.status_code == 200, r.text
    assert r.json()["company_name"] == f"{_MARK} New"
    assert r.json()["contact_name"] == "New Person"
    assert api.put(f"/api/customers/{cust}/end-users/{e['id']}",
                   json={"company_name": "   "}).status_code == 400


def test_soft_delete_hides_it_and_frees_the_primary_slot(api, cust):
    a = api.post(f"/api/customers/{cust}/end-users",
                 json={"company_name": f"{_MARK} A", "is_primary": True}).json()
    assert api.delete(f"/api/customers/{cust}/end-users/{a['id']}").status_code == 200
    assert api.get(f"/api/customers/{cust}/end-users").json() == []
    # The freed slot is immediately reusable — the delete drops is_primary too.
    b = api.post(f"/api/customers/{cust}/end-users",
                 json={"company_name": f"{_MARK} B", "is_primary": True})
    assert b.status_code == 200, b.text


def test_wrong_customer_404s(api, cust):
    from app.database import Customer, SessionLocal
    e = api.post(f"/api/customers/{cust}/end-users",
                 json={"company_name": f"{_MARK} Mine"}).json()
    with SessionLocal() as db:
        other = Customer(name=f"{_MARK} Other Ltd", is_active=True)
        db.add(other)
        db.commit()
        other_id = other.id
    assert api.put(f"/api/customers/{other_id}/end-users/{e['id']}",
                   json={"company_name": "hack"}).status_code == 404
    assert api.delete(f"/api/customers/{other_id}/end-users/{e['id']}").status_code == 404


# ── permission split (mirrors the contacts gate) ──────────────────────────────

def test_sales_user_can_quick_add_but_not_edit(app_mod, cust):
    """The calculator's inline "+" runs as whoever is quoting (Nadie = sales). CREATE
    passes for a non-admin; UPDATE / set-primary / DELETE stay admin-gated (require_admin
    resolves the session itself — no cookie here → 401; 401/403 both prove the gate)."""
    from app.database import SessionLocal, User
    from app.deps import require_user
    from starlette.testclient import TestClient
    with SessionLocal() as db:
        sales = User(username=f"{_MARK.lower()}_sales", password_hash="x", role="sales")
        db.add(sales)
        db.commit()
        db.refresh(sales)
    app_mod.app.dependency_overrides[require_user] = lambda: sales
    try:
        with TestClient(app_mod.app) as c:
            created = c.post(f"/api/customers/{cust}/end-users",
                             json={"company_name": f"{_MARK} QuickAdd", "is_primary": True})
            assert created.status_code == 200, created.text
            eid = created.json()["id"]
            assert c.put(f"/api/customers/{cust}/end-users/{eid}",
                         json={"company_name": "nope"}).status_code in (401, 403)
            assert c.post(f"/api/customers/{cust}/end-users/{eid}/set-primary",
                          json={}).status_code in (401, 403)
            assert c.delete(f"/api/customers/{cust}/end-users/{eid}").status_code in (401, 403)
    finally:
        app_mod.app.dependency_overrides.pop(require_user, None)


# ── cascade ───────────────────────────────────────────────────────────────────

def test_customer_hard_delete_cascades_end_users(api, cust):
    """FK ondelete=CASCADE — an end-user row is meaningless without its customer. Quote
    history is unaffected: the costing carries its own snapshot (see the sibling test
    module's SET NULL case)."""
    from sqlalchemy import text
    from app.database import SessionLocal
    e = api.post(f"/api/customers/{cust}/end-users",
                 json={"company_name": f"{_MARK} Doomed"}).json()
    with SessionLocal() as db:
        db.execute(text("DELETE FROM icb_costings.customers WHERE id = :i"), {"i": cust})
        db.commit()
        left = db.execute(text("SELECT count(*) FROM icb_costings.customer_end_users "
                               "WHERE id = :i"), {"i": e["id"]}).scalar()
    assert left == 0, "end-user row survived its customer's hard delete"
