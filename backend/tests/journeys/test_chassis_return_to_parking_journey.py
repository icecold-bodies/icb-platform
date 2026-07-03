"""WO v4.36a.2 — return a chassis from an assembly bay back to the parking pool (re-prioritise jobs):
drag a pre-merge bay tile onto the Parking pool.

The drag is an HTML5 DataTransfer drop (unreliable to drive headlessly); this exercises the SAME chokepoint
the drop calls — POST /api/chassis-records/{id}/return-to-parking — via page.request, plus the outcome
(status 'in_assembly' → 'in_workshop', the assembly_assigned event deleted, the bay cleared), the
pre-merge guard (409 once a body is attached), the D1 panels-stay case (the bay derives 'pre_assembly',
the panels remain), role gating (workshop = RO), and the UI (the /production bay tile shows
awaiting_attachment then clears to empty, and the chassis reappears in the /plan Parking pool; the
Planning-board drag affordance retired with /planning, 3 Jul 81ddfee). Runs on icb_test (CI).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, role_session, shot  # noqa: E402  (sys.path set in conftest)
import _v435 as h  # noqa: E402

T = 15_000
JOURNEY = "return_to_parking"


@pytest.fixture(autouse=True)
def _clean():
    h.purge()
    yield
    h.purge()


def _return(page, base, chassis_id, reason=None):
    return h.api_post(page, base, f"/api/chassis-records/{chassis_id}/return-to-parking",
                      {"reason": reason} if reason is not None else {})


def _panels(page, base, job_id, bay_id):
    return h.api_post(page, base, f"/api/production-jobs/{job_id}/panels-arrived-in-bay", {"bay_id": bay_id})


# ── the return (the drag's outcome): status reverts + the bay clears ──────────────
def test_return_reverts_status_and_clears_bay(page: Page, live_server: str) -> None:
    s = h.make_assembly_job(attached=False)                    # chassis on a bay, no body → awaiting_attachment
    admin_session(page)
    assert h.bay_merge_state(s["bay_id"]) == "awaiting_attachment"
    r = _return(page, live_server, s["chassis_id"], reason="rush order needs the bay")
    assert r.status == 200, r.text()
    assert h.chassis_status(s["chassis_id"]) == "in_workshop"   # back in the parking pool
    assert h.bay_merge_state(s["bay_id"]) == "empty"            # the assembly_assigned event is gone


# ── the pre-merge guard: once a body is attached, no return to parking ────────────
def test_return_blocked_after_body_attached_409(page: Page, live_server: str) -> None:
    s = h.make_assembly_job(attached=True)                     # body attached → attached_today
    admin_session(page)
    r = _return(page, live_server, s["chassis_id"])
    assert r.status == 409 and "Awaiting QA" in r.text()
    assert h.chassis_status(s["chassis_id"]) == "in_assembly"  # unchanged — the return was refused


# ── D1: panels staged in the bay STAY — the bay derives pre_assembly ──────────────
def test_return_with_panels_leaves_pre_assembly(page: Page, live_server: str) -> None:
    """Also the v4.36a.3 NON-regression guard: the panel-consumption gate (panels are consumed only when
    the job's chassis has body_attached) must NOT over-reach to this NO-body path — a returned chassis's
    panels stay LOOSE ('pre_assembly'), move-back affordance intact. body_attached is the only gate."""
    s = h.make_assembly_job(attached=False)
    admin_session(page)
    assert _panels(page, live_server, s["job_id"], s["bay_id"]).status == 201
    assert h.bay_merge_state(s["bay_id"]) == "ready_to_merge"   # chassis + its own panels
    assert _return(page, live_server, s["chassis_id"]).status == 200
    assert h.chassis_status(s["chassis_id"]) == "in_workshop"
    assert h.bay_merge_state(s["bay_id"]) == "pre_assembly"     # panels remain, no chassis (D1: not blocked)
    assert h.panels_event_count(s["job_id"]) == 1              # the panels event is untouched


# ── role gating (workshop is read-only, no return affordance) ─────────────────────
def test_workshop_cannot_return(page: Page, live_server: str, role_users) -> None:
    s = h.make_assembly_job(attached=False)
    role_session(page, role_users["workshop"], base=live_server)
    r = _return(page, live_server, s["chassis_id"])
    assert r.status == 403
    assert h.chassis_status(s["chassis_id"]) == "in_assembly"   # untouched


# ── UI: the /production bay tile clears after the return; the chassis reappears in /plan Parking ──
def test_production_bay_clears_and_chassis_returns_to_plan_parking(page: Page, live_server: str) -> None:
    s = h.make_assembly_job(attached=False)
    admin_session(page)
    h.open_production(page)
    tile = page.locator(f'[data-testid="production-bay-tile"][data-bay-code="{s["bay_code"]}"]')
    expect(tile).to_have_attribute("data-bay-state", "awaiting_attachment", timeout=T)
    shot(page, "01-bay-tile-awaiting-attachment", journey=JOURNEY)
    # the drop's chokepoint, then reload to see the post-return floor (bay clears, chassis back in Parking)
    assert _return(page, live_server, s["chassis_id"], reason="bumped for a rush order").status == 200
    page.reload()
    page.wait_for_selector("[data-testid='production-kpis']", timeout=T)
    expect(page.locator(f'[data-testid="production-bay-tile"][data-bay-code="{s["bay_code"]}"]')).to_have_attribute(
        "data-bay-state", "empty", timeout=T)                                   # the bay tile flipped to empty
    nav = page.get_by_test_id("nav-plan")
    expect(nav).to_be_visible(timeout=T)
    nav.click()
    card = page.locator(f'#parking .ccard[data-id="{s["vin"]}"]')               # live Parking: in_workshop → ccard
    expect(card).to_be_visible(timeout=T)                                       # chassis back in the Parking pool
    shot(page, "02-returned-to-parking", journey=JOURNEY)
