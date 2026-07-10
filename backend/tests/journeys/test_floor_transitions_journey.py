"""§9 P1 (v1.41.0) — server-confirmed floor drags (journey).

Real browser, real drags, server-authoritative floor: (1) HTML5-drag a scheduled V/P card
down to Panels Ready → the rail card appears only after the server confirms (declare_cut
journaled); (2) pointer-drag the panel-set into an assembly bay → body on the track
(start_body journaled); (3) a STALE drag — the body vanishes server-side behind the
browser's back — is rejected with a toast and no local mutation; (4) the admin Floor
Reset page (typed confirm) empties the shared floor and journals floor_reset.

Floor doc saved/restored around the test; marker rows JFLW* purged both sides.
CSP-safe: locator waits only. The engine's floor is not React — plain CSS selectors.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402

T = 20_000
JOURNEY = "floor_transitions"


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _purge(doc_state=None, doc_version=None):
    from app.database import CalculationRecord, SessionLocal
    from app.models.mes import FloorEvent, PlanFloorState, PlanningSlot, ProductionJob
    with SessionLocal() as db:
        for pj in db.query(ProductionJob).filter(ProductionJob.job_number.like("JFLW%")).all():
            for s in db.query(PlanningSlot).filter_by(production_job_id=pj.id).all():
                db.delete(s)
            cid = pj.calculation_record_id
            db.delete(pj)
            if cid:
                c = db.get(CalculationRecord, cid)
                if c and (c.quote_number or "").startswith("Q-JFLW"):
                    db.delete(c)
        for e in db.query(FloorEvent).filter(
                (FloorEvent.job_number.like("JFLW%"))
                | (FloorEvent.event_type == "floor_reset")).all():
            db.delete(e)
        if doc_state is not None:
            row = db.get(PlanFloorState, 1)
            if row is not None:
                row.state = doc_state
                if doc_version is not None:
                    row.version = doc_version
        db.commit()


@pytest.fixture()
def floor_fixture():
    from app.database import Branch, CalculationRecord, SessionLocal, User
    from app.models.mes import PlanFloorState, ProductionJob
    from app.services import planning as pl
    _purge()
    with SessionLocal() as db:
        row = db.get(PlanFloorState, 1)
        orig_state = row.state if row else None
        orig_ver = int(row.version or 0) if row else 0
        admin = db.query(User).filter_by(username="admin").first()
        jhb = db.query(Branch).filter_by(code="JHB").first()
        c = CalculationRecord(quote_number=f"Q-JFLW{uuid.uuid4().hex[:6]}", status="accepted",
                              branch_id=jhb.id,
                              dimensions_json=json.dumps({"body_type": "5.4m Chiller Body"}),
                              result_json=json.dumps({"selling_zar": 1000.0}))
        db.add(c)
        db.commit()
        db.refresh(c)
        pj = ProductionJob(calculation_record_id=c.id, branch_id=jhb.id,
                           job_number=f"JFLW{c.id}", status="planning",
                           chassis_received_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        db.add(pj)
        db.commit()
        db.refresh(pj)
        # today's slot on a REAL cockpit vacuum bay (probe past seeded occupancy)
        today = date.today()
        slot_err = None
        for bay in ("V-5", "V-4", "V-3", "V-2", "V-1"):
            try:
                pl.schedule(db, production_job_id=pj.id, week=_monday(today), bay=bay,
                            lane="vacuum", day_of_week=today.weekday(), user=admin)
                break
            except pl.CellOccupiedError as e:  # noqa: PERF203
                slot_err = e
        else:
            raise AssertionError(f"no free vacuum bay: {slot_err}")
        jn = pj.job_number
    yield {"jn": jn}
    _purge(doc_state=orig_state, doc_version=orig_ver)


def _drag(page: Page, source, target) -> None:
    """Pointer drag for the engine's pointerdown/move/up plumbing (not HTML5 DnD).
    Scrolls each end into view — the floor sections live below the fold, and unlike
    Playwright's drag_to (used for the HTML5 leg) raw mouse moves never auto-scroll."""
    source.scroll_into_view_if_needed()
    sb = source.bounding_box()
    assert sb
    page.mouse.move(sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2)
    page.mouse.down()
    page.mouse.move(sb["x"] + sb["width"] / 2 + 12, sb["y"] + sb["height"] / 2 + 12, steps=3)
    target.scroll_into_view_if_needed()
    tb = target.bounding_box()
    assert tb
    for i in range(1, 7):
        page.mouse.move(sb["x"] + (tb["x"] + tb["width"] / 2 - sb["x"]) * i / 6,
                        sb["y"] + (tb["y"] + tb["height"] / 2 - sb["y"]) * i / 6, steps=3)
    page.mouse.up()


