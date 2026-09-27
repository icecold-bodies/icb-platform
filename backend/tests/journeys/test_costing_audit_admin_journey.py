"""v1.59 — Admin -> Costing audit, clicked through the way Michael uses it
(BA dispatch 3 §3.4): fix -> run -> compare.

One stateful click-through in ONE browser context (banked: stateful loops are one
test), then the non-admin in a second, fresh context:

  * the menu entry is there for the admin, in the admin group
  * the header says, in plain words, which environment this is
  * Run on `smoke` returns at once, shows progress, and ends passed/flagged
  * the report renders in the page in the v1.57.2 layout (grid top, sections /
    lines bottom, the divider) — inside its own frame
  * Download HTML / Download CSV hand back attachments
  * running smoke AGAIN says "No change since …" (same data, same result)
  * the history lists both runs, newest first
  * a non-admin sees no menu entry and gets 403 from the page and the API

The journey server is a separate process, so the pricing data it audits must be
COMMITTED: the committed MES snapshot is loaded for the test and removed again row by
row by primary key (never by name — the shared test DB has other rows).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import BrowserContext, Page, expect

from _common import ROLE_USERS, shot  # noqa: E402

T = 15_000
RUN_T = 120_000
JOURNEY = "costing_audit_admin"


@pytest.fixture()
def audit_data():
    """The MES master data the smoke pack prices, for the journey server to read."""
    from tools.costing_audit.mes_snapshot import load_snapshot, snapshot_path, unload_snapshot
    inserted: dict = {}
    load_snapshot(snapshot_path("all"), inserted=inserted, log=lambda *_: None)
    yield
    unload_snapshot(inserted, log=lambda *_: None)


@pytest.fixture()
def run_ids():
    """The run records this journey creates — deleted BY ID afterwards."""
    ids: list[int] = []
    yield ids
    from sqlalchemy import text
    from app.database import SessionLocal
    if ids:
        with SessionLocal() as db:
            db.execute(text("DELETE FROM icb_costings.costing_audit_runs WHERE id = ANY(:ids)"), {"ids": ids})
            db.commit()


def _login(page: Page, base: str, username: str) -> None:
    """Mint `username`'s session in this browser context (the autologin role_session uses)."""
    base = base.rstrip("/")
    r = page.request.post(f"{base}/api/mes/autologin", data={"username": username}, headers={"Origin": base})
    assert r.ok, f"autologin as {username!r} failed: HTTP {r.status}"


def _run_smoke(page: Page, run_ids: list[int]) -> int:
    page.get_by_test_id("ca-pack").select_option("smoke")
    with page.expect_response(lambda r: r.url.endswith("/api/admin/costing-audit/runs")
                              and r.request.method == "POST") as posted:
        page.get_by_test_id("ca-run").click()
    resp = posted.value
    assert resp.status == 202, resp.text()
    rid = resp.json()["id"]
    run_ids.append(rid)
    expect(page.get_by_test_id("ca-current")).to_contain_text(f"Run #{rid}", timeout=T)
    # poll on STATE (banked): the run has ended when its status badge leaves 'running'
    status = page.get_by_test_id("ca-status")
    expect(status).not_to_have_text("running", timeout=RUN_T)
    assert status.inner_text().strip().lower() in ("passed", "flagged"), status.inner_text()
    return rid


def test_admin_runs_the_audit_and_sees_what_changed(
        page: Page, browser_context: BrowserContext, live_server, audit_data, run_ids, role_users) -> None:
    base = live_server.rstrip("/")
    _login(page, base, "admin")
    page.goto("/admin/costing-audit")

    # menu entry + plain-words header
    expect(page.get_by_test_id("nav-costing-audit")).to_be_visible(timeout=T)
    expect(page.get_by_test_id("ca-environment")).to_contain_text("Development", timeout=T)
    expect(page.get_by_test_id("ca-accepted-list")).to_contain_text("accepted_differences.yaml")
    shot(page, "01-page", JOURNEY)

    # first run
    first = _run_smoke(page, run_ids)
    report = page.frame_locator("[data-testid='ca-report']")
    expect(report.locator("#grid .st[data-sid]")).to_have_count(18, timeout=T)       # 18 smoke scenarios
    expect(report.locator("#divider")).to_be_visible()
    expect(report.locator("#left h2")).to_be_visible(timeout=T)                        # sections of the opened scenario
    expect(report.locator("#right h3")).to_be_visible(timeout=T)                       # lines of the opened section
    expect(page.get_by_test_id("ca-changes")).to_be_visible(timeout=T)
    expect(page.get_by_test_id("ca-current-head")).to_contain_text("ran by admin")
    shot(page, "02-first-run-report", JOURNEY)

    # downloads are attachments, never cached
    for tid, ext in (("ca-download-html", ".html"), ("ca-download-csv", ".csv")):
        href = page.get_by_test_id(tid).get_attribute("href")
        r = page.request.get(f"{base}{href}")
        assert r.status == 200, (tid, r.status)
        assert r.headers["content-disposition"].startswith("attachment;") and r.headers["content-disposition"].endswith(f'{ext}"')
        assert r.headers["cache-control"].startswith("no-store")

    # second run: same data -> "No change since …"
    second = _run_smoke(page, run_ids)
    assert second != first
    expect(page.get_by_test_id("ca-no-change")).to_be_visible(timeout=T)
    expect(page.get_by_test_id("ca-no-change")).to_contain_text("No change since")
    expect(page.get_by_test_id("ca-changes")).to_contain_text(f"run #{first}")
    shot(page, "03-no-change-since", JOURNEY)

    # history: both runs, newest first, each can be opened
    rows = page.get_by_test_id("ca-history-row")
    expect(rows.first).to_be_visible(timeout=T)
    ids = [int(x) for x in rows.evaluate_all("els => els.map(e => e.dataset.id)")]
    assert ids.index(second) < ids.index(first)
    page.locator(f"[data-testid='ca-open-run'][data-open='{first}']").click()
    expect(page.get_by_test_id("ca-current")).to_contain_text(f"Run #{first}", timeout=T)
    shot(page, "04-history-open-first", JOURNEY)

    # a non-admin, in a fresh context: no menu entry, 403 from the page and the API
    other = browser_context.browser.new_context(base_url=base, viewport={"width": 1440, "height": 900})
    try:
        p2 = other.new_page()
        p2.set_default_timeout(T)
        _login(p2, base, ROLE_USERS["sales"])
        p2.goto("/calculator")
        expect(p2.locator(".sidebar-nav")).to_be_visible(timeout=T)
        expect(p2.get_by_test_id("nav-costing-audit")).to_have_count(0)
        csrf = p2.locator('meta[name="csrf-token"]').get_attribute("content")
        shot(p2, "05-non-admin-no-menu-entry", JOURNEY)
        resp = p2.goto("/admin/costing-audit")
        assert resp.status == 403, resp.status
        api = p2.request.get(f"{base}/api/admin/costing-audit/runs")
        assert api.status == 403 and api.json()["detail"] == "Permission denied: admin.costing_audit"
        # a valid CSRF token, so the 403 below is the PERMISSION gate, not the CSRF check
        post = p2.request.post(f"{base}/api/admin/costing-audit/runs", data={"pack": "smoke"},
                               headers={"Origin": base, "X-CSRF-Token": csrf or ""})
        assert post.status == 403 and post.json()["detail"] == "Permission denied: admin.costing_audit", post.text()
    finally:
        other.close()
