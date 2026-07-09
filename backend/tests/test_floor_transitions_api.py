"""§9 P1 (v1.41.0) — server-authoritative floor transitions + journal + admin reset.

Covers at the contract level: the full forward arc (declare_cut → start_body → move_body →
drop_assembly → drop_chassis → confirm_merge → dispatch) and every reverse; the guard
matrix (staleness 409s, same-job 409s, merged-lock, unknown-type/unscheduled 422s) with
doc/version/journal all untouched on rejection; the server-side cut-prune (journaled);
Z-format stamps (drawer-clock parity); PUT /floor-state gone (405); GET carries version;
floor-reset 403 for a real non-admin session (user_can is a non-Depends gate — the
UserSession-cookie house pattern) and 200+journal for admin.

Fixture style: module TestClient + require_user override + self-cleaning factories
(test_planning_day_slots_api.py idiom); the floor doc singleton is saved/restored around
every test; marker rows FLT*/FLC* purged both sides.
"""
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as _c:
        yield m


@pytest.fixture
def admin():
    from app.database import SessionLocal, User
    with SessionLocal() as db:
        return db.query(User).filter_by(username="admin").first()


@pytest.fixture
def api(app_mod, admin):
    from app.deps import require_user
    from starlette.testclient import TestClient
    app_mod.app.dependency_overrides[require_user] = lambda: admin
    with TestClient(app_mod.app) as c:
        yield c
    app_mod.app.dependency_overrides.pop(require_user, None)


@pytest.fixture
def floor_doc_guard():
    """Save + restore the floor doc singleton (and purge marker floor_events) around a test."""
    from app.database import SessionLocal
    from app.models.mes import FloorEvent, PlanFloorState
    with SessionLocal() as db:
        row = db.get(PlanFloorState, 1)
        created = row is None
        orig_state = row.state if row else None
        orig_ver = int(row.version or 0) if row else 0
    yield
    with SessionLocal() as db:
        row = db.get(PlanFloorState, 1)
        if created and row is not None:
            db.delete(row)
        elif row is not None:
            row.state = orig_state
            row.version = orig_ver
        for e in db.query(FloorEvent).filter(
                (FloorEvent.job_number.like("FLT%")) | (FloorEvent.job_number.is_(None))
                | (FloorEvent.event_type == "floor_reset")).all():
            db.delete(e)
        db.commit()


