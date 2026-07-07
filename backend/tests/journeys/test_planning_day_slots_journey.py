"""A10 V/P day-slots — journey (Simeon-ratified v0.2, migration 0034).

Proves the day dimension on the routed surface (/plan embedded cockpit):
  * a job seeded on Wednesday renders in the day-2 sub-cell of its bay-week (data-day)
  * a Saturday job renders in the day-5 sub-cell wearing the WKND corner marker
    (the skinny weekend column expands for it — occupancy drives the grid template)
  * the weekend chassis-ETA gate at the drag path's contract (POST /api/planning-slots):
    ETA ≤ Saturday → 201; ETA Monday-next → 422 (§8.2.7 verbatim example)
  * drag-back-to-unscheduled from a WEEKEND slot (DELETE — the drag contract): the card
    leaves the grid and the job re-enters the Unscheduled rail

Structure mirrors test_unschedule_revert_journey.py: DB-seeded PLDAY marker rows (the
journey server shares this DB), page.request + session CSRF for unsafe calls (no fragile
HTML5-drag simulation), self-healing teardown.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
MARK = "PLDAY"
_RECEIVED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def _csrf(page: Page) -> str:
    from app.database import SessionLocal, UserSession
    sid = next((c["value"] for c in page.context.cookies() if c["name"] == "session_id"), None)
    assert sid, "no session_id cookie — autologin did not establish a session"
    with SessionLocal() as db:
        row = db.get(UserSession, sid)
        assert row is not None, "session row missing"
        return row.csrf_token or ""


def _post(page: Page, base: str, path: str, body: dict):
    return page.request.post(f"{base}{path}", data=body,
                             headers={"X-CSRF-Token": _csrf(page), "Origin": base})


def _delete(page: Page, base: str, path: str):
    return page.request.delete(f"{base}{path}",
                               headers={"X-CSRF-Token": _csrf(page), "Origin": base})


def _make_job(*, chassis_eta=None, received=True) -> dict:
    """Fresh status='planning' job (+ calc) with a classifiable body_type. NOT scheduled."""
    from app.database import Branch, CalculationRecord, SessionLocal
    from app.models.mes import ProductionJob

    tag = uuid.uuid4().hex[:6]
    with SessionLocal() as db:
        jhb = db.query(Branch).filter_by(code="JHB").first()
        calc = CalculationRecord(
            quote_number=f"{MARK}-{tag}", status="planning", branch_id=jhb.id,
            dimensions_json='{"body_type": "5.4m Chiller Body"}',
            result_json='{"selling_zar": 1000.0}')
        db.add(calc)
        db.flush()
        job = ProductionJob(
            calculation_record_id=calc.id, branch_id=jhb.id, status="planning",
            job_number=f"{MARK}{tag}", chassis_eta=chassis_eta,
            chassis_received_at=(_RECEIVED if received else None))
        db.add(job)
        db.commit()
        return {"job_id": job.id, "job_number": job.job_number}


def _schedule(job_id: int, bay: str, day: int) -> int:
    from app.database import SessionLocal
    from app.services import planning as pl
    with SessionLocal() as db:
        slot = pl.schedule(db, production_job_id=job_id, week=_monday(), bay=bay,
                           lane="vacuum", day_of_week=day, user=None)
        return slot.id


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    from app.database import SessionLocal
    from sqlalchemy import text
    with SessionLocal() as db:
        db.execute(text("DELETE FROM icb_mes.planning_slots WHERE bay LIKE 'QA-PLDAY-%'"))
        db.execute(text("DELETE FROM icb_mes.production_jobs WHERE job_number LIKE 'PLDAY%'"))
        db.execute(text("DELETE FROM icb_costings.calculations WHERE quote_number LIKE 'PLDAY%'"))
        db.commit()


def _open_board(page: Page) -> None:
    nav = page.get_by_test_id("nav-plan")
    expect(nav).to_be_visible(timeout=T)
    nav.click()
    expect(page.get_by_test_id("plan-embedded-cockpit")).to_be_visible(timeout=T)
    expect(page.get_by_role("heading", name="Planning Cockpit")).to_be_visible(timeout=T)


def test_day_slot_render_weekend_marker_and_dragback(page: Page, live_server: str) -> None:
    bay = f"QA-{MARK}-{uuid.uuid4().hex[:6]}"
    wed = _make_job()
    sat = _make_job()
    _schedule(wed["job_id"], bay, 2)                 # Wednesday, current week
    sat_slot = _schedule(sat["job_id"], bay, 5)      # Saturday, current week (weekend overtime)

    admin_session(page)
    _open_board(page)

    # Wednesday card sits in the day-2 sub-cell of its bay-week
    wed_card = page.locator(f"[data-testid='cockpit-slot-cell'][data-job-id='{wed['job_id']}']")
    expect(wed_card).to_be_visible(timeout=T)
    assert wed_card.get_attribute("data-day") == "2"
    expect(wed_card).to_contain_text(wed["job_number"])

    # Saturday card sits in day-5 wearing the WKND corner marker (expanded weekend column)
    sat_card = page.locator(f"[data-testid='cockpit-slot-cell'][data-job-id='{sat['job_id']}']")
    expect(sat_card).to_be_visible(timeout=T)
    assert sat_card.get_attribute("data-day") == "5"
    expect(sat_card).to_contain_text("WKND")
    shot(page, "01-day-slots-wed-and-wknd", journey="planning_day_slots")

    # Drag-back-to-unscheduled from the WEEKEND slot (the drag path's contract = DELETE)
    r = _delete(page, live_server, f"/api/planning-slots/{sat_slot}")
    assert r.status == 200, r.text()
    page.reload()
    expect(page.get_by_test_id("plan-embedded-cockpit")).to_be_visible(timeout=T)
    expect(page.locator(
        f"[data-testid='cockpit-slot-cell'][data-job-id='{sat['job_id']}']")).to_have_count(0)
    # the job re-enters the Unscheduled rail (pool cards render #job_number)
    expect(page.get_by_text(f"#{sat['job_number']}")).to_be_visible(timeout=T)
    shot(page, "02-weekend-dragback-to-pool", journey="planning_day_slots")


def test_weekend_eta_gate_contract(page: Page, live_server: str) -> None:
    """§8.2.7 — Saturday slots accept a job whose chassis ETA is on/before that Saturday;
    an ETA of Monday-next is rejected (422) with the slot-day named in the detail."""
    monday = _monday()
    sat_dt = datetime.combine(monday + timedelta(days=5), time(8, 0), tzinfo=timezone.utc)
    mon_next_dt = datetime.combine(monday + timedelta(days=7), time(8, 0), tzinfo=timezone.utc)
    ok = _make_job(chassis_eta=sat_dt, received=False)
    late = _make_job(chassis_eta=mon_next_dt, received=False)
    bay = f"QA-{MARK}-{uuid.uuid4().hex[:6]}"

    admin_session(page)
    _open_board(page)

    r_ok = _post(page, live_server, "/api/planning-slots",
                 {"production_job_id": ok["job_id"], "week": monday.isoformat(),
                  "bay": bay, "lane": "vacuum", "day_of_week": 5})
    assert r_ok.status == 201, r_ok.text()

    r_late = _post(page, live_server, "/api/planning-slots",
                   {"production_job_id": late["job_id"], "week": monday.isoformat(),
                    "bay": f"QA-{MARK}-{uuid.uuid4().hex[:6]}", "lane": "vacuum", "day_of_week": 5})
    assert r_late.status == 422, r_late.text()
    assert "slot day" in r_late.json()["detail"]

    # the accepted Saturday job renders with the WKND marker after a refresh
    page.reload()
    card = page.locator(f"[data-testid='cockpit-slot-cell'][data-job-id='{ok['job_id']}']")
    expect(card).to_be_visible(timeout=T)
    expect(card).to_contain_text("WKND")
    shot(page, "03-weekend-eta-gate", journey="planning_day_slots")
