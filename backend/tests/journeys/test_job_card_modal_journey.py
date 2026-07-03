"""WO v4.31 §3.5 — Job-card (JobCardSections) per-role journey: admin + planner (+ workshop price-hide).

3 Jul retirement: the Planning Board host is UNROUTED (/planning → /plan redirect), so the journey
now opens the SAME JobCardSections render in the /production bay side-panel — identical component,
identical GET /api/production-jobs/{id} enrichment; every assertion carries over verbatim.

Per Testing Strategy v1.1: admin + the primary affected role (planner opens the modal most often).
A third context covers the §0.5-locked workshop render: BOM lines visible, PRICE columns hidden —
a render-time display choice that a future dev could silently regress, so it gets durable journey
coverage here. Self-contained scenario fixture (job + current BOM [priced + null-price lines] +
in_assembly chassis with VCL checklist/notes + a current-week slot); cleaned up at module end.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, role_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "job_card_modal"


@pytest.fixture(scope="module")
def modal_scenario():
    """Job with full §3.2 enrichment; its chassis occupies a FREE assembly bay (occupancy is
    event-derived, ONE occupant per bay — demo seeds park chassis on bays, so a pinned bay is
    non-deterministic). Returns (job_number, bay_code)."""
    from app.database import Branch, SessionLocal
    from app.models.mes import (
        AssemblyBay, BomLine, ChassisLifecycleEvent, ChassisRecord, GeneratedBom,
        PlanningSlot, ProductionJob,
    )
    from app.services.chassis import current_occupants
    tag = uuid.uuid4().hex[:6]
    monday = date.today() - timedelta(days=date.today().weekday())
    with SessionLocal() as db:
        jhb = db.query(Branch).filter_by(code="JHB").first()
        occupied = set(current_occupants(db))
        bay = (db.query(AssemblyBay).filter_by(is_active=True)
               .filter(~AssemblyBay.id.in_(occupied or {0}))
               .order_by(AssemblyBay.sort_order).first())
        assert bay is not None, "no free assembly bay on this DB — clear a bay or reseed first"
        rec = ChassisRecord(vin=f"JRNYMJ{tag.upper()}", source="manual", status="in_assembly",
                            make="ISUZU", model="FTR 850", customer_name="Journey Modal Ltd")
        db.add(rec)
        db.commit()
        db.refresh(rec)
        db.add(ChassisLifecycleEvent(
            chassis_record_id=rec.id, cycle_number=1, event_type="VCL", event_date=date.today(),
            checklist_json={"tyres": True, "mileage": "98000"}, notes="journey condition note"))
        db.add(ChassisLifecycleEvent(
            chassis_record_id=rec.id, cycle_number=1, event_type="assembly_assigned",
            assembly_bay_id=bay.id, event_date=date.today()))
        job = ProductionJob(branch_id=jhb.id, source="workbook", status="in_production",
                            job_number=f"QAMJ{tag}", chassis_record_id=rec.id)
        db.add(job)
        db.commit()
        db.refresh(job)
        gb = GeneratedBom(production_job_id=job.id, version=1, bom_status="complete",
                          grand_total=1000, current=True)
        db.add(gb)
        db.commit()
        db.refresh(gb)
        db.add(BomLine(generated_bom_id=gb.id, sap_code="INS-PUR-50", description="PUR panel 50mm",
                       qty=4, unit_price=250, line_total=1000, section="Walls", line_order=1))
        db.add(BomLine(generated_bom_id=gb.id, sap_code="UNRESOLVED", description="EPS 24DV 42mm",
                       qty=2, unit_price=None, line_total=None, section="Roof", line_order=2))
        job.current_bom_id = gb.id
        db.add(PlanningSlot(production_job_id=job.id, week=monday, bay="QA-MJ", lane="test",
                            slot_position=99, status="scheduled"))
        db.commit()
        ids = (job.id, rec.id, job.job_number, bay.code)
    yield ids[2], ids[3]
    with SessionLocal() as db:
        for s in db.query(PlanningSlot).filter_by(production_job_id=ids[0]).all():
            db.delete(s)
        db.commit()
        j = db.get(ProductionJob, ids[0])
        if j:
            db.delete(j)                                  # cascades the BOM + lines
        db.commit()
        r = db.get(ChassisRecord, ids[1])
        if r:
            db.delete(r)                                  # cascades the events
        db.commit()


def _open_modal(page: Page, job_number: str) -> None:
    # 3 Jul: nav-planning / slot-cell are unrouted (Planning Board retired). The SAME
    # JobCardSections render lives in the /production bay side-panel (ProductionDashboard.tsx).
    page.goto("/mes-app/production")
    expect(page.get_by_test_id("production-kpis")).to_be_visible(timeout=T)
    tile = page.get_by_test_id("production-bay-tile").filter(has_text=job_number).first
    expect(tile).to_be_visible(timeout=T)
    tile.click()
    expect(page.get_by_test_id("production-bay-panel")).to_be_visible(timeout=T)
    expect(page.get_by_test_id("jobcard-bom")).to_be_visible(timeout=T)


def test_job_card_modal_admin_full_render(page: Page, modal_scenario) -> None:
    job_number, bay_code = modal_scenario
    admin_session(page)
    _open_modal(page, job_number)
    # chassis section: latest-VCL checklist + condition notes
    chassis = page.get_by_test_id("jobcard-chassis")
    expect(chassis.get_by_text("tyres")).to_be_visible(timeout=T)
    expect(chassis.get_by_text("journey condition note")).to_be_visible(timeout=T)
    # BOM section: prices visible for admin; null price renders an em-dash
    bom = page.get_by_test_id("jobcard-bom")
    expect(bom.get_by_text("Unit price")).to_be_visible(timeout=T)
    expect(bom.get_by_text("INS-PUR-50")).to_be_visible(timeout=T)
    expect(bom.locator("tr").filter(has_text="UNRESOLVED").get_by_text("—").first).to_be_visible(timeout=T)
    # bay context: derived current bay + since-date
    bay = page.get_by_test_id("jobcard-bay")
    expect(bay.get_by_text(bay_code)).to_be_visible(timeout=T)
    shot(page, "01-jobcard-admin", journey=JOURNEY)


def test_job_card_modal_planner_sees_prices(page: Page, live_server: str, role_users, modal_scenario) -> None:
    job_number, bay_code = modal_scenario
    role_session(page, role_users["planner"], base=live_server)
    _open_modal(page, job_number)
    expect(page.get_by_test_id("jobcard-chassis").get_by_text("journey condition note")).to_be_visible(timeout=T)
    expect(page.get_by_test_id("jobcard-bom").get_by_text("Unit price")).to_be_visible(timeout=T)
    expect(page.get_by_test_id("jobcard-bay").get_by_text(bay_code)).to_be_visible(timeout=T)
    shot(page, "02-jobcard-planner", journey=JOURNEY)


def test_job_card_modal_workshop_prices_hidden(page: Page, live_server: str, role_users, modal_scenario) -> None:
    # §0.5 lock: workshop sees chassis detail + BOM LINES but NOT pricing (render-time hide).
    job_number, _ = modal_scenario
    role_session(page, role_users["workshop"], base=live_server)
    _open_modal(page, job_number)
    bom = page.get_by_test_id("jobcard-bom")
    expect(bom.get_by_text("SAP code")).to_be_visible(timeout=T)                  # lines visible
    expect(bom.get_by_text("INS-PUR-50")).to_be_visible(timeout=T)
    expect(bom.get_by_text("Unit price")).to_have_count(0)                        # pricing hidden
    expect(bom.get_by_text("Line total")).to_have_count(0)
    expect(bom.get_by_text("Grand total")).to_have_count(0)
    expect(page.get_by_test_id("jobcard-chassis").get_by_text("journey condition note")).to_be_visible(timeout=T)
    shot(page, "03-jobcard-workshop-prices-hidden", journey=JOURNEY)
