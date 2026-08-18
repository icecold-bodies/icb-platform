"""WO v4.31 §3.5 — Unified Costings dashboard per-role journey: admin + sales.

Per Testing Strategy v1.1: admin + the primary affected role (sales lives in the dashboard).
Asserts, per role, that the full dashboard + §3.4 KPI strip render on /costings — and that
/costings/new is the calculator ONLY.

The §0.13 "same component, compressed below the calculator" contract was RETIRED on 18 Aug
(Michael): the embed duplicated the page that owns the list and turned a scroll inside an
unfinished costing into a wall of other people's costings. Context 2 now pins its ABSENCE.
Read-path only — no mutations.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from _common import admin_session, role_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "costings_unified"


def _assert_both_contexts(page: Page, prefix: str) -> None:
    # Context 1 — /costings: full dashboard + KPI strip + table.
    nav = page.get_by_test_id("nav-costings")
    expect(nav).to_be_visible(timeout=T)
    nav.click()
    expect(page.get_by_test_id("costings-dashboard")).to_be_visible(timeout=T)
    kpis = page.get_by_test_id("costings-kpis")
    expect(kpis).to_be_visible(timeout=T)
    expect(kpis.get_by_text("Quotes this week")).to_be_visible(timeout=T)
    expect(kpis.get_by_text("Approval rate")).to_be_visible(timeout=T)
    expect(page.get_by_test_id("costings-table")).to_be_visible(timeout=T)
    shot(page, f"{prefix}-costings-full", journey=JOURNEY)

    # Context 2 — /costings/new is the CALCULATOR ONLY (Michael, 18 Aug). The compressed
    # dashboard that used to sit below it was removed: scrolling down inside a costing you
    # are still building surfaced the whole costings list, duplicating the page that owns
    # that job. Asserted as an ABSENCE, and AFTER scrolling to the bottom — a list rendered
    # below the fold is precisely what the complaint was, so a top-of-page check would pass
    # on the very layout being removed.
    page.goto("/mes-app/costings/new")
    expect(page.locator("iframe[title='Calculator (live costing app)']")).to_be_visible(timeout=T)
    page.mouse.wheel(0, 20_000)
    page.wait_for_timeout(300)
    # Both testids DO exist — on /costings, asserted in context 1 above — so their absence
    # here is a real check. (The old `costings-dashboard-embedded` id is deliberately NOT
    # asserted: the prop that produced it is gone, so the assertion could never fail.)
    expect(page.get_by_test_id("costings-dashboard")).to_have_count(0)
    expect(page.get_by_test_id("costings-table")).to_have_count(0)
    shot(page, f"{prefix}-costings-new-calculator-only", journey=JOURNEY)


def test_costings_unified_admin(page: Page, live_server: str) -> None:
    # base=live_server, not a bare admin_session(page): the bare form defaults to
    # http://127.0.0.1:8000, so on a side-port run it mints the session against a
    # DIFFERENT server and this test fails for reasons that have nothing to do with
    # the dashboard. The sales test below was already base-aware.
    admin_session(page, base=live_server)
    _assert_both_contexts(page, "01-admin")


def test_costings_unified_sales(page: Page, live_server: str, role_users) -> None:
    # Sales reps live in the dashboard (and create costings on the calculator page).
    role_session(page, role_users["sales"], base=live_server)
    _assert_both_contexts(page, "02-sales")
