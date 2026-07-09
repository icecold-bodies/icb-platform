"""A10 V/P day-slots (migration 0034) — service + API tests.

Covers the new day dimension end-to-end at the contract level:
  * eta_gate_reason day-awareness (weekday, weekend, legacy weekly fallback)
  * (bay, week, DAY) occupancy — same bay+week on different days now coexists;
    same day still 409s; legacy NULL-day rows block Monday
  * move: explicit day change, day preserved on a day-omitted week-hop
  * planned_start_date = the slot DATE (Monday + day)
  * request validation (day_of_week 0..6) and board payload carrying day_of_week

Fixture style mirrors test_planning_session_roles_api.py (module TestClient +
require_user override + self-cleaning factories; unique bay names per test).
"""
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest


# ── fixtures (same pattern as test_planning_session_roles_api.py) ─────────────
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
def fresh_planning_job(app_mod):
    """Factory -> id of a fresh status='planning' production job (+ its calc). Cleaned up."""
    from app.database import Branch, CalculationRecord, SessionLocal
    from app.models.mes import PlanningSlot, ProductionJob
    pjs, calcs = [], []

    def _make(chassis_eta=None, chassis_received_at=None):
        with SessionLocal() as db:
            jhb = db.query(Branch).filter_by(code="JHB").first()
            c = CalculationRecord(
                quote_number=f"Q-DS{uuid.uuid4().hex[:8]}", status="accepted", branch_id=jhb.id,
                dimensions_json=json.dumps({"body_type": "5.4m Chiller Body"}),
                result_json=json.dumps({"selling_zar": 1000.0}))
            db.add(c)
            db.commit()
            db.refresh(c)
            calcs.append(c.id)
            pj = ProductionJob(calculation_record_id=c.id, branch_id=jhb.id, job_number=f"DS{c.id}",
                               status="planning", chassis_eta=chassis_eta,
                               chassis_received_at=chassis_received_at)
            db.add(pj)
            db.commit()
            db.refresh(pj)
            pjs.append(pj.id)
            return pj.id

    yield _make
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


_RCV = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _bay() -> str:
    return f"QA-A10-{uuid.uuid4().hex[:6]}"


# ── service unit tests ─────────────────────────────────────────────────────────
def test_eta_gate_day_aware_unit():
    """§8.2.7 — with a day_of_week the deadline is the SLOT DAY's end (weekends included, no special
    allowance); without one the original weekly Friday-EOD rule is byte-identical (legacy callers)."""
    from app.services import planning as pl

    class J:
        pass
    j = J()
    monday = date(2026, 9, 7)                                   # a Monday
    j.chassis_eta = datetime(2026, 9, 9, tzinfo=timezone.utc)   # Wednesday of that week

    # day-aware: Tue (before ETA) blocks; Wed/Fri (on/after ETA) pass
    assert pl.eta_gate_reason(j, monday, received=False, day_of_week=1) is not None
    assert pl.eta_gate_reason(j, monday, received=False, day_of_week=2) is None
    assert pl.eta_gate_reason(j, monday, received=False, day_of_week=4) is None
    # legacy weekly (day omitted): ETA within the week -> ok (Friday-EOD rule preserved)
    assert pl.eta_gate_reason(j, monday, received=False) is None

    # weekend: ETA Saturday -> Saturday slot ok, Friday slot blocks
    j.chassis_eta = datetime(2026, 9, 12, tzinfo=timezone.utc)  # Saturday
    assert pl.eta_gate_reason(j, monday, received=False, day_of_week=5) is None
    assert pl.eta_gate_reason(j, monday, received=False, day_of_week=4) is not None
    # ETA Monday-next rejects a Saturday drop (the §8.2.7 example verbatim)
    j.chassis_eta = datetime(2026, 9, 14, tzinfo=timezone.utc)  # next Monday
    assert pl.eta_gate_reason(j, monday, received=False, day_of_week=5) is not None
    # received bypasses regardless of day
    assert pl.eta_gate_reason(j, monday, received=True, day_of_week=5) is None


def test_same_bay_week_different_days_coexist(fresh_planning_job, admin):
    """The NEW capability: two jobs share a bay-week on different days; the same day still 409s."""
    from app.database import SessionLocal
    from app.services import planning as pl
    a, b, c = (fresh_planning_job(chassis_received_at=_RCV) for _ in range(3))
    bay, week = _bay(), date(2026, 9, 7)
    with SessionLocal() as db:
        s1 = pl.schedule(db, production_job_id=a, week=week, bay=bay, day_of_week=0, user=admin)
        s2 = pl.schedule(db, production_job_id=b, week=week, bay=bay, day_of_week=1, user=admin)
        assert s1.day_of_week == 0 and s2.day_of_week == 1
        with pytest.raises(pl.CellOccupiedError):
            pl.schedule(db, production_job_id=c, week=week, bay=bay, day_of_week=1, user=admin)


