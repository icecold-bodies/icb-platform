"""v1.49 — admin soft delete of a costing, and the guard that protects scheduled work.

Ratified by Michael 18 Aug 2026: an unscheduled repair "can be deleted but only
disappears from the costing board. It will only show if the user selects a
'Deleted' pill". A scheduled one cannot be deleted at all — it is rejected from
the Planning board instead.

The guard is the interesting part. Exactly three things reference a costing, and
before this work the endpoint (a bare db.delete) failed against two of them in
OPPOSITE ways:

    icb_costings.validated_references.calculation_id   CASCADE   (fine)
    icb_mes.prejob_cards.calculation_id                RESTRICT  (500, ugly)
    icb_mes.production_jobs.calculation_record_id      NO FK     (SILENT ORPHAN)

The last is the dangerous one, and it is worse than it looks: whether the database
protects that case DEPENDS ON WHICH DATABASE YOU ARE ON. Migration 0003 does create
fk_production_jobs_calculation_record_id (RESTRICT), and a database migrated from
scratch has it — but Michael's dev database has drifted and does NOT. A guard that
relies on the constraint would therefore be correct in CI and wrong in dev, which is
the worst possible split. So the guard asks first, and never relies on failing.

House pattern (test_calculation_end_user_api.py): live test DB, marker rows,
module-local fixtures, purge on both sides.
"""
import pytest
from sqlalchemy import text

_MARK = "V149DEL"


def _purge(db) -> None:
    db.execute(text(
        "DELETE FROM icb_mes.prejob_cards WHERE calculation_id IN ("
        " SELECT cal.id FROM icb_costings.calculations cal"
        " JOIN icb_costings.customers c ON c.id = cal.customer_id WHERE c.name LIKE :m)"),
        {"m": f"{_MARK}%"})
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
    with TestClient(m.app):
        yield m


@pytest.fixture
def api(app_mod):
    import uuid
    from app.database import SessionLocal, User, UserSession
    from app.deps import require_admin, require_user
    from starlette.testclient import TestClient
    sid = str(uuid.uuid4())
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
def repair():
    """An unscheduled REPAIRS costing: is_repair AND no trailer type."""
    import json
    from app.database import Customer, CalculationRecord, SessionLocal
    with SessionLocal() as db:
        _purge(db)
        cust = Customer(name=f"{_MARK} Carriers", bp_code=f"{_MARK}1", is_active=True)
        db.add(cust)
        db.flush()
        rec = CalculationRecord(
            trailer_type_id=None, customer_id=cust.id, is_repair=True,
            quote_number=f"{_MARK}/08/2026", dimensions_json="{}",
            result_json=json.dumps({"items": [], "grand_total": 0.0}))
        db.add(rec)
        db.commit()
        ids = (rec.id, cust.id)
    yield ids
    with SessionLocal() as db:
        _purge(db)


# ── the happy path ───────────────────────────────────────────────────────────

def test_delete_hides_it_from_the_board_without_destroying_it(api, repair):
    from app.database import SessionLocal, CalculationRecord
    rec_id, _ = repair

    assert any(r["id"] == rec_id for r in api.get("/api/calculations?limit=200").json())

    r = api.delete(f"/api/calculations/{rec_id}")
    assert r.status_code == 200, r.text[:300]

    # Gone from the board...
    assert not any(x["id"] == rec_id for x in api.get("/api/calculations?limit=200").json())
    # ...but the ROW survives. A real delete would take validated_references with
    # it and silently orphan any production job.
    with SessionLocal() as db:
        row = db.query(CalculationRecord).filter_by(id=rec_id).first()
        assert row is not None, "the row must survive — this is a SOFT delete"
        assert row.deleted_at is not None
        assert row.deleted_by, "who deleted it must be recorded"


def test_only_the_deleted_pill_shows_it(api, repair):
    rec_id, _ = repair
    api.delete(f"/api/calculations/{rec_id}")
    shown = api.get("/api/calculations?filter=deleted&limit=200").json()
    assert any(x["id"] == rec_id for x in shown)
    row = next(x for x in shown if x["id"] == rec_id)
    assert row["deleted_at"] and row["deleted_by"]


