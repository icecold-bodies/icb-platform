"""A11 Pre-Assembly Chute (v1.42) — journey.

Real browser over a CRAFTED floor doc (backdated enteredAt stamps = deterministic
time-travel, no clock mocking): five bodies render at their elapsed positions with the
mockup colour ramp — green (30%), warm (65%), hot (90%), ready-pulsing at the end
(125%), and a greyscale hold card with the pause badge. The andon aggregates all five.
Interactions against the REAL server: right-click holds a card (toggle_hold journaled,
card greys + freezes); a pointer drag BACK re-arms its clock (reset_timer journaled,
elapsed recomputes to the drop fraction). The merge block stays byte-identical (boundary
assert: five .m-block cells, none containing chute markup).

Floor doc saved/restored around the test; marker floor_events JCHU* purged both sides.
CSP-safe: locator waits only. The engine floor is not React — plain CSS selectors.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402

T = 20_000
JOURNEY = "pa_chute"
THRESHOLD_S = 2 * 3600          # 0038 — the ratified 2h pre_assembly threshold


def _iso_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _backdated(frac: float) -> str:
    return _iso_z(datetime.now(timezone.utc) - timedelta(seconds=frac * THRESHOLD_S))


def _body(jn: str, frac: float, *, held: bool = False, btype: str = "Chiller") -> dict:
    b = {"id": jn, "job": jn, "cust": f"Chute Cust {jn[-1]}", "len": 5.4, "type": btype,
         "status": "green", "prog": 0, "pos": 0, "days": 0, "chassisVin": "—",
         "method": "Vacuum", "enteredAt": _backdated(frac)}
    if held:
        b["held"] = True
        b["heldAt"] = _iso_z(datetime.now(timezone.utc))
        b["heldElapsedS"] = round(frac * THRESHOLD_S, 3)
    return b


def _purge(doc_state=None, doc_version=None):
    from app.database import SessionLocal
    from app.models.mes import FloorEvent, PlanFloorState
    with SessionLocal() as db:
        for e in db.query(FloorEvent).filter(FloorEvent.job_number.like("JCHU%")).all():
            db.delete(e)
        if doc_state is not None:
            row = db.get(PlanFloorState, 1)
            if row is not None:
                row.state = doc_state
                if doc_version is not None:
                    row.version = doc_version
        db.commit()


@pytest.fixture()
def chute_floor():
    """Craft the 5-bay doc: JCHU1 30% · JCHU2 65% · JCHU3 90% · JCHU4 125% (ready) ·
    JCHU5 held at 40% · Bay 5 empty. No ProductionJob rows needed — the chute is doc-driven
    and the journal tolerates unknown job numbers (production_job_id NULL)."""
    from app.database import SessionLocal
    from app.models.mes import PlanFloorState
    _purge()
    with SessionLocal() as db:
        row = db.get(PlanFloorState, 1)
        orig_state = row.state if row else None
        orig_ver = int(row.version or 0) if row else 0
        doc = {
            "v": 1,
            "pre": [
                {"id": "Bay 1", "bodies": [_body("JCHU1", 0.30)],
                 "merge": {"chassis": None, "assembly": None, "attached": None}},
                {"id": "Bay 2", "bodies": [_body("JCHU2", 0.65, btype="Freezer")],
                 "merge": {"chassis": None, "assembly": None, "attached": None}},
                {"id": "Bay 3", "bodies": [_body("JCHU3", 0.90, btype="Dryfreight")],
                 "merge": {"chassis": None, "assembly": None, "attached": None}},
                {"id": "Bay 4", "bodies": [_body("JCHU4", 1.25, btype="Insulated"),
                                            _body("JCHU5", 0.40, held=True, btype="Repair")],
                 "merge": {"chassis": None, "assembly": None, "attached": None}},
                {"id": "Bay 5", "bodies": [],
                 "merge": {"chassis": None, "assembly": None, "attached": None}},
            ],
            "qc": [], "cut": [], "cutAt": {}, "consumed": ["JCHU1", "JCHU2", "JCHU3", "JCHU4", "JCHU5"],
            "mergedJobs": [], "mergedChassis": [],
        }
        state = json.dumps(doc)
        if row is None:
            db.add(PlanFloorState(id=1, state=state, version=1))
        else:
            row.state = state
            row.version = int(row.version or 0) + 1
        db.commit()
    yield
    _purge(doc_state=orig_state, doc_version=orig_ver)


def _open_plan(page: Page) -> None:
    nav = page.get_by_test_id("nav-plan")
    expect(nav).to_be_visible(timeout=T)
    nav.click()
    page.wait_for_selector(".pa-card", timeout=T)


def _events(jn: str) -> list[str]:
    from app.database import SessionLocal
    from app.models.mes import FloorEvent
    from sqlalchemy import select
    with SessionLocal() as db:
        return [e.event_type for e in db.execute(
            select(FloorEvent).where(FloorEvent.job_number == jn)
            .order_by(FloorEvent.id)).scalars().all()]


def test_chute_renders_ramp_ready_hold_and_andon(page: Page, chute_floor) -> None:
    admin_session(page)
    _open_plan(page)

    expect(page.locator(".pa-card")).to_have_count(5, timeout=T)
    expect(page.locator(".pa-card.stage-green")).to_have_count(1)
    expect(page.locator(".pa-card.stage-warm")).to_have_count(1)
    expect(page.locator(".pa-card.stage-hot")).to_have_count(1)
    expect(page.locator(".pa-card.stage-ready")).to_have_count(1)
    expect(page.locator(".pa-card.stage-hold")).to_have_count(1)

    # ready card: tick replaces the countdown; it SITS at the chute end (>60% across)
    ready = page.locator(".pa-card.stage-ready")
    expect(ready.locator(".ready-tick")).to_have_text("✓ Ready")
    lane = page.locator(".pa-lane.chute").nth(3)
    lb, rb = lane.bounding_box(), ready.bounding_box()
    assert rb["x"] - lb["x"] > 0.6 * lb["width"], "ready card should dock at the chute end"

    # hold card: pause badge + frozen footer
    held = page.locator(".pa-card.stage-hold")
    expect(held.locator(".hold-badge")).to_be_visible()
    expect(held.locator(".csub")).to_contain_text("paused")

    # andon aggregate: 1 on track · 2 approaching (65% warm + 90% hot) · 1 ready · 1 hold
    andon = page.locator("#paAndon")
    expect(andon).to_contain_text("1 on track")
    expect(andon).to_contain_text("2 approaching")
    expect(andon).to_contain_text("1 ready")
    expect(andon).to_contain_text("1 hold")

    # bay rail: Bay 4 reads Ready (its 125% card wins) + slot dots; Bay 5 stays Available
    expect(page.locator(".pa-rail .st", has_text="Ready").first).to_be_visible()
    expect(page.locator(".chute-empty")).to_contain_text("Available — drop a panel-set to start")

    # merge-block boundary: five untouched .m-block cells, chute markup stays out of them
    expect(page.locator(".m-block")).to_have_count(5)
    assert page.locator(".m-block .pa-card").count() == 0
    shot(page, "01-chute-ramp-ready-hold", journey=JOURNEY)


def test_chute_right_click_holds_and_drag_back_resets(page: Page, chute_floor) -> None:
    admin_session(page)
    _open_plan(page)

    # right-click the green 30% card → server toggle_hold → greys + pause badge
    green = page.locator(".pa-card[data-id='JCHU1']")
    expect(green).to_be_visible(timeout=T)
    green.click(button="right")
    expect(page.locator(".pa-card[data-id='JCHU1'].stage-hold")).to_be_visible(timeout=T)
    expect(page.locator(".pa-card[data-id='JCHU1'] .hold-badge")).to_be_visible()
    assert "toggle_hold" in _events("JCHU1")
    shot(page, "02-right-click-hold", journey=JOURNEY)

    # pointer-drag the 65% card BACK to ~10% → reset_timer → stage returns to green and
    # the server doc's enteredAt re-arms to <20% elapsed
    warm = page.locator(".pa-card[data-id='JCHU2']")
    wb = warm.bounding_box()
    lane = page.locator(".pa-lane.chute").nth(1)
    lb = lane.bounding_box()
    page.mouse.move(wb["x"] + wb["width"] / 2, wb["y"] + wb["height"] / 2)
    page.mouse.down()
    page.mouse.move(lb["x"] + 30, lb["y"] + lb["height"] / 2, steps=12)
    page.mouse.up()
    expect(page.locator(".pa-card[data-id='JCHU2'].stage-green")).to_be_visible(timeout=T)
    assert "reset_timer" in _events("JCHU2")

    from app.database import SessionLocal
    from app.models.mes import PlanFloorState
    with SessionLocal() as db:
        doc = json.loads(db.get(PlanFloorState, 1).state)
        body = next(b for bay in doc["pre"] for b in bay["bodies"] if b["job"] == "JCHU2")
        entered = datetime.fromisoformat(str(body["enteredAt"]).replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - entered).total_seconds()
        assert elapsed < 0.2 * THRESHOLD_S, f"drag-back should re-arm the clock (elapsed={elapsed:.0f}s)"
    shot(page, "03-drag-back-reset", journey=JOURNEY)