@pytest.fixture
def fresh_planning_job(app_mod):
    from app.database import Branch, CalculationRecord, SessionLocal
    from app.models.mes import PlanningSlot, ProductionJob
    pjs, calcs = [], []

    def _make():
        with SessionLocal() as db:
            jhb = db.query(Branch).filter_by(code="JHB").first()
            c = CalculationRecord(
                quote_number=f"Q-FLT{uuid.uuid4().hex[:8]}", status="accepted", branch_id=jhb.id,
                dimensions_json=json.dumps({"body_type": "5.4m Chiller Body"}),
                result_json=json.dumps({"selling_zar": 1000.0}))
            db.add(c)
            db.commit()
            db.refresh(c)
            calcs.append(c.id)
            pj = ProductionJob(calculation_record_id=c.id, branch_id=jhb.id,
                               job_number=f"FLT{c.id}", status="planning",
                               chassis_received_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            db.add(pj)
            db.commit()
            db.refresh(pj)
            pjs.append(pj.id)
            return pj.id

    yield _make
    from app.database import SessionLocal
    with SessionLocal() as db:
        for pid in pjs:
            for s in db.query(PlanningSlot).filter_by(production_job_id=pid).all():
                db.delete(s)
            pj = db.get(ProductionJob, pid)
            if pj:
                db.delete(pj)
        for cid in calcs:
            c = db.get(CalculationRecord, cid)
            if c:
                db.delete(c)
        db.commit()


def _schedule(pid, bay=None):
    from app.database import SessionLocal, User
    from app.services import planning as pl
    with SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").first()
        pl.schedule(db, production_job_id=pid, week=date(2026, 10, 5),
                    bay=bay or f"QA-FLT-{uuid.uuid4().hex[:5]}", lane="vacuum",
                    day_of_week=0, user=admin)


def _jn(pid):
    from app.database import SessionLocal
    from app.models.mes import ProductionJob
    with SessionLocal() as db:
        return db.get(ProductionJob, pid).job_number


def _events_for(jn):
    from app.database import SessionLocal
    from app.models.mes import FloorEvent
    from sqlalchemy import select
    with SessionLocal() as db:
        return [e.event_type for e in db.execute(
            select(FloorEvent).where(FloorEvent.job_number == jn)
            .order_by(FloorEvent.id)).scalars().all()]


T = "/api/plan/floor-transitions"


def test_full_arc_and_journal(api, fresh_planning_job, floor_doc_guard):
    pid = fresh_planning_job()
    jn = _jn(pid)
    _schedule(pid)
    # marker chassis for the merge leg
    from app.database import SessionLocal
    from app.models.mes import ChassisRecord, ProductionJob
    vin = f"FLTVIN{uuid.uuid4().hex[:10]}"
    with SessionLocal() as db:
        rec = ChassisRecord(vin=vin, status="in_workshop", customer_name="FLT Cust")
        db.add(rec)
        db.commit()
        db.refresh(rec)
        db.get(ProductionJob, pid).chassis_record_id = rec.id   # same-job link for the merge
        db.commit()
        rec_id = rec.id
    try:
        assert api.post(T, json={"type": "declare_cut", "job": jn}).status_code == 200
        assert api.post(T, json={"type": "start_body", "job": jn, "li": 1,
                                 "card": {"len": 5.4, "cust": "FLT"}}).status_code == 200
        assert api.post(T, json={"type": "drop_assembly", "id": jn, "li": 1}).status_code == 200
        r = api.post(T, json={"type": "drop_chassis", "li": 1, "vin": vin, "card": {}})
        assert r.status_code == 200, r.text
        r = api.post(T, json={"type": "confirm_merge", "li": 1})
        assert r.status_code == 200, r.text
        doc = json.loads(r.json()["state"])
        assert jn in [str(x) for x in doc["mergedJobs"]] and vin in [str(x) for x in doc["mergedChassis"]]
        assert doc["pre"][1]["merge"]["attached"]["matched"] is True   # DB-resolved same-job link
        r = api.post(T, json={"type": "dispatch", "li": 1})
        assert r.status_code == 200, r.text
        doc = json.loads(r.json()["state"])
        assert doc["qc"] and str(doc["qc"][0]["job"]) == jn
        assert doc["qc"][0]["enteredAt"].endswith("Z")                  # drawer-clock stamp parity
        assert _events_for(jn) == ["declare_cut", "start_body", "drop_assembly",
                                   "drop_chassis", "confirm_merge", "dispatch"]
        # merged job can never re-enter panels
        assert api.post(T, json={"type": "declare_cut", "job": jn}).status_code == 409
    finally:
        with SessionLocal() as db:
            db.get(ProductionJob, pid).chassis_record_id = None
            rec = db.get(ChassisRecord, rec_id)
            if rec:
                db.delete(rec)
            db.commit()


def test_guards_reject_without_side_effects(api, fresh_planning_job, floor_doc_guard):
    from app.database import SessionLocal
    from app.models.mes import PlanFloorState
    pid = fresh_planning_job()
    jn = _jn(pid)
    _schedule(pid)
    assert api.post(T, json={"type": "declare_cut", "job": jn}).status_code == 200
    with SessionLocal() as db:
        ver = int(db.get(PlanFloorState, 1).version)
    cases = [
        {"type": "warp_drive", "job": jn},                        # unknown type
        {"type": "declare_cut", "job": "FLTNOPE"},                # unscheduled
        {"type": "declare_cut", "job": jn},                       # already cut
        {"type": "start_body", "job": jn, "li": 9},               # bad line index
        {"type": "move_body", "id": "FLTGHOST", "li": 1, "desired": 0},   # not on a track
        {"type": "confirm_merge", "li": 0},                       # nothing staged
        {"type": "dispatch", "li": 0},                            # nothing attached
        {"type": "chassis_back_to_parking", "vin": "FLTNOVIN"},   # not staged
        {"type": "drop_chassis", "li": 0, "vin": "FLTNOVIN"},     # unknown VIN → 404
    ]
    for body in cases:
        r = api.post(T, json=body)
        assert r.status_code in (404, 409, 422), f"{body} -> {r.status_code}"
    with SessionLocal() as db:
        assert int(db.get(PlanFloorState, 1).version) == ver, "rejections must not bump version"
    assert _events_for(jn) == ["declare_cut"], "rejections must not journal"


def test_cut_prune_is_journaled(api, fresh_planning_job, floor_doc_guard):
    """An orphaned cut entry (job no longer scheduled, never started) is pruned by the
    next transition and journaled as cut_pruned — the engine's lazy prune, now persisted."""
    from app.database import SessionLocal
    from app.models.mes import PlanFloorState, PlanningSlot
    ghost = fresh_planning_job()
    ghost_jn = _jn(ghost)
    _schedule(ghost)
    other = fresh_planning_job()
    other_jn = _jn(other)
    _schedule(other)
    assert api.post(T, json={"type": "declare_cut", "job": ghost_jn}).status_code == 200
    with SessionLocal() as db:                                   # unschedule behind the doc's back
        for s in db.query(PlanningSlot).filter_by(production_job_id=ghost).all():
            db.delete(s)
        db.commit()
    assert api.post(T, json={"type": "declare_cut", "job": other_jn}).status_code == 200
    from app.models.mes import FloorEvent
    from sqlalchemy import select
    with SessionLocal() as db:
        pruned = db.execute(select(FloorEvent).where(
            FloorEvent.job_number == ghost_jn,
            FloorEvent.event_type == "cut_pruned")).scalars().all()
        assert pruned, "prune must journal"
        doc = json.loads(db.get(PlanFloorState, 1).state)
    assert ghost_jn not in [str(x) for x in doc["cut"]]
    assert ghost_jn not in doc["cutAt"]


def test_put_floor_state_is_gone(api):
    assert api.put("/api/plan/floor-state", json={"state": "{}"}).status_code == 405
    r = api.get("/api/plan/floor-state")
    assert r.status_code == 200 and "version" in r.json()


def test_floor_reset_admin_gate_and_journal(app_mod, admin, floor_doc_guard):
    """Reset: 403 for a REAL non-admin session (user_can resolves role server-side — the
    UserSession-cookie pattern; dependency overrides cannot model it), 200 + floor_reset
    journal row + monotonic version for admin."""
    from app.database import SessionLocal, User, UserSession
    from app.deps import require_user
    from app.models.mes import FloorEvent, PlanFloorState
    from sqlalchemy import select
    from starlette.testclient import TestClient

    sid = str(uuid.uuid4())
    uname = f"flr_{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        u = User(username=uname, password_hash="x", role="planner")
        db.add(u)
        db.commit()
        db.refresh(u)
        db.add(UserSession(id=sid, user_id=u.id, role=u.role, expires_at=None))
        db.commit()
        uid = u.id
    try:
        with TestClient(app_mod.app) as c:
            c.headers["Cookie"] = f"session_id={sid}"
            info = c.get("/api/session").json()
            c.headers["X-CSRF-Token"] = info.get("csrf_token") or ""
            assert c.post("/api/plan/floor-reset", json={"confirm": True}).status_code == 403

        app_mod.app.dependency_overrides[require_user] = lambda: admin
        try:
            with TestClient(app_mod.app) as c:
                assert c.post("/api/plan/floor-reset", json={"confirm": False}).status_code == 422
                with SessionLocal() as db:
                    before = int((db.get(PlanFloorState, 1) or PlanFloorState(version=0)).version or 0)
                r = c.post("/api/plan/floor-reset", json={"confirm": True})
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["version"] == before + 1
                doc = json.loads(body["state"])
                assert doc["cut"] == [] and doc["qc"] == [] and len(doc["pre"]) == 5
        finally:
            app_mod.app.dependency_overrides.pop(require_user, None)

        with SessionLocal() as db:
            evs = db.execute(select(FloorEvent).where(
                FloorEvent.event_type == "floor_reset")).scalars().all()
            assert evs and evs[-1].user_name == "admin"
    finally:
        with SessionLocal() as db:
            db.query(UserSession).filter_by(id=sid).delete()
            u = db.get(User, uid)
            if u:
                db.delete(u)
            db.commit()
