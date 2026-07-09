"""v1.40.6 admin Master-Data WO — production stage thresholds (0036) + board stage-clock.

Covers, at the contract level:
  * seeded rows (vacuum 8h / press 4h @ 07:00) present and served by the admin CRUD
  * CRUD: create (409 dup, 422 non-positive), PATCH (version bump, 422 guard), DELETE
  * auth: no session -> 401; a real NON-admin session cookie -> 403 (require_admin
    resolves the session itself — dependency overrides cannot reach it, so the 403
    test uses the UserSession + raw-Cookie-header house pattern; sid is a bare uuid,
    user_sessions.id is VARCHAR(36))
  * board progress matrix: this-week vacuum slot -> stage/threshold/elapsed sign;
    future week -> negative elapsed (pending); NULL day_of_week -> Monday start;
    lane='panelshop' -> press/4h; is_active=false -> progress None
  * all 16 admin.* Permission catalogue rows exist after startup bootstrap

Fixture style mirrors test_planning_day_slots_api.py (module TestClient +
require_user/require_admin overrides + self-cleaning factories). Times are asserted
as SIGNS/RANGES only — CI runners live in other timezones.
"""
import json
import uuid
from datetime import date, datetime, time, timedelta, timezone

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
    """Admin on BOTH gates: require_user (board reads) and require_admin (thresholds CRUD)."""
    from app.deps import require_admin, require_user
    from starlette.testclient import TestClient
    app_mod.app.dependency_overrides[require_user] = lambda: admin
    app_mod.app.dependency_overrides[require_admin] = lambda: admin
    with TestClient(app_mod.app) as c:
        yield c
    app_mod.app.dependency_overrides.pop(require_user, None)
    app_mod.app.dependency_overrides.pop(require_admin, None)


