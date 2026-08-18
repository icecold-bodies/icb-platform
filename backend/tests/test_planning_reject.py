"""v1.49 — Reject a job from the Planning board.

Michael: "if the job has been scheduled it should be showing on the Planning page
where the option should be to 'Reject' the job."

Reject is the sanctioned way OUT of a scheduled repair. A costing with a
production job cannot be soft-deleted, deliberately — nobody should be able to
delete work off the floor by right-clicking a list. Rejecting is the reviewed
path, and it closes the loop: reject, and the costing becomes deletable.

It is NOT revert-to-unscheduled, which is slot-only and keeps the job as work ICB
still intends to do.

The job row is MARKED, never deleted: deleting it would cascade away
production_jobs_audit (including reject's own audit row) and null out
floor_events.production_job_id. The board needs no help — its pool selects
status == 'planning', so a rejected job stops matching.

House pattern: live test DB, marker rows, module-local fixtures, purge both sides.
"""
import json

import pytest
from sqlalchemy import text

_MARK = "V149REJ"


def _purge(db) -> None:
    db.execute(text(
        "DELETE FROM icb_mes.planning_slots WHERE production_job_id IN ("
        " SELECT j.id FROM icb_mes.production_jobs j"
        " JOIN icb_costings.calculations cal ON cal.id = j.calculation_record_id"
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
    from starlette.testclient import TestClient
    # No dependency_overrides here, unlike the sibling costing tests. The reject
    # endpoint is gated by require_permission("planning.unschedule"), a dependency
    # FACTORY that an override cannot target by name — and overriding require_user
    # with a detached User then blows up inside it. A real session cookie exercises
    # the true auth path, and admin passes every gate via the user_can wildcard.
    sid = str(uuid.uuid4())
    with SessionLocal() as db:
        _purge(db)
        admin = db.query(User).filter_by(username="admin").first()
        db.add(UserSession(id=sid, user_id=admin.id, role=admin.role, expires_at=None))
        db.commit()
    with TestClient(app_mod.app) as c:
        c.headers["Cookie"] = f"session_id={sid}"
        yield c
    with SessionLocal() as db:
        db.query(UserSession).filter_by(id=sid).delete()
        db.commit()
        _purge(db)


@pytest.fixture
def planned_repair():
    """A repair sitting in the board's unscheduled pool: job status 'planning'."""
    from app.database import Customer, CalculationRecord, SessionLocal
    from app.models.mes import ProductionJob
    with SessionLocal() as db:
        _purge(db)
        cust = Customer(name=f"{_MARK} Carriers", bp_code=f"{_MARK}1", is_active=True)
        db.add(cust)
        db.flush()
        rec = CalculationRecord(
            trailer_type_id=None, customer_id=cust.id, is_repair=True, status="planning",
            quote_number=f"{_MARK}/08/2026", dimensions_json="{}",
            result_json=json.dumps({"items": [], "grand_total": 0.0}))
        db.add(rec)
        db.flush()
        branch = db.execute(text("SELECT id FROM icb_costings.branches LIMIT 1")).scalar()
        job = ProductionJob(calculation_record_id=rec.id, branch_id=branch,
                            job_number=f"{_MARK}J", status="planning")
        db.add(job)
        db.commit()
        ids = (rec.id, job.id)
    yield ids
    with SessionLocal() as db:
        _purge(db)


REASON = "Customer withdrew the repair"


def test_rejecting_takes_the_job_off_the_board(api, planned_repair):
    """The board's own pool query must stop returning it."""
    from app.database import SessionLocal
    from app.services import planning
    _rec_id, job_id = planned_repair

    with SessionLocal() as db:
        before = planning._unscheduled_pool(db)
    assert any(getattr(j, "id", None) == job_id or getattr(j, "job_id", None) == job_id
               for j in before), "fixture should start on the board"

    r = api.post(f"/api/production-jobs/{job_id}/reject", json={"reason": REASON})
    assert r.status_code == 200, r.text[:300]

    with SessionLocal() as db:
        after = planning._unscheduled_pool(db)
    assert not any(getattr(j, "id", None) == job_id or getattr(j, "job_id", None) == job_id
                   for j in after), "a rejected job must leave the board"


def test_the_costing_reads_as_Rejected(api, planned_repair):
    """'declined' is what the costings board already renders as "Rejected", so the
    planner's decision arrives in the vocabulary the app already uses."""
    rec_id, job_id = planned_repair
    api.post(f"/api/production-jobs/{job_id}/reject", json={"reason": REASON})
    rows = api.get("/api/calculations?limit=200").json()
    row = next(x for x in rows if x["id"] == rec_id)
    assert row["status"] == "declined"
    assert row["mes_status"] == "Rejected"
    assert row["decline_reason"] == REASON


def test_the_job_row_is_marked_not_deleted(api, planned_repair):
    """Deleting it would cascade away production_jobs_audit — including reject's
    own audit row — and null out floor_events.production_job_id."""
    from app.database import SessionLocal
    from app.models.mes import ProductionJob
    _rec_id, job_id = planned_repair
    api.post(f"/api/production-jobs/{job_id}/reject", json={"reason": REASON})
    with SessionLocal() as db:
        job = db.get(ProductionJob, job_id)
        assert job is not None, "the job row must survive"
        assert job.status == "rejected"
        audit = db.execute(text(
            "SELECT action, previous_status, new_status, reason FROM icb_mes.production_jobs_audit "
            "WHERE production_job_id = :i AND action = 'reject'"), {"i": job_id}).first()
    assert audit is not None, "the transition must be audited"
    assert audit[1] == "planning" and audit[2] == "rejected"
    assert audit[3] == REASON


def test_rejecting_makes_the_costing_deletable(api, planned_repair):
    """The loop closes: scheduled work cannot be deleted, but rejected work can."""
    rec_id, job_id = planned_repair

    blocked = api.delete(f"/api/calculations/{rec_id}")
    assert blocked.status_code == 409, "a scheduled costing must not be deletable"
    assert f"{_MARK}J" in blocked.json()["detail"]

    api.post(f"/api/production-jobs/{job_id}/reject", json={"reason": REASON})

    ok = api.delete(f"/api/calculations/{rec_id}")
    assert ok.status_code == 200, ok.text[:300]
    assert not any(x["id"] == rec_id for x in api.get("/api/calculations?limit=200").json())


def test_a_reason_is_required(api, planned_repair):
    """Declining a costing has always required one, and the reason is what the
    costing shows to whoever asks why planned work disappeared."""
    _rec_id, job_id = planned_repair
    for body in ({"reason": ""}, {"reason": "   "}, {"reason": None}):
        r = api.post(f"/api/production-jobs/{job_id}/reject", json=body)
        assert r.status_code == 409, f"{body} should be refused, got {r.status_code}"
        assert "reason" in r.json()["detail"].lower()


def test_a_scheduled_job_is_unslotted_through_the_guarded_chokepoint(api, planned_repair):
    """A job on the GRID must lose its slot, and must do so through the same
    guarded path as the drag — not by a second, unchecked delete."""
    from app.database import SessionLocal
    from app.models.mes import PlanningSlot
    import datetime as _dt
    _rec_id, job_id = planned_repair
    with SessionLocal() as db:
        monday = _dt.date(2026, 8, 17)
        db.add(PlanningSlot(production_job_id=job_id, week=monday, bay="VAC-1",
                            lane="vacuum", slot_position=1, day_of_week=0,
                            status="scheduled"))
        db.commit()

    r = api.post(f"/api/production-jobs/{job_id}/reject", json={"reason": REASON})
    assert r.status_code == 200, r.text[:300]

    with SessionLocal() as db:
        left = db.execute(text(
            "SELECT count(*) FROM icb_mes.planning_slots WHERE production_job_id = :i"),
            {"i": job_id}).scalar()
        # the chokepoint writes its own audit row before deleting the slot
        revert = db.execute(text(
            "SELECT count(*) FROM icb_mes.production_jobs_audit "
            "WHERE production_job_id = :i AND action = 'revert_to_unscheduled'"),
            {"i": job_id}).scalar()
    assert left == 0, "the slot must be released"
    assert revert == 1, "unslotting must route through the guarded chokepoint, which audits"


def test_a_job_that_has_left_planning_cannot_be_rejected(api, planned_repair):
    """Same whitelist the revert path uses — once the workshop has it, it is theirs."""
    from app.database import SessionLocal
    from app.models.mes import ProductionJob
    _rec_id, job_id = planned_repair
    with SessionLocal() as db:
        db.get(ProductionJob, job_id).status = "in_production"
        db.commit()
    r = api.post(f"/api/production-jobs/{job_id}/reject", json={"reason": REASON})
    assert r.status_code == 409, r.text[:300]
    assert "in_production" in r.json()["detail"]


def test_rejecting_an_unknown_job_is_a_404(api):
    r = api.post("/api/production-jobs/99999999/reject", json={"reason": REASON})
    assert r.status_code == 404
