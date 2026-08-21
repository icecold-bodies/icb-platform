"""v1.50 — Internal Sales ('full') may soft-delete its OWN untouched draft.

Michael ratified widening the v1.49 admin-only soft delete on 20 Aug 2026, and
ratified it TIGHTLY: holding `costings.delete_own_draft` is permission to delete
your own pending, unscheduled costing, not permission to delete. Four conditions,
all of which must hold, and this module states each one as its own refusal.

Why the key rather than a role check: a role hardcode would have to be repeated
at every surface and would put Internal Sales' own rules outside the permission
system, where nobody administering the site can see them. The key is seeded
{admin, full} exactly like costings.price_master_edit (#115) and
costings.validated_refs_manage (#121), so the catalogue is the whole statement.

The other half of the ratification is the NEGATIVE space, which is why admin has
its own tests here: widening a gate is the easiest way to accidentally narrow it
(fold the new conditions in for everyone and admin can suddenly only delete its
own drafts). Admin's cases are asserted unchanged. RESTORE is asserted still
admin-only — undelete is a correction, not a sales action.

House pattern (test_costing_soft_delete.py): live test DB, marker rows,
module-local fixtures, purge on both sides.
"""
import uuid

import pytest
from sqlalchemy import text

_MARK = "V150OWN"


