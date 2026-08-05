"""v1.44.3 — configurator Settings deletes must work INSIDE the calculator embed.

The bug (Michael 5 Aug): the Settings page's X buttons ran window.confirm, and
the /mes-app/costings/new iframe sandbox has no allow-modals — a sandboxed
native confirm() is silently blocked and returns false, so deleteNode bailed
before deleting anything. Fix: confirmModal (the in-page modal), matching the
two call sites in the same file that were already migrated.

This journey drives the REAL bug path: the embedded calculator's sidebar
"Settings" link (navigates within the frame) → pick the staged body → click a
node's X → the in-page #modal-confirm MUST appear inside the iframe (pre-fix:
nothing happened) → confirm → the node and its children are gone.

Marker J1443; purge at setup AND teardown; admin_session gets base=live_server.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "settings_confirm_modal"
MARK = "J1443"

DRAFT = {
    "nextId": 3,
    "rootIds": ["1"],
    "nodes": {
        "1": {"id": "1", "type": "folder", "label": f"{MARK} FOLDER",
              "childIds": ["2"], "parentId": None,
              "folderMode": "container", "folderValue": 0},
        "2": {"id": "2", "type": "flag", "label": f"{MARK} FLAG",
              "childIds": [], "parentId": "1",
              "flagMode": "tickbox", "flagValue": 0,
              "flagBindingName": "", "flagBindingId": None},
    },
    "itemRules": {},
}


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.configurator_drafts WHERE trailer_type_id IN "
        "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    from app.database import ConfiguratorDraft, SessionLocal, TrailerType
    with SessionLocal() as db:
        _purge(db)
        trailer = TrailerType(name=f"{MARK} SETTINGS BODY", is_active=True)
        db.add(trailer)
        db.flush()
        db.add(ConfiguratorDraft(trailer_type_id=trailer.id, payload=json.dumps(DRAFT)))
        db.commit()
        ids = {"tt_id": trailer.id}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def test_embedded_settings_delete_uses_in_page_modal(page: Page, live_server: str, staged) -> None:
    admin_session(page, base=live_server)
    page.goto("/mes-app/costings/new")
    frame = page.frame_locator("iframe[title='Calculator (live costing app)']")
    expect(frame.locator("#trailer-select")).to_be_visible(timeout=30_000)

    # The real user path: the calculator sidebar's Settings link navigates the
    # FRAME (this is exactly where native confirm() was sandbox-blocked).
    frame.locator("a[href^='/admin/settings']").first.click()
    body_select = frame.locator("select").first
    expect(body_select).to_be_visible(timeout=30_000)
    body_select.select_option(str(staged["tt_id"]))
    expect(frame.get_by_text(f"{MARK} FLAG")).to_be_visible(timeout=30_000)
    shot(page, "01-settings-in-embed", journey=JOURNEY)

    # X on the root folder → the IN-PAGE modal must appear inside the iframe.
    frame.get_by_title("Delete").first.click()
    expect(frame.locator("#modal-confirm")).to_be_visible(timeout=T)
    expect(frame.locator("#confirm-message")).to_contain_text(f"{MARK} FOLDER")
    shot(page, "02-in-page-confirm-modal", journey=JOURNEY)

    # Confirm → folder AND its child flag are gone (recursive delete ran).
    # NB: the folder name lingers in the now-HIDDEN modal's message text, so
    # the gone-checks are the flag text (never in the modal), the modal being
    # hidden, and zero remaining Delete buttons in the tree.
    frame.locator("#confirm-ok").click()
    expect(frame.locator("#modal-confirm")).to_be_hidden(timeout=T)
    expect(frame.get_by_text(f"{MARK} FLAG")).to_have_count(0, timeout=T)
    expect(frame.get_by_title("Delete")).to_have_count(0)
    shot(page, "03-node-deleted", journey=JOURNEY)


def test_cancel_keeps_the_node(page: Page, live_server: str, staged) -> None:
    """Rebuild the draft (module fixture ran once), then Cancel must keep it."""
    from app.database import ConfiguratorDraft, SessionLocal
    with SessionLocal() as db:
        row = db.query(ConfiguratorDraft).filter_by(trailer_type_id=staged["tt_id"]).first()
        row.payload = json.dumps(DRAFT)
        db.commit()

    admin_session(page, base=live_server)
    page.goto("/mes-app/costings/new")
    frame = page.frame_locator("iframe[title='Calculator (live costing app)']")
    expect(frame.locator("#trailer-select")).to_be_visible(timeout=30_000)
    frame.locator("a[href^='/admin/settings']").first.click()
    body_select = frame.locator("select").first
    expect(body_select).to_be_visible(timeout=30_000)
    body_select.select_option(str(staged["tt_id"]))
    expect(frame.get_by_text(f"{MARK} FLAG")).to_be_visible(timeout=30_000)

    frame.get_by_title("Delete").first.click()
    expect(frame.locator("#modal-confirm")).to_be_visible(timeout=T)
    frame.locator("#confirm-cancel").click()
    expect(frame.locator("#modal-confirm")).to_be_hidden(timeout=T)
    expect(frame.get_by_text(f"{MARK} FLAG")).to_be_visible()
    shot(page, "04-cancel-keeps-node", journey=JOURNEY)