@pytest.fixture
def fresh_planning_job(app_mod):
    """Factory -> id of a fresh status='planning' production job (+ its calc). Cleaned up."""
    from app.database import Branch, CalculationRecord, SessionLocal
    from app.models.mes import PlanningSlot, ProductionJob
    pjs, calcs = [], []

    def _make():
        with SessionLocal() as db:
            jhb = db.query(Branch).filter_by(code="JHB").first()
            c = CalculationRecord(
                quote_number=f"Q-TH{uuid.uuid4().hex[:8]}", status="accepted", branch_id=jhb.id,
                dimensions_json=json.dumps({"body_type": "5.4m Chiller Body"}),
                result_json=json.dumps({"selling_zar": 1000.0}))
            db.add(c)
            db.commit()
            db.refresh(c)
            calcs.append(c.id)
            pj = ProductionJob(calculation_record_id=c.id, branch_id=jhb.id, job_number=f"TH{c.id}",
                               status="planning",
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


def _bay() -> str:
    return f"QA-TH-{uuid.uuid4().hex[:6]}"


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _board_slot(api, slot_id: int):
    board = api.get("/api/planning-board", params={"weeks": 12}).json()
    return next((s for s in board["slots"] if s["id"] == slot_id), None)


BASE = "/api/admin/production-thresholds"


# ── seeded rows + CRUD ────────────────────────────────────────────────────────

def test_seeded_stage_rows_served(api):
    rows = {r["stage_code"]: r for r in api.get(BASE).json()}
    assert "vacuum" in rows and "press" in rows, "0036 seeds missing"
    assert rows["vacuum"]["threshold_hours"] == 8.0
    assert rows["press"]["threshold_hours"] == 4.0
    assert rows["vacuum"]["workday_start"].startswith("07:00")
    assert rows["vacuum"]["is_active"] is True


def test_crud_create_dup_and_guards(api):
    from app.database import SessionLocal
    from app.models.mes import ProductionStageThreshold
    created = api.post(BASE, json={"stage_code": f"qa-{uuid.uuid4().hex[:6]}", "label": "QA Stage",
                                   "threshold_hours": 2.5, "workday_start": "06:30"})
    assert created.status_code == 201, created.text
    body = created.json()
    try:
        assert body["workday_start"].startswith("06:30")

        dup = api.post(BASE, json={"stage_code": body["stage_code"], "label": "x",
                                   "threshold_hours": 1})
        assert dup.status_code == 409

        bad = api.post(BASE, json={"stage_code": f"qa-{uuid.uuid4().hex[:6]}", "label": "x",
                                   "threshold_hours": 0})
        assert bad.status_code == 422

        patched = api.patch(f"{BASE}/{body['id']}", json={"threshold_hours": 3.25})
        assert patched.status_code == 200
        assert patched.json()["threshold_hours"] == 3.25
        with SessionLocal() as db:
            assert db.get(ProductionStageThreshold, body["id"]).version == 2  # PATCH bumps

        bad_patch = api.patch(f"{BASE}/{body['id']}", json={"threshold_hours": -1})
        assert bad_patch.status_code == 422
    finally:
        assert api.delete(f"{BASE}/{body['id']}").status_code == 204
    assert api.get(BASE).status_code == 200
    assert all(r["id"] != body["id"] for r in api.get(BASE).json())


def test_thresholds_auth_no_session_and_non_admin(app_mod):
    """require_admin resolves the session itself — overrides can't reach it. No cookie ->
    401; a REAL non-admin session cookie -> 403 ([[testclient-session-cookie]] pattern)."""
    from app.database import SessionLocal, User, UserSession
    from starlette.testclient import TestClient

    with TestClient(app_mod.app) as bare:
        assert bare.get(BASE).status_code == 401

    sid = str(uuid.uuid4())                     # bare uuid — user_sessions.id is VARCHAR(36)
    uname = f"th_{uuid.uuid4().hex[:8]}"
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
            assert c.get(BASE).status_code == 403
    finally:
        with SessionLocal() as db:
            db.query(UserSession).filter_by(id=sid).delete()
            u = db.get(User, uid)
            if u:
                db.delete(u)
            db.commit()


# ── board stage-clock matrix ──────────────────────────────────────────────────

def test_board_progress_this_week_vacuum(api, fresh_planning_job):
    pid = fresh_planning_job()
    week = _monday(date.today()).isoformat()
    r = api.post("/api/planning-slots", json={
        "production_job_id": pid, "week": week, "bay": _bay(), "lane": "vacuum",
        "day_of_week": 0})
    assert r.status_code in (200, 201), r.text
    slot = _board_slot(api, r.json()["id"])
    assert slot is not None and slot["progress"] is not None
    p = slot["progress"]
    assert p["stage"] == "vacuum" and p["label"] == "Vacuum"
    assert p["threshold_hours"] == 8.0
    assert p["workday_start"] == "07:00"
    # Monday of the current week @ 07:00 is in the past for any run later than Monday
    # 07:00; on CI the run COULD land Monday pre-07:00 — assert a sane range, not a sign.
    assert -168.0 < p["elapsed_hours"] < 168.0
    assert p["started_at"].startswith(week)


def test_board_progress_future_week_pending(api, fresh_planning_job):
    pid = fresh_planning_job()
    week = (_monday(date.today()) + timedelta(weeks=2)).isoformat()
    r = api.post("/api/planning-slots", json={
        "production_job_id": pid, "week": week, "bay": _bay(), "lane": "vacuum",
        "day_of_week": 3})
    assert r.status_code in (200, 201), r.text
    p = _board_slot(api, r.json()["id"])["progress"]
    assert p is not None
    assert p["elapsed_hours"] < 0, "a slot 2 weeks out must read pending (negative elapsed)"


def test_board_progress_null_day_normalises_to_monday(api, fresh_planning_job):
    """Direct-insert legacy row (no day_of_week) — started_at lands on the week's MONDAY,
    byte-identical to every other NULL-day renderer."""
    from app.database import SessionLocal
    from app.models.mes import PlanningSlot
    pid = fresh_planning_job()
    week = _monday(date.today()) + timedelta(weeks=1)
    with SessionLocal() as db:
        s = PlanningSlot(production_job_id=pid, week=week, bay=_bay(), lane="vacuum",
                         status="scheduled", day_of_week=None)
        db.add(s)
        db.commit()
        db.refresh(s)
        sid = s.id
    p = _board_slot(api, sid)["progress"]
    assert p is not None
    assert p["started_at"].startswith(week.isoformat())


def test_board_progress_press_lane(api, fresh_planning_job):
    pid = fresh_planning_job()
    week = _monday(date.today()).isoformat()
    r = api.post("/api/planning-slots", json={
        "production_job_id": pid, "week": week, "bay": _bay(), "lane": "panelshop",
        "day_of_week": 1})
    assert r.status_code in (200, 201), r.text
    p = _board_slot(api, r.json()["id"])["progress"]
    assert p is not None
    assert p["stage"] == "press" and p["threshold_hours"] == 4.0


def test_board_progress_inactive_stage_none(api, fresh_planning_job):
    """PATCH vacuum is_active=false -> its bars switch off (progress None); restored after."""
    from app.database import SessionLocal
    from app.models.mes import ProductionStageThreshold
    from sqlalchemy import select
    pid = fresh_planning_job()
    week = _monday(date.today()).isoformat()
    r = api.post("/api/planning-slots", json={
        "production_job_id": pid, "week": week, "bay": _bay(), "lane": "vacuum",
        "day_of_week": 0})
    assert r.status_code in (200, 201), r.text
    slot_id = r.json()["id"]
    with SessionLocal() as db:
        vac = db.execute(select(ProductionStageThreshold)
                         .where(ProductionStageThreshold.stage_code == "vacuum")).scalar_one()
        vac_id = vac.id
    try:
        assert api.patch(f"{BASE}/{vac_id}", json={"is_active": False}).status_code == 200
        assert _board_slot(api, slot_id)["progress"] is None
    finally:
        assert api.patch(f"{BASE}/{vac_id}", json={"is_active": True}).status_code == 200
    assert _board_slot(api, slot_id)["progress"] is not None


# ── permission catalogue ──────────────────────────────────────────────────────

def test_admin_page_permission_rows_bootstrapped(app_mod):
    """The 16 admin.<slug> catalogue keys exist as Permission rows after startup
    (the catalogue bootstrap is the authoritative healing mechanism)."""
    from app.database import PERMISSION_CATALOGUE, Permission, SessionLocal
    keys = [n for (n, _d, c, _r) in PERMISSION_CATALOGUE if c == "admin" and n.startswith("admin.")]
    assert len(keys) == 16
    with SessionLocal() as db:
        present = {p.name for p in db.query(Permission).filter(Permission.name.in_(keys)).all()}
    assert present == set(keys), f"missing: {set(keys) - present}"


# ── v1.40.8 — the drawer's floor-stage clock (job-card bundle) ────────────────

def test_job_card_stage_clock_matrix(api, fresh_planning_job):
    """GET /api/plan/job-card/{job}.stage_clock: Panels Ready (stamped) → panels_ready
    threshold + positive elapsed; Pre-Assembly body stamp → pre_assembly; merge.assembly
    stamp → 'merge' threshold with stage_label Pre-Merge; UNSTAMPED cut entry → clock
    fields None (no invented start); off-floor job → stage_clock None entirely."""
    import json as J
    from datetime import datetime, timedelta, timezone
    from app.database import SessionLocal
    from app.models.mes import PlanFloorState, ProductionJob

    pids = [fresh_planning_job() for _ in range(5)]
    with SessionLocal() as db:
        jns = [db.get(ProductionJob, p).job_number for p in pids]
        cut_j, body_j, merge_j, bare_j, off_j = jns
        stamp = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        row = db.get(PlanFloorState, 1)
        created_row = row is None
        original = row.state if row is not None else None
        doc = J.loads(original) if original else {}
        doc.setdefault("cut", []).extend([cut_j, bare_j])
        doc["cutAt"] = {**(doc.get("cutAt") or {}), cut_j: stamp}   # bare_j deliberately unstamped
        doc.setdefault("pre", [])
        doc["pre"] = doc["pre"] or []
        doc["pre"].append({"id": "Bay QA", "bodies": [
            {"id": body_j, "job": body_j, "enteredAt": stamp}],
            "merge": {"chassis": None, "attached": None,
                      "assembly": {"id": merge_j, "job": merge_j, "mergeEnteredAt": stamp}}})
        if created_row:
            db.add(PlanFloorState(id=1, state=J.dumps(doc)))
        else:
            row.state = J.dumps(doc)
        db.commit()

    try:
        def clock(jn):
            r = api.get(f"/api/plan/job-card/{jn}")
            assert r.status_code == 200, r.text
            return r.json()["stage_clock"]

        c = clock(cut_j)
        assert c["stage"] == "panels_ready" and c["stage_label"] == "Panels Ready"
        assert c["threshold_hours"] == 24.0
        assert 1.9 < c["elapsed_hours"] < 2.5          # stamped 2h ago (range: CI slowness)

        b = clock(body_j)
        assert b["stage"] == "pre_assembly" and b["threshold_hours"] == 40.0
        assert b["elapsed_hours"] is not None

        m = clock(merge_j)
        assert m["stage"] == "merge" and m["stage_label"] == "Pre-Merge"
        assert m["threshold_hours"] == 16.0

        bare = clock(bare_j)
        assert bare is not None and bare["stage"] == "panels_ready"
        assert bare["elapsed_hours"] is None and bare["started_at"] is None

        assert clock(off_j) is None                    # not on the floor doc at all
    finally:
        with SessionLocal() as db:
            row = db.get(PlanFloorState, 1)
            if created_row and row is not None:
                db.delete(row)
            elif row is not None:
                row.state = original
            db.commit()


def test_startup_bootstraps_seed_fresh_env(app_mod):
    """v1.40.9 — init_db's three bootstraps (permissions / report templates / chassis
    catalogues) run on every boot. On CI's fresh icb_test, THIS suite's own TestClient
    startup is what seeds them — the dead _run_migrations body that once held these
    calls was deleted, so this asserts the rewiring stays live."""
    from sqlalchemy import text
    from app.database import SessionLocal
    with SessionLocal() as db:
        rt = db.execute(text("SELECT count(*) FROM icb_costings.report_templates")).scalar()
        co = db.execute(text("SELECT count(*) FROM icb_costings.chassis_options")).scalar()
        cc = db.execute(text("SELECT count(*) FROM icb_costings.chassis_constants")).scalar()
    assert rt >= 4, f"report templates not seeded (got {rt})"
    assert co >= 40, f"chassis options not seeded (got {co})"
    assert cc >= 15, f"chassis constants not seeded (got {cc})"