def test_legacy_null_day_row_blocks_monday(fresh_planning_job, admin):
    """A pre-0034 row (day_of_week NULL, e.g. a direct fixture insert) normalises to Monday: an
    explicit Monday drop 409s against it; Tuesday is free."""
    from app.database import SessionLocal
    from app.models.mes import PlanningSlot
    from app.services import planning as pl
    a, b, c = (fresh_planning_job(chassis_received_at=_RCV) for _ in range(3))
    bay, week = _bay(), date(2026, 9, 7)
    with SessionLocal() as db:
        db.add(PlanningSlot(production_job_id=a, week=week, bay=bay, lane="vacuum",
                            day_of_week=None, status="scheduled"))
        db.commit()
    with SessionLocal() as db:
        with pytest.raises(pl.CellOccupiedError):
            pl.schedule(db, production_job_id=b, week=week, bay=bay, day_of_week=0, user=admin)
        it = pl.schedule(db, production_job_id=c, week=week, bay=bay, day_of_week=1, user=admin)
        assert it.day_of_week == 1


def test_planned_start_is_slot_date(fresh_planning_job, admin):
    from app.database import SessionLocal
    from app.services import planning as pl
    jid = fresh_planning_job(chassis_received_at=_RCV)
    week = date(2026, 9, 7)
    with SessionLocal() as db:
        pl.schedule(db, production_job_id=jid, week=week, bay=_bay(), day_of_week=3, user=admin)
    from app.models.mes import ProductionJob
    with SessionLocal() as db:
        job = db.get(ProductionJob, jid)
        assert job.planned_start_date.date() == week + timedelta(days=3)   # Thursday


def test_move_day_change_and_day_preserved_on_omit(fresh_planning_job, admin):
    from app.database import SessionLocal
    from app.services import planning as pl
    jid = fresh_planning_job(chassis_received_at=_RCV)
    bay, week = _bay(), date(2026, 9, 7)
    with SessionLocal() as db:
        slot = pl.schedule(db, production_job_id=jid, week=week, bay=bay, day_of_week=2, user=admin)
        # explicit day change within the week
        mv = pl.move(db, slot_id=slot.id, week=week, bay=bay, day_of_week=4, user=admin)
        assert mv.day_of_week == 4
        # day-omitted week-hop preserves the day (Friday stays Friday)
        mv2 = pl.move(db, slot_id=slot.id, week=week + timedelta(weeks=1), bay=bay, user=admin)
        assert mv2.day_of_week == 4 and mv2.week == week + timedelta(weeks=1)


# ── API integration tests ──────────────────────────────────────────────────────
def test_api_schedule_day_roundtrip_and_board_payload(api, fresh_planning_job):
    jid = fresh_planning_job(chassis_received_at=_RCV)
    bay = _bay()
    r = api.post("/api/planning-slots", json={"production_job_id": jid, "week": "2026-10-05",
                                              "bay": bay, "lane": "vacuum", "day_of_week": 2})
    assert r.status_code == 201 and r.json()["day_of_week"] == 2
    slot_id = r.json()["id"]
    # the board carries day_of_week on every slot
    bd = api.get("/api/planning-board?weeks=4&start=2026-10-05").json()
    mine = [s for s in bd["slots"] if s["id"] == slot_id]
    assert mine and mine[0]["day_of_week"] == 2
    # move to Saturday of the same week (received chassis -> weekend gate bypassed)
    mv = api.post(f"/api/planning-slots/{slot_id}/move",
                  json={"week": "2026-10-05", "bay": bay, "day_of_week": 5})
    assert mv.status_code == 200 and mv.json()["day_of_week"] == 5
    assert api.delete(f"/api/planning-slots/{slot_id}").status_code == 200


def test_api_weekend_eta_gate(api, fresh_planning_job):
    """§8.2.7 — Saturday accepts an ETA up to that Saturday; an ETA of Monday-next 422s."""
    ok = fresh_planning_job(chassis_eta=datetime(2026, 10, 10, tzinfo=timezone.utc))   # Sat 10 Oct
    late = fresh_planning_job(chassis_eta=datetime(2026, 10, 12, tzinfo=timezone.utc)) # Mon 12 Oct
    bay = _bay()
    r_ok = api.post("/api/planning-slots", json={"production_job_id": ok, "week": "2026-10-05",
                                                 "bay": bay, "day_of_week": 5})
    assert r_ok.status_code == 201
    r_late = api.post("/api/planning-slots", json={"production_job_id": late, "week": "2026-10-05",
                                                   "bay": _bay(), "day_of_week": 5})
    assert r_late.status_code == 422
    assert "slot day" in r_late.json()["detail"]


