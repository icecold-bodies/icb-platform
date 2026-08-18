"""v1.49 — /schedule-repair actually schedules.

Michael, 18 Aug 2026: "the user has scheduled a repair but does not pulse on the
planning board". It never could. The handler was:

    rec.repair_phases_json = json.dumps(cleaned)
    db.commit()

— a JSON blob on the costing and nothing else. Three separate things then kept
the repair off the board, and fixing any one alone would have left it invisible:

  1. the job stayed 'accepted', and planning._unscheduled_pool selects
     ProductionJob.status == 'planning'
  2. the COSTING stayed 'accepted' too, and PlanningBoard drops anything whose
     status is not 'Planning' (the pulse hangs off that card)
  3. even at status 'planning' a repair reported mes_status "Repair", because the
     repair override in the list serializer swallowed 'planning'

Repairs cannot reach 'planning' the body way — that route runs through the
Pre-Job Card and both sign-offs, which repairs deliberately skip. Scheduling IS
their transition, so it has to do the work.

House pattern: live test DB, marker rows, module-local fixtures, purge both sides.
"""
import json

import pytest
from sqlalchemy import text

_MARK = "V149SCH"


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
def accepted_repair():
    """An ACCEPTED repair with its production job — the state the Schedule button
    is pressed from."""
    from app.database import Customer, CalculationRecord, SessionLocal
    from app.models.mes import ProductionJob
    with SessionLocal() as db:
        _purge(db)
        cust = Customer(name=f"{_MARK} Carriers", bp_code=f"{_MARK}1", is_active=True)
        db.add(cust)
        db.flush()
        rec = CalculationRecord(
            trailer_type_id=None, customer_id=cust.id, is_repair=True, status="accepted",
            quote_number=f"{_MARK}/08/2026", dimensions_json="{}",
            result_json=json.dumps({"items": [], "grand_total": 0.0}))
        db.add(rec)
        db.flush()
        branch = db.execute(text("SELECT id FROM icb_costings.branches LIMIT 1")).scalar()
        job = ProductionJob(calculation_record_id=rec.id, branch_id=branch,
                            job_number=f"{_MARK}J", status="accepted")
        db.add(job)
        db.commit()
        ids = (rec.id, job.id)
    yield ids
    with SessionLocal() as db:
        _purge(db)


PHASES = [{"phase": "Pre-Assembly", "bay_id": "PRE-1", "estimated_hours": 4}]


def test_scheduling_moves_the_job_into_planning(api, accepted_repair):
    """Root cause 1: the board's pool selects jobs with status 'planning'."""
    from app.database import SessionLocal
    from app.models.mes import ProductionJob
    rec_id, job_id = accepted_repair

    r = api.post(f"/api/calculations/{rec_id}/schedule-repair", json={"phases": PHASES})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["job_status"] == "planning"

    with SessionLocal() as db:
        assert db.get(ProductionJob, job_id).status == "planning"


def test_scheduling_moves_the_costing_into_planning_too(api, accepted_repair):
    """Root cause 2: the board drops any costing whose status is not Planning.

    The two must move in lock-step, exactly as record_planning_ack does it —
    otherwise the Costings dashboard and the Planning board disagree about the
    same piece of work.
    """
    from app.database import SessionLocal, CalculationRecord
    rec_id, _ = accepted_repair
    api.post(f"/api/calculations/{rec_id}/schedule-repair", json={"phases": PHASES})
    with SessionLocal() as db:
        rec = db.get(CalculationRecord, rec_id)
        assert rec.status == "planning"
        assert rec.job_number_assigned, "the job number is assigned as the work becomes real"


def test_a_scheduled_repair_reports_as_Planning_not_Repair(api, accepted_repair):
    """Root cause 3, and the subtlest: the repair override used to swallow
    'planning', so the board dropped the card however correct the rest was."""
    rec_id, _ = accepted_repair
    api.post(f"/api/calculations/{rec_id}/schedule-repair", json={"phases": PHASES})
    row = next(x for x in api.get("/api/calculations?limit=200").json() if x["id"] == rec_id)
    assert row["mes_status"] == "Planning", (
        f"the Planning board filters on exactly 'Planning'; got {row['mes_status']!r}")
    assert row["is_repair"] is True, "it is still a repair — only the STATUS reads differently"


def test_the_phases_reach_the_MES_side(api, accepted_repair):
    """The phase plan was only ever written to the costing, so the job carried
    NULL and nothing in MES could act on it — which is what makes "straight to
    pre-assembly, no vacuum or press" expressible at all."""
    from app.database import SessionLocal
    from app.models.mes import ProductionJob
    rec_id, job_id = accepted_repair
    api.post(f"/api/calculations/{rec_id}/schedule-repair", json={"phases": PHASES})
    with SessionLocal() as db:
        stored = json.loads(db.get(ProductionJob, job_id).repair_phases_json or "null")
    assert stored == PHASES, "the job must carry the phases the planner chose"


