"""v1.40.6 thresholds WO §3.6 — V/P stage-progress bars on /plan (journey).

Determinism trick that also proves the admin→board integration end-to-end: the fixture
drops the VACUUM threshold to 0.01h with workday_start 00:00 (restored in teardown), so a
job scheduled TODAY reads >100% elapsed — data-tone="red" — at ANY run time of day, on any
CI timezone. A second job two weeks out must read "pending" (clock not started). The
drawer's stage-clock line renders on card click. Marker jobs JVP*, slots on real cockpit
bays (V-5 downward probing — seeded data may occupy cells), all cleaned both sides.

CSP-safe: locator/attribute waits only (the app CSP has no unsafe-eval).
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402

T = 15_000
JOURNEY = "vp_progress"
_VAC_FAST = (0.01, time(0, 0))
_VAC_SEED = (8.00, time(7, 0))


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _set_vacuum(hours: float, start: time) -> None:
    from app.database import SessionLocal
    from app.models.mes import ProductionStageThreshold
    from sqlalchemy import select
    with SessionLocal() as db:
        vac = db.execute(select(ProductionStageThreshold)
                         .where(ProductionStageThreshold.stage_code == "vacuum")).scalar_one()
        vac.threshold_hours = hours
        vac.workday_start = start
        vac.is_active = True
        db.commit()


def _mk_job(db, tag: str):
    from app.database import Branch, CalculationRecord
    from app.models.mes import ProductionJob
    jhb = db.query(Branch).filter_by(code="JHB").first()
    c = CalculationRecord(
        quote_number=f"Q-JVP{uuid.uuid4().hex[:6]}", status="accepted", branch_id=jhb.id,
        dimensions_json=json.dumps({"body_type": "5.4m Chiller Body"}),
        result_json=json.dumps({"selling_zar": 1000.0}))
    db.add(c)
    db.commit()
    db.refresh(c)
    pj = ProductionJob(calculation_record_id=c.id, branch_id=jhb.id,
                       job_number=f"JVP{tag}{c.id}", status="planning",
                       chassis_received_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    db.add(pj)
    db.commit()
    db.refresh(pj)
    return pj.id, c.id


def _schedule_probing(db, admin, pid: int, week: date, day: int) -> int:
    """Schedule onto a REAL vacuum cockpit bay (V-5 → V-1), probing past occupied cells —
    the CI seed may hold slots. Returns the slot id."""
    from app.services import planning as pl
    last = None
    for bay in ("V-5", "V-4", "V-3", "V-2", "V-1"):
        try:
            it = pl.schedule(db, production_job_id=pid, week=week, bay=bay,
                             lane="vacuum", day_of_week=day, user=admin)
            return it.id
        except pl.CellOccupiedError as e:  # noqa: PERF203 — tiny loop, clarity wins
            last = e
    raise AssertionError(f"no free vacuum bay for week={week} day={day}: {last}")


@pytest.fixture()
def progress_fixture():
    from app.database import SessionLocal, User
    from app.models.mes import PlanningSlot, ProductionJob
    from app.database import CalculationRecord
    _set_vacuum(*_VAC_FAST)
    today = date.today()
    made: dict = {}
    with SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").first()
        red_pid, red_cid = _mk_job(db, "R")
        pend_pid, pend_cid = _mk_job(db, "P")
        _schedule_probing(db, admin, red_pid, _monday(today), today.weekday())
        _schedule_probing(db, admin, pend_pid, _monday(today) + timedelta(weeks=2), 0)
        made = {"jobs": [red_pid, pend_pid], "calcs": [red_cid, pend_cid],
                "red": red_pid, "pending": pend_pid}
    yield made
    _set_vacuum(*_VAC_SEED)                       # restore the 0036 seed values
    with SessionLocal() as db:
        for pid in made.get("jobs", []):
            for s in db.query(PlanningSlot).filter_by(production_job_id=pid).all():
                db.delete(s)
            pj = db.get(ProductionJob, pid)
            if pj:
                db.delete(pj)
        for cid in made.get("calcs", []):
            c = db.get(CalculationRecord, cid)
            if c:
                db.delete(c)
        db.commit()


def test_vp_progress_bars_and_drawer_clock(page: Page, progress_fixture) -> None:
    red_id, pend_id = progress_fixture["red"], progress_fixture["pending"]
    admin_session(page)
    page.goto("/mes-app/plan")   # the SPA shell path — bare /plan is not a served route

    # The cockpit grid portals into the floor engine; our TODAY job's card carries the bar.
    red_card = page.locator(f"[data-testid='cockpit-slot-cell'][data-job-id='{red_id}']")
    expect(red_card).to_be_visible(timeout=30_000)
    red_bar = red_card.locator("[data-testid='slot-progress']")
    # 0.01h threshold + 00:00 start ⇒ over-threshold from 00:00:36 — red at any run time.
    expect(red_bar).to_have_attribute("data-tone", "red", timeout=T)
    shot(page, "01-red-bar-today", journey=JOURNEY)

    # The week+2 job hasn't started: pending tone (empty track). Attribute assertions
    # auto-wait on ATTACHED — the card may sit off-viewport in the 12-week scroller.
    pend_bar = page.locator(
        f"[data-testid='cockpit-slot-cell'][data-job-id='{pend_id}'] [data-testid='slot-progress']")
    expect(pend_bar).to_have_attribute("data-tone", "pending", timeout=T)

    # Card click → the standardized drawer overview carries the stage-clock line.
    red_card.click()
    clock = page.locator("[data-testid='slot-stage-clock']")
    expect(clock).to_be_visible(timeout=T)
    expect(clock).to_have_attribute("data-tone", "red", timeout=T)
    expect(clock).to_contain_text("Vacuum clock", timeout=T)
    shot(page, "02-drawer-stage-clock", journey=JOURNEY)
