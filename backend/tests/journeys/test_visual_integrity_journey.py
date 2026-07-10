"""WO v4.36b §3.6 — Visual Integrity journey: the nav attention badge → Health Check dashboard →
drill-through renders against a deliberately-flagged chassis. Browser-level coverage of the §3.2 nav
badge + §3.3 dashboard surfaces (the API-level role-filter + flag lifecycle live in
test_visual_integrity_api.py). J436BVI marker; purge at setup AND teardown.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402

T = 15_000
JOURNEY = "visual_integrity"
_MARK = "J436BVI"
UTC = timezone.utc


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_mes.chassis_records WHERE created_source_ref LIKE 'J436BVI%'"))
    db.execute(text("DELETE FROM icb_mes.production_jobs WHERE job_number LIKE 'J436BVI%'"))
    db.commit()


@pytest.fixture(scope="module")
def flagged():
    """A live, backdated (>24h) VIN-less chassis → trips chassis_no_vin (Chassis group, RED). The
    journey server reads this same DB, so the seed is visible to the running SPA."""
    from app.database import SessionLocal
    from app.models.mes import ChassisRecord
    with SessionLocal() as db:
        _purge(db)
        rec = ChassisRecord(vin=None, customer_name="J436B VI Cust", make="HINO", model="500",
                            status="received", source="manual", created_via="manual_chassis_menu",
                            created_source_ref=f"{_MARK}-{uuid.uuid4().hex[:6]}",
                            created_at=datetime.now(UTC) - timedelta(days=2),
                            created_by="t", updated_by="t")
        db.add(rec)
        db.commit()
        db.refresh(rec)
        cid = rec.id
    yield {"chassis_id": cid}
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def test_nav_badge_to_health_check_drill(page: Page, flagged) -> None:
    """The nav 'N attention items' badge is present (≥1 flag), routes to the Health Check dashboard,
    and drilling chassis_no_vin lists the affected chassis (the §3 demo narrative, end-to-end)."""
    admin_session(page)
    badge = page.get_by_test_id("nav-flag-badge")
    expect(badge).to_be_visible(timeout=T)
    badge.click()

    expect(page.get_by_test_id("health-check")).to_be_visible(timeout=T)
    expect(page.get_by_test_id("health-total")).to_contain_text("attention")
    flagbtn = page.get_by_test_id("health-flag-chassis_no_vin")
    expect(flagbtn).to_be_visible(timeout=T)
    flagbtn.click()
    expect(page.get_by_test_id("health-drill-list")).to_be_visible(timeout=T)
    shot(page, "01-health-check-drill", journey=JOURNEY)


@pytest.fixture()
def stage_breached():
    """A job 30h into Panels Ready against an 8h threshold (stage-breach WO, v1.41.1): floor-doc
    cut entry with a v1.40.8 cutAt stamp 30h back → stage_panels_ready_overdue fires RED. Floor
    doc + threshold row saved/restored; J436BVI marker rows purged both sides."""
    import json
    from app.database import Branch, SessionLocal
    from app.models.mes import PlanFloorState, ProductionJob, ProductionStageThreshold
    jn = f"J436BVI{uuid.uuid4().hex[:4].upper()}"
    with SessionLocal() as db:
        jhb = db.query(Branch).filter_by(code="JHB").first()
        db.add(ProductionJob(branch_id=jhb.id, source="quote", status="planning",
                             job_number=jn, customer_name="J436B VI Stage Cust"))
        t = db.query(ProductionStageThreshold).filter_by(stage_code="panels_ready").one()
        orig_thr = (t.threshold_hours, t.is_active)
        t.threshold_hours, t.is_active = 8, True
        row = db.get(PlanFloorState, 1)
        created = row is None
        if created:
            row = PlanFloorState(id=1, state="{}")
            db.add(row)
        orig_state = None if created else row.state
        doc = json.loads(row.state or "{}") if not created else {}
        stamp = (datetime.now(UTC) - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        doc.setdefault("cut", []).append({"job": jn})
        doc.setdefault("cutAt", {})[jn] = stamp
        row.state = json.dumps(doc)
        db.commit()
    yield {"jn": jn}
    with SessionLocal() as db:
        t = db.query(ProductionStageThreshold).filter_by(stage_code="panels_ready").one()
        t.threshold_hours, t.is_active = orig_thr
        row = db.get(PlanFloorState, 1)
        if created and row is not None:
            db.delete(row)
        elif row is not None:
            row.state = orig_state
        db.commit()
        _purge(db)


def test_stage_breach_flag_drills_with_detail(page: Page, stage_breached) -> None:
    """Stage-threshold breach end-to-end (Michael's 10-Jul WO): the Health Check Jobs card lists
    'Panels Ready overdue', and the drill row carries the job number PLUS the measured clock
    ('30.0h of 8h') — the detail line this release adds to the drill list."""
    jn = stage_breached["jn"]
    admin_session(page)
    page.goto("/mes-app/admin/health-check")
    expect(page.get_by_test_id("health-check")).to_be_visible(timeout=T)
    flagbtn = page.get_by_test_id("health-flag-stage_panels_ready_overdue")
    expect(flagbtn).to_be_visible(timeout=T)
    expect(flagbtn).to_be_enabled(timeout=T)        # count >= 1 (disabled at zero by design)
    flagbtn.click()
    drill = page.get_by_test_id("health-drill-list")
    expect(drill).to_be_visible(timeout=T)
    row = drill.locator("li").filter(has_text=jn)
    expect(row).to_be_visible(timeout=T)
    expect(row).to_contain_text("h of 8h")          # the measured detail, threshold included
    shot(page, "02-stage-breach-drill", journey=JOURNEY)