def test_api_day_of_week_range_validation(api, fresh_planning_job):
    jid = fresh_planning_job(chassis_received_at=_RCV)
    r = api.post("/api/planning-slots", json={"production_job_id": jid, "week": "2026-10-05",
                                              "bay": _bay(), "day_of_week": 7})
    assert r.status_code == 422        # pydantic ge/le range, before any service logic


def test_api_same_cell_409_names_the_day(api, fresh_planning_job):
    a = fresh_planning_job(chassis_received_at=_RCV)
    b = fresh_planning_job(chassis_received_at=_RCV)
    bay = _bay()
    assert api.post("/api/planning-slots", json={"production_job_id": a, "week": "2026-10-05",
                                                 "bay": bay, "day_of_week": 3}).status_code == 201
    r = api.post("/api/planning-slots", json={"production_job_id": b, "week": "2026-10-05",
                                              "bay": bay, "day_of_week": 3})
    assert r.status_code == 409 and "2026-10-08" in r.json()["detail"]   # Thursday named in the error


def test_floor_doc_downstream_releases_cell(api, fresh_planning_job):
    """v1.40.6 ghost-slot fix + the same-day 9934 refinement: a job the FLOOR DOCUMENT has
    taken past Vacuum/Press must (a) KEEP its slot in board.slots — the /plan Panels-Ready
    rail feeds off board slots (boardToPanels → engine setPanels), and the engine PRUNES
    cut declarations for jobs missing from that feed, so filtering these slots out of the
    board left cut-but-not-consumed jobs invisible everywhere and one doc-persist from
    losing their Panels-Ready state; (b) release its CELL for drops (the V-1 Wednesday
    ghost — grid cards are hidden CLIENT-side); (c) stay out of the unscheduled pool;
    (d) keep its slot row non-destructively (panels dragged back re-surface it)."""
    import json as J
    from app.database import SessionLocal
    from app.models.mes import PlanFloorState, PlanningSlot, ProductionJob

    ghost_pid = fresh_planning_job(chassis_received_at=_RCV)
    other_pid = fresh_planning_job(chassis_received_at=_RCV)
    week, bay = "2026-10-05", _bay()
    r = api.post("/api/planning-slots", json={"production_job_id": ghost_pid, "week": week,
                                              "bay": bay, "lane": "vacuum", "day_of_week": 2})
    assert r.status_code == 201, r.text
    ghost_slot_id = r.json()["id"]

    with SessionLocal() as db:
        jn = db.get(ProductionJob, ghost_pid).job_number
        row = db.get(PlanFloorState, 1)
        created_row = row is None
        original = row.state if row is not None else None
        doc = J.loads(original) if original else {}
        doc.setdefault("cut", []).append({"job": jn})     # Panels Ready — past Vacuum/Press
        if created_row:
            db.add(PlanFloorState(id=1, state=J.dumps(doc)))
        else:
            row.state = J.dumps(doc)
        db.commit()

    try:
        # Anchor the 12-week window ON the slot's week — 2026-10-05 sits outside the rolling
        # window from "today", which made the previous inverse assertion pass vacuously.
        board = api.get("/api/planning-board", params={"weeks": 12, "start": week}).json()
        assert any(s["id"] == ghost_slot_id for s in board["slots"]), \
            "doc-downstream slot must STAY in board.slots — the Panels-Ready rail feeds off it (9934)"
        pool_ids = {j["id"] for j in board["unscheduled_pool"]}
        assert ghost_pid not in pool_ids, "a cut job must not be re-schedulable from the pool"
        r2 = api.post("/api/planning-slots", json={"production_job_id": other_pid, "week": week,
                                                   "bay": bay, "lane": "vacuum", "day_of_week": 2})
        assert r2.status_code == 201, f"the freed cell must accept a drop: {r2.text}"
        with SessionLocal() as db:
            assert db.get(PlanningSlot, ghost_slot_id) is not None, \
                "the ghost's slot row must survive non-destructively"
    finally:
        with SessionLocal() as db:
            row = db.get(PlanFloorState, 1)
            if created_row and row is not None:
                db.delete(row)
            elif row is not None:
                row.state = original
            db.commit()