def _purge(db) -> None:
    db.execute(text(
        "DELETE FROM icb_mes.production_jobs WHERE calculation_record_id IN ("
        " SELECT cal.id FROM icb_costings.calculations cal"
        " JOIN icb_costings.customers c ON c.id = cal.customer_id WHERE c.name LIKE :m)"),
        {"m": f"{_MARK}%"})
    db.execute(text(
        "DELETE FROM icb_costings.calculations cal USING icb_costings.customers c "
        "WHERE cal.customer_id = c.id AND c.name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.customers WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    # Entering the client runs startup, and startup is what seeds the new
    # catalogue key + its {admin, full} grants into this database.
    with TestClient(m.app):
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


def _session_for(user_id: int, role: str) -> dict:
    """A REAL session row. The route resolves the session itself rather than
    through Depends, so a dependency_override would not reach it — and a test
    that overrode the gate could not see the gate."""
    from app.database import SessionLocal, UserSession
    sid = f"v150-{uuid.uuid4().hex[:12]}"
    with SessionLocal() as db:
        db.merge(UserSession(id=sid, user_id=user_id, role=role, expires_at=None,
                             csrf_token=f"csrf-{sid}"))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": f"csrf-{sid}"}


@pytest.fixture(scope="module")
def people(app_mod):
    """Nadie (role 'full'), a second 'full' colleague, and admin."""
    from app.database import SessionLocal, User, UserSession
    names = {}
    out = {}
    with SessionLocal() as db:
        for who in ("sales", "other"):
            uname = f"t150_{who}_{uuid.uuid4().hex[:6]}"
            db.add(User(username=uname, password_hash="x", role="full", email=""))
            names[who] = uname
        db.commit()
        for who, uname in names.items():
            u = db.query(User).filter_by(username=uname).first()
            out[who] = {"id": u.id, "username": uname,
                        "headers": _session_for(u.id, "full")}
        a = db.query(User).filter_by(username="admin").first()
        out["admin"] = {"id": a.id, "username": a.username,
                        "headers": _session_for(a.id, a.role)}
    yield out
    with SessionLocal() as db:
        for who in ("sales", "other", "admin"):
            sid = out[who]["headers"]["Cookie"].split("session_id=")[1]
            db.query(UserSession).filter_by(id=sid).delete()
        for who in ("sales", "other"):
            db.query(User).filter_by(id=out[who]["id"]).delete()
        db.commit()


def _make(owner_id: int, status: str = "pending", **extra) -> int:
    """A costing owned by `owner_id`. Returns its id."""
    import json
    from app.database import Customer, CalculationRecord, SessionLocal
    with SessionLocal() as db:
        cust = db.query(Customer).filter_by(name=f"{_MARK} Carriers").first()
        if not cust:
            cust = Customer(name=f"{_MARK} Carriers", bp_code=f"{_MARK}1", is_active=True)
            db.add(cust)
            db.flush()
        rec = CalculationRecord(
            trailer_type_id=None, customer_id=cust.id, is_repair=True,
            user_id=owner_id, status=status,
            quote_number=f"{_MARK}/{uuid.uuid4().hex[:6]}/2026",
            dimensions_json="{}",
            result_json=json.dumps({
                "items": [], "category_totals": {}, "category_multipliers": {},
                "materials_total": 0.0, "cost_per_sqm": 0.0, "geometry": {},
                "chassis": None, "profit_amount": 0.0, "profit_margin": 0.0,
                "ratio_value": 1.0, "ratio_label": "100%", "ratio_amount": 0.0,
                "grand_total": 0.0, "selling_price": 0.0, "net_total": 0.0,
            }),
            **extra)
        db.add(rec)
        db.commit()
        return rec.id


@pytest.fixture(autouse=True)
def _clean():
    from app.database import SessionLocal
    with SessionLocal() as db:
        _purge(db)
    yield
    with SessionLocal() as db:
        _purge(db)


def _deleted_at(rec_id: int):
    from app.database import SessionLocal, CalculationRecord
    with SessionLocal() as db:
        return db.query(CalculationRecord).filter_by(id=rec_id).first().deleted_at


# ── the key itself ───────────────────────────────────────────────────────────

def test_the_key_is_in_the_catalogue_and_granted_to_full(app_mod):
    """A gate string that is not a catalogue key is INVISIBLE: admin passes on the
    code-level wildcard, so a typo here would look like a working feature right up
    until a non-admin tried it."""
    from app.database import PERMISSION_CATALOGUE
    row = [r for r in PERMISSION_CATALOGUE if r[0] == "costings.delete_own_draft"]
    assert row, "costings.delete_own_draft is missing from PERMISSION_CATALOGUE"
    assert row[0][3] == {"admin", "full"}


def test_startup_granted_it_to_the_full_role(app_mod):
    """The catalogue is only a statement until the boot-time bootstrap seeds it."""
    from app.database import SessionLocal
    with SessionLocal() as db:
        granted = db.execute(text(
            "SELECT 1 FROM icb_costings.role_permissions rp "
            "JOIN icb_costings.permissions p ON p.id = rp.permission_id "
            "WHERE rp.role = 'full' AND p.name = 'costings.delete_own_draft'")).first()
    assert granted, "role 'full' never received the grant at startup"


# ── the one case that is allowed ─────────────────────────────────────────────

def test_full_role_deletes_its_own_pending_draft(client, people):
    rec_id = _make(people["sales"]["id"])
    r = client.delete(f"/api/calculations/{rec_id}", headers=people["sales"]["headers"])
    assert r.status_code == 200, r.text[:400]
    assert _deleted_at(rec_id) is not None
    # ...and it is off the board, exactly as an admin delete leaves it.
    ids = [x["id"] for x in client.get("/api/calculations?limit=200",
                                       headers=people["sales"]["headers"]).json()]
    assert rec_id not in ids


# ── the refusals ─────────────────────────────────────────────────────────────

def test_full_role_may_not_delete_someone_elses_draft(client, people):
    rec_id = _make(people["other"]["id"])
    r = client.delete(f"/api/calculations/{rec_id}", headers=people["sales"]["headers"])
    assert r.status_code == 403, r.text[:400]
    assert people["other"]["username"] in r.json()["detail"], \
        "the refusal must name whose costing it is"
    assert _deleted_at(rec_id) is None


def test_full_role_may_not_delete_an_accepted_costing(client, people):
    rec_id = _make(people["sales"]["id"], status="accepted")
    r = client.delete(f"/api/calculations/{rec_id}", headers=people["sales"]["headers"])
    assert r.status_code == 403, r.text[:400]
    assert "accepted" in r.json()["detail"].lower()
    assert _deleted_at(rec_id) is None


def test_full_role_may_not_delete_a_declined_costing(client, people):
    """Not-pending, not merely not-accepted: a decline records the customer's
    answer and is not a draft either."""
    rec_id = _make(people["sales"]["id"], status="declined")
    r = client.delete(f"/api/calculations/{rec_id}", headers=people["sales"]["headers"])
    assert r.status_code == 403, r.text[:400]
    assert _deleted_at(rec_id) is None


def test_full_role_may_not_delete_a_pre_job_sent_costing(client, people):
    from datetime import datetime, timezone
    rec_id = _make(people["sales"]["id"], status="pre_job_sent",
                   pre_job_sent_at=datetime.now(timezone.utc))
    r = client.delete(f"/api/calculations/{rec_id}", headers=people["sales"]["headers"])
    assert r.status_code == 403, r.text[:400]
    assert _deleted_at(rec_id) is None


def test_full_role_may_not_delete_a_scheduled_costing(client, people):
    """Still PENDING and still theirs, but a job is on the floor. The v1.49 guard
    is the one that speaks here, and it must not have been bypassed by the new
    permission path."""
    from app.database import SessionLocal
    rec_id = _make(people["sales"]["id"])
    with SessionLocal() as db:
        branch = db.execute(text("SELECT id FROM icb_costings.branches LIMIT 1")).scalar()
        db.execute(text(
            "INSERT INTO icb_mes.production_jobs (calculation_record_id, branch_id, "
            " job_number, status, created_at) VALUES (:i, :b, :j, 'accepted', now())"),
            {"i": rec_id, "b": branch, "j": f"{_MARK}-JOB"})
        db.commit()
    r = client.delete(f"/api/calculations/{rec_id}", headers=people["sales"]["headers"])
    assert r.status_code == 409, r.text[:400]
    assert "scheduled" in r.json()["detail"].lower()
    assert _deleted_at(rec_id) is None


def test_a_user_without_the_key_is_refused_outright(client, people):
    """A role with no grant does not reach the own-draft conditions at all — it is
    refused at the door, with the same wording as before v1.50."""
    from app.database import SessionLocal, User, UserSession
    uname = f"t150_prod_{uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        db.add(User(username=uname, password_hash="x", role="production", email=""))
        db.commit()
        uid = db.query(User).filter_by(username=uname).first().id
    headers = _session_for(uid, "production")
    try:
        rec_id = _make(uid)          # their OWN pending draft — still refused
        r = client.delete(f"/api/calculations/{rec_id}", headers=headers)
        assert r.status_code == 403, r.text[:400]
        assert _deleted_at(rec_id) is None
    finally:
        # calculations.user_id FKs users: the costing must go FIRST, or the user
        # DELETE raises a ForeignKeyViolation and the teardown fails the test it
        # was cleaning up after.
        with SessionLocal() as db:
            _purge(db)
            db.query(UserSession).filter_by(
                id=headers["Cookie"].split("session_id=")[1]).delete()
            db.query(User).filter_by(id=uid).delete()
            db.commit()


# ── admin is unchanged ───────────────────────────────────────────────────────

def test_admin_still_deletes_a_costing_it_did_not_create(client, people):
    rec_id = _make(people["sales"]["id"])
    r = client.delete(f"/api/calculations/{rec_id}", headers=people["admin"]["headers"])
    assert r.status_code == 200, r.text[:400]
    assert _deleted_at(rec_id) is not None


def test_admin_still_deletes_an_accepted_costing(client, people):
    """The narrowing risk: the new conditions must apply to NON-admins only."""
    rec_id = _make(people["sales"]["id"], status="accepted")
    r = client.delete(f"/api/calculations/{rec_id}", headers=people["admin"]["headers"])
    assert r.status_code == 200, r.text[:400]
    assert _deleted_at(rec_id) is not None


def test_admin_is_still_refused_on_scheduled_work(client, people):
    """Admin's ONE limit, from v1.49, still holds."""
    from app.database import SessionLocal
    rec_id = _make(people["sales"]["id"])
    with SessionLocal() as db:
        branch = db.execute(text("SELECT id FROM icb_costings.branches LIMIT 1")).scalar()
        db.execute(text(
            "INSERT INTO icb_mes.production_jobs (calculation_record_id, branch_id, "
            " job_number, status, created_at) VALUES (:i, :b, :j, 'accepted', now())"),
            {"i": rec_id, "b": branch, "j": f"{_MARK}-JOB2"})
        db.commit()
    r = client.delete(f"/api/calculations/{rec_id}", headers=people["admin"]["headers"])
    assert r.status_code == 409, r.text[:400]


# ── restore stays admin-only ─────────────────────────────────────────────────

def test_restore_is_still_admin_only(client, people):
    """The key widens DELETE and nothing else. A full-role user who deleted their
    own draft cannot put it back — that is a correction, and corrections are the
    administrator's."""
    rec_id = _make(people["sales"]["id"])
    assert client.delete(f"/api/calculations/{rec_id}",
                         headers=people["sales"]["headers"]).status_code == 200
    r = client.post(f"/api/calculations/{rec_id}/restore",
                    headers=people["sales"]["headers"])
    assert r.status_code == 403, r.text[:400]
    assert _deleted_at(rec_id) is not None, "a refused restore must not have restored it"
    # ...and admin still can.
    assert client.post(f"/api/calculations/{rec_id}/restore",
                       headers=people["admin"]["headers"]).status_code == 200
    assert _deleted_at(rec_id) is None
