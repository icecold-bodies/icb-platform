"""§9 P1 (v1.41.0) + P2 chokepoint wiring — server-authoritative floor transitions.

Covers at the contract level: the full forward arc (declare_cut → start_body → move_body →
drop_assembly → drop_chassis → confirm_merge → dispatch) and every reverse; the guard
matrix (staleness 409s, same-job 409s, merged-lock, unknown-type/unscheduled 422s) with
doc/version/journal all untouched on rejection; the server-side cut-prune (journaled);
Z-format stamps (drawer-clock parity); PUT /floor-state gone (405); GET carries version;
floor-reset 403 for a real non-admin session (user_can is a non-Depends gate — the
UserSession-cookie house pattern) and 200+journal for admin.

P2 (this release): the arc now asserts the DOMAIN side of every wired transition —
declare_cut flips the V/P slot to 'completed' (and locks unschedule until undo_cut),
drop_assembly writes panels_arrived_in_bay on the ordinal-mapped bay (relink-tolerant),
drop_chassis writes assembly_assigned + 'in_assembly', confirm_merge writes body_attached
+ links job.chassis_record_id, dispatch writes moved_to_awaiting_qa + 'awaiting_qa'
(Kenny's inbox). Non-admin permission gates (planning.schedule / chassis.assembly_assign)
are proven with a real UserSession cookie. The arc chassis is BOOKED IN (VCL event) —
assign_assembly_bay requires an open cycle. The merge line is PROBED for a free mapped
bay (shared-DB discipline: never assume bay N is clear).

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


def _free_line():
    """Probe the five floor lines for one whose ORDINAL-MAPPED assembly bay is genuinely
    free (no loose panels, no in-assembly occupant) — shared-DB discipline; a hardcoded
    line index would collide with seed/dev state."""
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.mes import ChassisRecord, ProductionJobBayEvent
    from app.services import chassis as ch
    with SessionLocal() as db:
        bays = ch.list_assembly_bays(db)[:5]
        for li, bay in enumerate(bays):
            other = db.execute(
                select(ProductionJobBayEvent).where(
                    ProductionJobBayEvent.bay_id == bay.id,
                    ProductionJobBayEvent.event_type == "panels_arrived_in_bay")
                .order_by(ProductionJobBayEvent.id.desc())).scalars().first()
            if other is not None and not ch._panels_consumed(db, other.production_job_id):
                continue
            occupied = any(
                ch._current_assembly_bay_id(db, cid) == bay.id
                for (cid,) in db.execute(select(ChassisRecord.id).where(
                    ChassisRecord.status == "in_assembly")).all())
            if not occupied:
                return li, bay.id
    raise AssertionError("no free assembly bay for the merge leg on this DB")


@pytest.fixture
def booked_in_chassis():
    """Marker chassis for the merge leg — BOOKED IN (VCL event opens cycle 1: the P2
    assign_assembly_bay chokepoint refuses a chassis with no open workshop cycle)."""
    from app.database import SessionLocal
    from app.models.mes import ChassisLifecycleEvent, ChassisRecord
    vin = f"FLTVIN{uuid.uuid4().hex[:10]}"
    with SessionLocal() as db:
        rec = ChassisRecord(vin=vin, status="in_workshop", customer_name="FLT Cust")
        db.add(rec)
        db.commit()
        db.refresh(rec)
        db.add(ChassisLifecycleEvent(chassis_record_id=rec.id, cycle_number=1,
                                     event_type="VCL", event_date=date.today(),
                                     created_by="t"))
        db.commit()
        rec_id = rec.id
    yield {"vin": vin, "rec_id": rec_id}
    with SessionLocal() as db:
        rec = db.get(ChassisRecord, rec_id)
        if rec:
            db.delete(rec)                      # lifecycle events CASCADE
        db.commit()


def _chassis_events(rec_id):
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.mes import ChassisLifecycleEvent
    with SessionLocal() as db:
        return [e.event_type for e in db.execute(
            select(ChassisLifecycleEvent)
            .where(ChassisLifecycleEvent.chassis_record_id == rec_id)
            .order_by(ChassisLifecycleEvent.id)).scalars().all()]


def _slot_statuses(pid):
    from app.database import SessionLocal
    from app.models.mes import PlanningSlot
    with SessionLocal() as db:
        return [s.status for s in db.query(PlanningSlot).filter_by(production_job_id=pid).all()]


def test_full_arc_and_journal(api, fresh_planning_job, booked_in_chassis, floor_doc_guard):
    pid = fresh_planning_job()
    jn = _jn(pid)
    _schedule(pid)
    vin, rec_id = booked_in_chassis["vin"], booked_in_chassis["rec_id"]
    li, bay_id = _free_line()
    from app.database import SessionLocal
    from app.models.mes import AssemblyBay, ChassisRecord, ProductionJob, ProductionJobBayEvent
    with SessionLocal() as db:
        db.get(ProductionJob, pid).chassis_record_id = rec_id   # same-job link for the merge
        bay = db.get(AssemblyBay, bay_id)
        bay_build = (bay.build_stage, bay.build_progress_pct)   # restore after (shared row)
        db.commit()
    try:
        assert api.post(T, json={"type": "declare_cut", "job": jn}).status_code == 200
        assert _slot_statuses(pid) == ["completed"]             # P2: slot vocabulary realized
        assert api.post(T, json={"type": "start_body", "job": jn, "li": li,
                                 "card": {"len": 5.4, "cust": "FLT"}}).status_code == 200
        assert api.post(T, json={"type": "drop_assembly", "id": jn, "li": li}).status_code == 200
        with SessionLocal() as db:                              # P2: panels committed to the mapped bay
            evs = db.query(ProductionJobBayEvent).filter_by(
                production_job_id=pid, event_type="panels_arrived_in_bay").all()
            assert [e.bay_id for e in evs] == [bay_id]
        r = api.post(T, json={"type": "drop_chassis", "li": li, "vin": vin, "card": {}})
        assert r.status_code == 200, r.text
        with SessionLocal() as db:                              # P2: chassis assigned to the bay
            assert db.get(ChassisRecord, rec_id).status == "in_assembly"
        assert "assembly_assigned" in _chassis_events(rec_id)
        r = api.post(T, json={"type": "confirm_merge", "li": li})
        assert r.status_code == 200, r.text
        doc = json.loads(r.json()["state"])
        assert jn in [str(x) for x in doc["mergedJobs"]] and vin in [str(x) for x in doc["mergedChassis"]]
        assert doc["pre"][li]["merge"]["attached"]["matched"] is True   # DB-resolved same-job link
        assert "body_attached" in _chassis_events(rec_id)       # P2: THE real merge chokepoint
        r = api.post(T, json={"type": "dispatch", "li": li})
        assert r.status_code == 200, r.text
        doc = json.loads(r.json()["state"])
        assert doc["qc"] and str(doc["qc"][0]["job"]) == jn
        assert doc["qc"][0]["enteredAt"].endswith("Z")                  # drawer-clock stamp parity
        with SessionLocal() as db:                              # P2: Kenny's QC inbox feeds natively
            assert db.get(ChassisRecord, rec_id).status == "awaiting_qa"
        assert "moved_to_awaiting_qa" in _chassis_events(rec_id)
        assert _events_for(jn) == ["declare_cut", "start_body", "drop_assembly",
                                   "drop_chassis", "confirm_merge", "dispatch"]
        # merged job can never re-enter panels
        assert api.post(T, json={"type": "declare_cut", "job": jn}).status_code in (409, 422)
    finally:
        with SessionLocal() as db:
            db.get(ProductionJob, pid).chassis_record_id = None
            bay = db.get(AssemblyBay, bay_id)
            bay.build_stage, bay.build_progress_pct = bay_build
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


# ── §9 P2 — chokepoint wiring contracts ──────────────────────────────────────

def test_undo_cut_restores_slot_and_unschedule_lock(api, fresh_planning_job, floor_doc_guard):
    """declare_cut flips the slot to 'completed' and LOCKS unschedule (409 naming undo-cut
    as the path); undo_cut flips it back to 'scheduled' and re-opens it."""
    from app.database import SessionLocal
    from app.models.mes import PlanningSlot
    from app.services import planning as pl
    pid = fresh_planning_job()
    jn = _jn(pid)
    _schedule(pid)
    assert api.post(T, json={"type": "declare_cut", "job": jn}).status_code == 200
    assert _slot_statuses(pid) == ["completed"]
    with SessionLocal() as db:
        slot_id = db.query(PlanningSlot).filter_by(production_job_id=pid).one().id
        with pytest.raises(pl.RevertNotAllowedError, match="undo the cut"):
            pl.unschedule(db, slot_id=slot_id, user=None)
    r = api.post(T, json={"type": "undo_cut", "job": jn})
    assert r.status_code == 200, r.text
    assert _slot_statuses(pid) == ["scheduled"]
    ev = _events_for(jn)
    assert ev == ["declare_cut", "undo_cut"]


def test_transition_permission_gates(app_mod, fresh_planning_job, floor_doc_guard):
    """Real UserSession cookies (no overrides): a sales user is 403'd off declare_cut
    (planning.schedule) and drop_assembly (chassis.assembly_assign) but move_body stays
    open (require_user only, doc guard answers); a planner passes both gates (the service
    guard answers instead of 403). Rejections leave version + journal untouched."""
    import uuid as _uuid
    from app.database import SessionLocal, User, UserSession
    from app.models.mes import PlanFloorState
    from starlette.testclient import TestClient

    def _session_client(role):
        sid = str(_uuid.uuid4())
        uname = f"flp_{_uuid.uuid4().hex[:8]}"
        with SessionLocal() as db:
            u = User(username=uname, password_hash="x", role=role)
            db.add(u)
            db.commit()
            db.refresh(u)
            db.add(UserSession(id=sid, user_id=u.id, role=u.role, expires_at=None))
            db.commit()
            uid = u.id
        c = TestClient(app_mod.app)
        c.headers["Cookie"] = f"session_id={sid}"
        info = c.get("/api/session").json()
        c.headers["X-CSRF-Token"] = info.get("csrf_token") or ""
        return c, sid, uid

    def _cleanup(sid, uid):
        with SessionLocal() as db:
            db.query(UserSession).filter_by(id=sid).delete()
            u = db.get(User, uid)
            if u:
                db.delete(u)
            db.commit()

    with SessionLocal() as db:
        row = db.get(PlanFloorState, 1)
        ver_before = int(row.version or 0) if row else 0

    sales, s_sid, s_uid = _session_client("sales")
    planner, p_sid, p_uid = _session_client("planner")
    try:
        with sales:
            assert sales.post(T, json={"type": "declare_cut", "job": "FLTNOPE"}).status_code == 403
            assert sales.post(T, json={"type": "drop_assembly", "id": "FLTGHOST", "li": 0}).status_code == 403
            # move_body is deliberately ungated — the DOC guard answers (409), not the perm gate
            assert sales.post(T, json={"type": "move_body", "id": "FLTGHOST", "li": 0,
                                       "desired": 0}).status_code == 409
        with planner:
            # gates pass for planner — the SERVICE guard answers (422 unscheduled / 409 stale)
            assert planner.post(T, json={"type": "declare_cut", "job": "FLTNOPE"}).status_code == 422
            assert planner.post(T, json={"type": "drop_assembly", "id": "FLTGHOST",
                                         "li": 0}).status_code == 409
    finally:
        _cleanup(s_sid, s_uid)
        _cleanup(p_sid, p_uid)
    with SessionLocal() as db:
        row = db.get(PlanFloorState, 1)
        ver_after = int(row.version or 0) if row else 0
    # the two 403s wrote nothing; the 409/422 rejections roll back — only the move_body/
    # drop_assembly probes never mutated anything either, so version is exactly unchanged
    assert ver_after == ver_before


def test_drop_assembly_relinks_stale_panels_event(api, fresh_planning_job, floor_doc_guard):
    """Cutover tolerance: a pre-P2 panels_arrived event on a DIFFERENT bay is relinked
    (clear + re-record in the same transaction) instead of 409ing, and the floor_events
    journal notes where it came from."""
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.mes import AssemblyBay, FloorEvent, ProductionJobBayEvent
    from app.services import chassis as ch
    pid = fresh_planning_job()
    jn = _jn(pid)
    _schedule(pid)
    li, bay_id = _free_line()
    with SessionLocal() as db:
        bays = ch.list_assembly_bays(db)
        stale_bay = next(b for b in bays if b.id != bay_id)
        stale_id = stale_bay.id
        mapped = db.get(AssemblyBay, bay_id)
        restore = {bay_id: (mapped.build_stage, mapped.build_progress_pct),
                   stale_id: (stale_bay.build_stage, stale_bay.build_progress_pct)}
        db.add(ProductionJobBayEvent(production_job_id=pid, bay_id=stale_id,
                                     event_type="panels_arrived_in_bay"))
        db.commit()
    try:
        assert api.post(T, json={"type": "declare_cut", "job": jn}).status_code == 200
        assert api.post(T, json={"type": "start_body", "job": jn, "li": li,
                                 "card": {"len": 5.4}}).status_code == 200
        assert api.post(T, json={"type": "drop_assembly", "id": jn, "li": li}).status_code == 200
        with SessionLocal() as db:
            evs = db.query(ProductionJobBayEvent).filter_by(
                production_job_id=pid, event_type="panels_arrived_in_bay").all()
            assert [e.bay_id for e in evs] == [bay_id], "stale event relinked to the mapped bay"
            fe = db.execute(select(FloorEvent).where(
                FloorEvent.job_number == jn,
                FloorEvent.event_type == "drop_assembly")).scalars().one()
            assert fe.details.get("panels_relinked_from_bay_id") == stale_id
            assert fe.details.get("bay_id") == bay_id
    finally:
        with SessionLocal() as db:
            for bid, (st, pct) in restore.items():
                b = db.get(AssemblyBay, bid)
                b.build_stage, b.build_progress_pct = st, pct
            db.commit()


def test_merge_and_dispatch_cutover_tolerance(api, fresh_planning_job, booked_in_chassis,
                                              floor_doc_guard):
    """A pre-P2 floor whose DB facts are ALREADY true converges instead of jamming:
    confirm_merge with body_attached already recorded for the same pair no-ops (no duplicate
    lifecycle event — the unique constraint would refuse one anyway) and notes it; dispatch
    of an already-awaiting_qa chassis likewise."""
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.mes import (
        ChassisLifecycleEvent, ChassisRecord, FloorEvent, PlanFloorState, ProductionJob,
    )
    pid = fresh_planning_job()
    jn = _jn(pid)
    vin, rec_id = booked_in_chassis["vin"], booked_in_chassis["rec_id"]
    li, bay_id = _free_line()
    with SessionLocal() as db:
        db.get(ProductionJob, pid).chassis_record_id = rec_id
        rec = db.get(ChassisRecord, rec_id)
        rec.status = "in_assembly"
        db.add(ChassisLifecycleEvent(chassis_record_id=rec_id, cycle_number=1,
                                     event_type="assembly_assigned", assembly_bay_id=bay_id,
                                     event_date=date.today(), created_by="t"))
        db.add(ChassisLifecycleEvent(chassis_record_id=rec_id, cycle_number=1,
                                     event_type="body_attached",
                                     event_date=date.today(), created_by="t"))
        # craft the doc: body + chassis staged in li's merge block (pre-P2 shape).
        # CI's fresh icb_test has no singleton row yet (dev does) — create like _locked_row;
        # floor_doc_guard captured created-ness and deletes it on teardown.
        row = db.get(PlanFloorState, 1)
        if row is None:
            row = PlanFloorState(id=1, state="{}", version=0)
            db.add(row)
        doc = json.loads(row.state or "{}")
        if not isinstance(doc.get("pre"), list) or len(doc["pre"]) != 5:
            doc["pre"] = [{"id": f"Bay {n}", "bodies": [],
                           "merge": {"chassis": None, "assembly": None, "attached": None}}
                          for n in range(1, 6)]
        doc["pre"][li]["merge"] = {
            "assembly": {"id": jn, "job": jn, "cust": "FLT", "len": 5.4, "status": "green"},
            "chassis": {"id": vin, "job": jn, "model": "T", "cust": "FLT"},
            "attached": None,
        }
        doc.setdefault("consumed", []).append(jn)
        doc.setdefault("cut", []).append(jn)
        row.state = json.dumps(doc)
        db.commit()
    try:
        r = api.post(T, json={"type": "confirm_merge", "li": li})
        assert r.status_code == 200, r.text
        with SessionLocal() as db:
            n_attached = len(db.execute(select(ChassisLifecycleEvent).where(
                ChassisLifecycleEvent.chassis_record_id == rec_id,
                ChassisLifecycleEvent.event_type == "body_attached")).scalars().all())
            assert n_attached == 1, "tolerance must not duplicate body_attached"
            fe = db.execute(select(FloorEvent).where(
                FloorEvent.job_number == jn,
                FloorEvent.event_type == "confirm_merge")).scalars().one()
            assert fe.details.get("already_attached") is True
            db.get(ChassisRecord, rec_id).status = "awaiting_qa"   # pre-P2 lane already moved it
            db.commit()
        r = api.post(T, json={"type": "dispatch", "li": li})
        assert r.status_code == 200, r.text
        with SessionLocal() as db:
            moved = db.execute(select(ChassisLifecycleEvent).where(
                ChassisLifecycleEvent.chassis_record_id == rec_id,
                ChassisLifecycleEvent.event_type == "moved_to_awaiting_qa")).scalars().all()
            assert moved == [], "tolerance must not write a duplicate handoff event"
            fe = db.execute(select(FloorEvent).where(
                FloorEvent.job_number == jn,
                FloorEvent.event_type == "dispatch")).scalars().one()
            assert fe.details.get("already_awaiting_qa") is True
    finally:
        with SessionLocal() as db:
            db.get(ProductionJob, pid).chassis_record_id = None
            db.commit()


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
