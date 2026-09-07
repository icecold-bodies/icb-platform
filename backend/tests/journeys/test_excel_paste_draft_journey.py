"""v1.53 — Excel paste on a DRAFT-rendered (masterless v2) body.

The v1.42 paste feature matched pasted labels only against is_body_option
master rows, and its journey coverage deliberately stopped at flat-panel
bodies ("CI has no v2 configurator draft" — test_excel_paste_journey.py).
Michael then hit exactly that hole on Manni RIGIDS CB (7 Sep): 104 BOM rows,
ZERO masters, panel rendered purely from the Explorer draft — the modal said
"Select a body type first — nothing to match against." with a body selected,
and every option row fell out "not recognised".

This journey stages that body shape (configurator_v2, no masters, a draft
with radio door FOLDERS + radio flags + tickbox flags) and asserts the fix:
the misleading warning is gone, labels match the draft vocabulary, a Y on a
door-side flag derives the containing DOOR folder switch, ticks select and
deselect, thickness on a name-only flag is honestly skipped, and Apply drives
the rendered panel's own inputs. A second test proves the both-doors conflict
is rejected as a data error (and takes its branch selections with it).

JXPD markers; purge at setup AND teardown; admin_session gets base=live_server.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "excel_paste_draft"
MARK = "JXPD"


def _purge(db) -> None:
    from sqlalchemy import text
    tt_sub = "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"
    db.execute(text(
        f"DELETE FROM icb_costings.configurator_drafts WHERE trailer_type_id IN {tt_sub}"),
        {"m": f"{MARK}%"})
    db.execute(text(
        f"DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN {tt_sub}"),
        {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


def _draft() -> dict:
    """DOOR TYPE (container) → DRD/SRD radio FOLDERS with EPS/PU radio flags
    (SRD initially the door), plus a FLOOR category with two tickbox flags
    (RICE initially on). DRD/SRD flags carry flagBindingName; the floor flags
    are label-only — both draft-vocabulary lookups are exercised."""
    def flag(nid, label, parent, mode, val, bind=""):
        return {"id": nid, "type": "flag", "label": label, "parentId": parent,
                "childIds": [], "flagMode": mode, "flagValue": val,
                "flagBindingName": bind, "flagBindingId": None}
    return {
        "nextId": 11,
        "rootIds": ["1", "8"],
        "nodes": {
            "1": {"id": "1", "type": "folder", "label": "DOOR TYPE", "parentId": None,
                  "childIds": ["2", "3"], "folderMode": "container", "folderValue": 0},
            "2": {"id": "2", "type": "folder", "label": f"{MARK} DRD DOORS", "parentId": "1",
                  "childIds": ["4", "5"], "folderMode": "radio", "folderValue": 0},
            "3": {"id": "3", "type": "folder", "label": f"{MARK} SRD DOORS", "parentId": "1",
                  "childIds": ["6", "7"], "folderMode": "radio", "folderValue": 1},
            "4": flag("4", f"{MARK} DRD EPS", "2", "radio", 0, bind=f"{MARK} DRD EPS"),
            "5": flag("5", f"{MARK} DRD PU", "2", "radio", 0, bind=f"{MARK} DRD PU"),
            "6": flag("6", f"{MARK} SRD EPS", "3", "radio", 1, bind=f"{MARK} SRD EPS"),
            "7": flag("7", f"{MARK} SRD PU", "3", "radio", 0, bind=f"{MARK} SRD PU"),
            "8": {"id": "8", "type": "category", "label": f"{MARK} FLOOR",
                  "sourceCategoryKey": None, "parentId": None, "childIds": ["9", "10"]},
            "9": flag("9", f"{MARK} FINN PLY FLOOR", "8", "tickbox", 0),
            "10": flag("10", f"{MARK} RICE GRAIN", "8", "tickbox", 1),
        },
        "itemRules": {},
    }


@pytest.fixture(scope="module")
def staged():
    from app.database import (
        BillOfMaterial, ConfiguratorDraft, Material, SessionLocal, TrailerType,
    )
    with SessionLocal() as db:
        _purge(db)
        trailer = TrailerType(name=f"{MARK} DRAFT BODY", is_active=True,
                              configurator_v2=True,
                              default_length=4.0, default_width=2.0, default_height=2.0)
        m1 = Material(name=f"{MARK} PANEL", unit_of_measure="each", price_per_unit=1.0)
        m2 = Material(name=f"{MARK} RIVETS", unit_of_measure="each", price_per_unit=1.0)
        db.add_all([trailer, m1, m2])
        db.flush()
        # Plain items only — the Manni RIGIDS CB shape: a real BOM, ZERO masters.
        db.add(BillOfMaterial(trailer_type_id=trailer.id, material_id=m1.id,
                              formula_expression="1", bom_section=f"{MARK} SIDES"))
        db.add(BillOfMaterial(trailer_type_id=trailer.id, material_id=m2.id,
                              formula_expression="2", bom_section=f"{MARK} SIDES"))
        db.add(ConfiguratorDraft(trailer_type_id=trailer.id, payload=json.dumps(_draft())))
        db.commit()
        ids = {"trailer": trailer.id}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _open_paste_modal(page: Page, base: str, trailer_id: int) -> None:
    admin_session(page, base=base)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(trailer_id))
    # Draft renderer attached = the staged flags exist as draft inputs; SRD is
    # the seeded door and RICE starts ticked (the paste must flip both).
    expect(page.locator(f"input[data-draft-flag='{MARK} SRD EPS']")).to_be_attached(timeout=T)
    expect(page.locator("input[data-draft-folder='3']")).to_be_checked()
    expect(page.locator(f"input[data-draft-flag='{MARK} RICE GRAIN']")).to_be_checked()
    page.locator("#excel-paste-btn").click()
    expect(page.locator("#modal-excel-paste")).to_be_visible(timeout=T)


def test_draft_body_paste_preview_and_apply(page: Page, live_server: str, staged) -> None:
    _open_paste_modal(page, live_server, staged["trailer"])
    apply_btn = page.locator("#excel-paste-apply")
    expect(apply_btn).to_be_disabled()

    page.locator("#excel-paste-input").fill("\n".join([
        "LENGTH\t\t6.5\t6.55",
        "WIDTH\t\t2.5",
        "HEIGHT\t\t2.4",
        f"{MARK} DRD EPS\t\t0.06\tY",     # flips the door folder; thickness has no row → honest skip
        f"{MARK} DRD PU\t\t\tN",
        f"{MARK} SRD EPS\t\t\tN",
        f"{MARK} SRD PU\t\t\tN",
        f"{MARK} FINNPLY FLOOR\t\t\tY",   # spacing drift vs the draft label — squash-matched
        f"{MARK} RICE GRAIN\t\t\tN",
        f"{MARK} UNKNOWN THING\t\t\tY",
    ]))

    preview = page.locator("#excel-paste-preview")
    # THE bug under test: a selected draft body must never show the
    # "Select a body type first" warning.
    expect(preview.locator("[data-xp-row='dim']")).to_have_count(3, timeout=T)
    expect(preview.locator("[data-xp-row='warn']")).to_have_count(0)
    # Draft matches: the chosen door-side flag + its DERIVED door folder…
    expect(preview.locator(f"[data-xp-row='draftsel'][data-xp-label='{MARK} DRD EPS']")).to_contain_text("selected (explorer)")
    expect(preview.locator(f"[data-xp-row='draftsel'][data-xp-label='{MARK} DRD DOORS']")).to_contain_text("follows the option below")
    # …tick + detick, the honest thickness skip, the no-Y radio group, unknown.
    expect(preview.locator(f"[data-xp-row='drafttick'][data-xp-label='{MARK} FINNPLY FLOOR']")).to_contain_text("selected")
    expect(preview.locator(f"[data-xp-row='drafttick'][data-xp-label='{MARK} RICE GRAIN']")).to_contain_text("deselected")
    expect(preview.locator(f"[data-xp-row='skip'][data-xp-label='{MARK} DRD EPS thickness']")).to_contain_text("no BOM template row")
    expect(preview.locator("[data-xp-row='skip']").filter(has_text=f"{MARK} SRD EPS")).to_contain_text("no Y option")
    expect(preview.locator(f"[data-xp-row='skip'][data-xp-label='{MARK} UNKNOWN THING']")).to_contain_text("not recognised")
    # Preview alone changed nothing: SRD still the door, RICE still ticked.
    expect(page.locator("input[data-draft-folder='3']")).to_be_checked()
    expect(page.locator(f"input[data-draft-flag='{MARK} RICE GRAIN']")).to_be_checked()
    expect(apply_btn).to_be_enabled()
    shot(page, "01-draft-preview", journey=JOURNEY)

    apply_btn.click()
    expect(page.locator("#modal-excel-paste")).to_be_hidden(timeout=T)

    expect(page.locator("#f-length")).to_have_value("6.5", timeout=T)
    expect(page.locator("#f-width")).to_have_value("2.5")
    expect(page.locator("#f-height")).to_have_value("2.4")

    # Door folder flipped SRD→DRD via the panel's own radio, and the chosen
    # EPS flag is selected INSIDE the newly-restored branch (the apply waited
    # for the folder handler's branch restore before clicking the flag).
    expect(page.locator("input[data-draft-folder='2']")).to_be_checked(timeout=T)
    expect(page.locator("input[data-draft-folder='3']")).not_to_be_checked()
    expect(page.locator(f"input[data-draft-flag='{MARK} DRD EPS']")).to_be_checked(timeout=T)
    expect(page.locator(f"input[data-draft-flag='{MARK} DRD PU']")).not_to_be_checked()
    # Ticks: FINN selected, RICE deselected.
    expect(page.locator(f"input[data-draft-flag='{MARK} FINN PLY FLOOR']")).to_be_checked()
    expect(page.locator(f"input[data-draft-flag='{MARK} RICE GRAIN']")).not_to_be_checked()
    shot(page, "02-draft-applied", journey=JOURNEY)


def test_both_door_sides_y_is_a_data_error(page: Page, live_server: str, staged) -> None:
    _open_paste_modal(page, live_server, staged["trailer"])
    page.locator("#excel-paste-input").fill("\n".join([
        f"{MARK} DRD EPS\t\t\tY",
        f"{MARK} SRD EPS\t\t\tY",
    ]))
    preview = page.locator("#excel-paste-preview")
    # Both derived door folders land in ONE radio group → data error; the
    # branch selections are dropped with it (no draftsel rows at all).
    expect(preview.locator("[data-xp-row='error']").filter(has_text="DRD DOORS")).to_contain_text(
        "BOTH sides of one radio group", timeout=T)
    expect(preview.locator("[data-xp-row='draftsel']")).to_have_count(0)
    expect(preview.locator("[data-xp-row='warn']")).to_have_count(0)
    shot(page, "03-both-doors-conflict", journey=JOURNEY)