def test_a_repair_can_skip_vacuum_and_press(api, accepted_repair):
    """Michael: "A repair might not need to go thru the vacuum or press process
    and can go straight to pre-assembly bay." Nothing may force a route."""
    from app.database import SessionLocal
    from app.models.mes import ProductionJob
    rec_id, job_id = accepted_repair
    r = api.post(f"/api/calculations/{rec_id}/schedule-repair",
                 json={"phases": [{"phase": "Pre-Assembly", "bay_id": "PRE-2",
                                   "estimated_hours": 6}]})
    assert r.status_code == 200, r.text[:300]
    with SessionLocal() as db:
        stored = json.loads(db.get(ProductionJob, job_id).repair_phases_json)
    names = [p["phase"] for p in stored]
    assert names == ["Pre-Assembly"]
    assert not any(n.lower() in ("vacuum", "press") for n in names), \
        "no phase may be injected that the planner did not choose"


def test_it_lands_in_the_boards_unscheduled_pool(api, accepted_repair):
    """The end-to-end assertion: the board's own query now returns the repair.

    Asserted through services/planning rather than the HTTP surface so the test
    pins the pool itself — the thing that was empty when Michael looked.
    """
    from app.database import SessionLocal
    from app.services import planning
    rec_id, job_id = accepted_repair
    api.post(f"/api/calculations/{rec_id}/schedule-repair", json={"phases": PHASES})
    with SessionLocal() as db:
        pool = planning._unscheduled_pool(db)
    assert any(getattr(j, "id", None) == job_id or getattr(j, "job_id", None) == job_id
               for j in pool), "the scheduled repair must be in the unscheduled pool"


def test_scheduling_an_accepted_repair_creates_its_job_if_the_client_never_did(api):
    """The job is normally created by a SECOND client call after /accept.

    Depending on that call having happened makes scheduling fail for a costing the
    user can plainly see is accepted, with no way to recover — which is exactly
    what the journey hit. Scheduling now creates it through accept_calculation
    (idempotent, resolves the branch, assigns the number), so the ordering of two
    client calls stops being load-bearing.
    """
    import json as _json
    from app.database import Customer, CalculationRecord, SessionLocal
    from app.models.mes import ProductionJob
    with SessionLocal() as db:
        _purge(db)
        cust = Customer(name=f"{_MARK} NoJobYet", bp_code=f"{_MARK}4", is_active=True)
        db.add(cust)
        db.flush()
        rec = CalculationRecord(trailer_type_id=None, customer_id=cust.id, is_repair=True,
                                status="accepted", quote_number=f"{_MARK}NJY/08/2026",
                                dimensions_json="{}",
                                result_json=_json.dumps({"items": [], "grand_total": 0.0}))
        db.add(rec)
        db.commit()
        rec_id = rec.id
        assert db.query(ProductionJob).filter_by(calculation_record_id=rec_id).count() == 0
    try:
        r = api.post(f"/api/calculations/{rec_id}/schedule-repair", json={"phases": PHASES})
        assert r.status_code == 200, r.text[:300]
        with SessionLocal() as db:
            job = db.query(ProductionJob).filter_by(calculation_record_id=rec_id).one()
            assert job.status == "planning"
            assert job.job_number, "accept_calculation assigns the number — not this code"
    finally:
        with SessionLocal() as db:
            _purge(db)


def test_scheduling_before_accepting_is_refused_clearly(api):
    """A costing that was never accepted has nothing to schedule, and creating a
    job for it would invent work nobody approved."""
    import json as _json
    from app.database import Customer, CalculationRecord, SessionLocal
    with SessionLocal() as db:
        _purge(db)
        cust = Customer(name=f"{_MARK} NoJob", bp_code=f"{_MARK}2", is_active=True)
        db.add(cust)
        db.flush()
        rec = CalculationRecord(trailer_type_id=None, customer_id=cust.id, is_repair=True,
                                status="pending", quote_number=f"{_MARK}NJ/08/2026",
                                dimensions_json="{}",
                                result_json=_json.dumps({"items": [], "grand_total": 0.0}))
        db.add(rec)
        db.commit()
        rec_id = rec.id
    try:
        r = api.post(f"/api/calculations/{rec_id}/schedule-repair", json={"phases": PHASES})
        assert r.status_code == 422, r.text[:300]
        assert "accept" in r.json()["detail"].lower()
    finally:
        with SessionLocal() as db:
            _purge(db)


def test_a_body_costing_still_cannot_use_this_endpoint(api):
    """Negative control — the repair-only guard is unchanged."""
    import json as _json
    from app.database import Customer, CalculationRecord, SessionLocal
    with SessionLocal() as db:
        _purge(db)
        cust = Customer(name=f"{_MARK} Body", bp_code=f"{_MARK}3", is_active=True)
        db.add(cust)
        db.flush()
        tt = db.execute(text("SELECT id FROM icb_costings.trailer_types LIMIT 1")).scalar()
        rec = CalculationRecord(trailer_type_id=tt, customer_id=cust.id, is_repair=False,
                                status="accepted", quote_number=f"{_MARK}B/08/2026",
                                dimensions_json="{}",
                                result_json=_json.dumps({"items": [], "grand_total": 0.0}))
        db.add(rec)
        db.commit()
        rec_id = rec.id
    try:
        r = api.post(f"/api/calculations/{rec_id}/schedule-repair", json={"phases": PHASES})
        assert r.status_code == 409
    finally:
        with SessionLocal() as db:
            _purge(db)