def _events(jn: str) -> list[str]:
    from app.database import SessionLocal
    from app.models.mes import FloorEvent
    from sqlalchemy import select
    with SessionLocal() as db:
        return [e.event_type for e in db.execute(
            select(FloorEvent).where(FloorEvent.job_number == jn)
            .order_by(FloorEvent.id)).scalars().all()]


def test_server_confirmed_floor_drags(page: Page, floor_fixture) -> None:
    jn = floor_fixture["jn"]
    admin_session(page)
    page.goto("/mes-app/plan")

    # (1) declare-cut: HTML5-drag the scheduled cockpit card down onto the Panels-Ready rail
    card = page.locator(f"[data-testid='cockpit-slot-cell'][data-job-id]").filter(has_text=jn).first
    expect(card).to_be_visible(timeout=30_000)
    rail = page.locator("#panels")
    expect(rail).to_be_visible(timeout=T)
    card.drag_to(rail)
    pcard = page.locator(f".pcard:has-text('{jn}')")
    expect(pcard).to_be_visible(timeout=T)          # appears only after the server confirmed
    assert _events(jn) == ["declare_cut"]
    shot(page, "01-declared-cut", journey=JOURNEY)

    # (2) start-body: pointer-drag the panel-set into assembly bay 1's lane
    lane = page.locator(".pa-lane").first
    expect(lane).to_be_visible(timeout=T)
    _drag(page, pcard, lane)
    body = page.locator(f".body-wrap[data-id='{jn}']").first   # track bodies render images only — data-id is the handle
    expect(body).to_be_visible(timeout=T)
    assert _events(jn) == ["declare_cut", "start_body"]
    shot(page, "02-body-started", journey=JOURNEY)

    # (3) STALE drag → server 409 → toast, no local mutation: erase the body server-side
    #     behind the browser's back, then drag the still-rendered card to the merge block.
    from app.database import SessionLocal
    from app.models.mes import PlanFloorState
    with SessionLocal() as db:
        row = db.get(PlanFloorState, 1)
        doc = json.loads(row.state)
        for bay in doc["pre"]:
            bay["bodies"] = [b for b in bay["bodies"] if str(b.get("job")) != jn]
        row.state = json.dumps(doc)
        row.version = int(row.version or 0) + 1
        db.commit()
    merge_block = page.locator(".m-block").first
    _drag(page, body, merge_block)
    # the server rejects (body not found in the doc) → toast surfaces the message
    expect(page.get_by_test_id('toast').first).to_be_visible(timeout=T)
    assert "drop_assembly" not in _events(jn)
    shot(page, "03-stale-drag-toast", journey=JOURNEY)

    # (4) admin floor reset: typed confirm → empty floor + journaled
    page.goto("/mes-app/admin/floor-reset")
    expect(page.get_by_test_id("floor-reset-admin")).to_be_visible(timeout=T)
    page.get_by_test_id("floor-reset-confirm-input").fill("RESET")
    page.get_by_test_id("floor-reset-button").click()
    from app.models.mes import FloorEvent
    from sqlalchemy import select
    def _reset_logged() -> bool:
        with SessionLocal() as db:
            return bool(db.execute(select(FloorEvent).where(
                FloorEvent.event_type == "floor_reset")).scalars().first())
    # Success signal = the toast (the component CLEARS the typed confirm on success,
    # which re-disables the button by design — asserting enabled here was wrong).
    expect(page.get_by_test_id("toast").first).to_be_visible(timeout=T)
    assert _reset_logged(), "floor_reset must be journaled"
    shot(page, "04-floor-reset", journey=JOURNEY)