def test_a_deleted_costing_cannot_leak_back_via_another_filter(api, repair):
    """The board hides it on EVERY filter, not just the default one."""
    rec_id, _ = repair
    api.delete(f"/api/calculations/{rec_id}")
    for f in ("all", "week", "month", "pending", "repair"):
        ids = [x["id"] for x in api.get(f"/api/calculations?filter={f}&limit=200").json()]
        assert rec_id not in ids, f"filter={f} leaked a deleted costing back onto the board"


def test_restore_puts_it_back(api, repair):
    rec_id, _ = repair
    api.delete(f"/api/calculations/{rec_id}")
    r = api.post(f"/api/calculations/{rec_id}/restore")
    assert r.status_code == 200, r.text[:300]
    assert any(x["id"] == rec_id for x in api.get("/api/calculations?limit=200").json())
    assert not any(x["id"] == rec_id
                   for x in api.get("/api/calculations?filter=deleted&limit=200").json())


def test_deleting_twice_is_not_an_error(api, repair):
    """Two admins on the same row, or a double click, must not read as failure."""
    rec_id, _ = repair
    assert api.delete(f"/api/calculations/{rec_id}").status_code == 200
    second = api.delete(f"/api/calculations/{rec_id}")
    assert second.status_code == 200
    assert second.json().get("already_deleted") is True


# ── the guard ────────────────────────────────────────────────────────────────

def test_a_costing_with_a_prejob_card_is_refused(api, repair):
    """RESTRICT would have made this a 500. It must be a readable 409."""
    from app.database import SessionLocal
    rec_id, _ = repair
    with SessionLocal() as db:
        db.execute(text(
            "INSERT INTO icb_mes.prejob_cards (calculation_id, status, sections, created_at) "
            "VALUES (:i, 'draft', '{}', now())"), {"i": rec_id})
        db.commit()
    r = api.delete(f"/api/calculations/{rec_id}")
    assert r.status_code == 409, r.text[:300]
    assert "Pre-Job Card" in r.json()["detail"]
    # and it is still on the board, untouched
    assert any(x["id"] == rec_id for x in api.get("/api/calculations?limit=200").json())


def test_a_scheduled_costing_is_refused_and_named(api, repair):
    """The silent-orphan case: production_jobs has NO FK, so nothing but this
    guard stops the job being cut loose from its costing."""
    from app.database import SessionLocal
    rec_id, _ = repair
    with SessionLocal() as db:
        branch = db.execute(text("SELECT id FROM icb_costings.branches LIMIT 1")).scalar()
        db.execute(text(
            "INSERT INTO icb_mes.production_jobs (calculation_record_id, branch_id, "
            " job_number, status, created_at) VALUES (:i, :b, :j, 'accepted', now())"),
            {"i": rec_id, "b": branch, "j": f"{_MARK}-JOB"})
        db.commit()
    r = api.delete(f"/api/calculations/{rec_id}")
    assert r.status_code == 409, r.text[:300]
    detail = r.json()["detail"]
    assert f"{_MARK}-JOB" in detail, f"the refusal must name the job: {detail}"
    assert "Planning" in detail, "it should point the admin at the Planning board"


def test_the_guard_does_not_depend_on_the_database_having_the_foreign_key():
    """The guard must refuse BEFORE the database gets a chance to — because on
    some databases it would not.

    Discovered while writing this: `fk_production_jobs_calculation_record_id`
    (RESTRICT) IS created by migration 0003 and IS present on a database migrated
    from scratch — but it is ABSENT from Michael's dev database, which has drifted.
    So whether the DB protects this case depends on which database you are on,
    which is no protection at all.

    This asserts the property that holds either way: costing_delete_blockers names
    the job from a plain SELECT, with no write attempted and no reliance on a
    constraint existing. test_a_scheduled_costing_is_refused_and_named proves the
    behaviour end to end; this pins the mechanism.
    """
    import inspect
    from app.routers.calculator import costing_delete_blockers

    src = inspect.getsource(costing_delete_blockers)
    assert "production_jobs" in src and "SELECT" in src,         "the guard must ASK about production jobs, not discover them by failing"
    body = src.split('"""')[2]          # skip the docstring; it discusses deletes
    for verb in ("db.delete", "UPDATE ", "INSERT ", "DELETE FROM"):
        assert verb not in body, f"the guard must not mutate anything (found {verb!r})"
