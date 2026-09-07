"""v1.53 — insulation thickness on DRAFT-rendered (masterless) bodies.

Michael's follow-up to the paste fix (7 Sep, Manni RIGIDS CB): "the insulation
thickness on the various sections not showing". Verified mechanism: on a body
with zero is_body_option masters there is NO variable_value to display or
edit — thickness sat hardcoded inside formulas (width*height*0.076*75). The
fix gives name-only flags a real thickness channel (draftFlagVars, metres)
that rides the EXISTING name-keyed body_variable_overrides into the formula
engine, with one honesty rule: the editable suffix renders exactly when some
formula on the body references {FLAG NAME} — it can never show a number the
calc ignores. Referenced-but-unset renders a LOUD orange "(set thickness)"
because the engine substitutes 0 for unknown tokens (the quiet-zero class).

Assertions ride the real /api/calculate wire (expect_response) — journeys may
not evaluate page JS (CSP), and the response's body_variables + item quantity
are the engine-level truth the suffix claims to control.

JXFV markers; purge at setup AND teardown; admin_session gets base=live_server.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "draft_flag_thickness"
MARK = "JXFV"


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


@pytest.fixture(scope="module")
def staged():
    """Masterless v2 body whose insulation row's formula references the flag
    by name — {JXFV FLOOR PU} — plus an unreferenced flag as the negative."""
    from app.database import (
        BillOfMaterial, ConfiguratorDraft, Material, SessionLocal, TrailerType,
    )
    with SessionLocal() as db:
        _purge(db)
        trailer = TrailerType(name=f"{MARK} VAR BODY", is_active=True,
                              configurator_v2=True,
                              default_length=4.0, default_width=2.0, default_height=2.0)
        m_ins = Material(name=f"{MARK} INSULATION BOARD", unit_of_measure="m3", price_per_unit=2.0)
        m_riv = Material(name=f"{MARK} RIVETS", unit_of_measure="each", price_per_unit=1.0)
        db.add_all([trailer, m_ins, m_riv])
        db.flush()
        db.add(BillOfMaterial(trailer_type_id=trailer.id, material_id=m_ins.id,
                              formula_expression=f"width*height*{{{MARK} FLOOR PU}}*75",
                              bom_section=f"{MARK} FLOOR"))
        db.add(BillOfMaterial(trailer_type_id=trailer.id, material_id=m_riv.id,
                              formula_expression="2", bom_section=f"{MARK} FLOOR"))
        draft = {
            "nextId": 4,
            "rootIds": ["1"],
            "nodes": {
                "1": {"id": "1", "type": "category", "label": f"{MARK} FLOOR",
                      "sourceCategoryKey": None, "parentId": None, "childIds": ["2", "3"]},
                "2": {"id": "2", "type": "flag", "label": f"{MARK} FLOOR PU",
                      "parentId": "1", "childIds": [], "flagMode": "tickbox",
                      "flagValue": 1, "flagBindingName": "", "flagBindingId": None},
                "3": {"id": "3", "type": "flag", "label": f"{MARK} EXTRA",
                      "parentId": "1", "childIds": [], "flagMode": "tickbox",
                      "flagValue": 0, "flagBindingName": "", "flagBindingId": None},
            },
            "itemRules": {},
        }
        db.add(ConfiguratorDraft(trailer_type_id=trailer.id, payload=json.dumps(draft)))
        db.commit()
        ids = {"trailer": trailer.id}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _open_body(page: Page, base: str, trailer_id: int) -> None:
    admin_session(page, base=base)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(trailer_id))
    expect(page.locator(f"input[data-draft-flag='{MARK} FLOOR PU']")).to_be_attached(timeout=T)


def _ins_item(result: dict) -> dict | None:
    for it in result.get("items") or []:
        if f"{MARK} INSULATION BOARD" in str(it.get("material") or it.get("material_name") or ""):
            return it
    return None


def test_suffix_lifecycle_edit_and_calc(page: Page, live_server: str, staged) -> None:
    _open_body(page, live_server, staged["trailer"])
    suffix = page.locator(f".flag-var-edit[data-flag-var='{MARK} FLOOR PU']")

    # Referenced flag → LOUD unset suffix; unreferenced flag → no suffix at all.
    expect(suffix).to_be_visible(timeout=T)
    expect(suffix).to_have_text("(set thickness)")
    expect(page.locator(f".flag-var-edit[data-flag-var='{MARK} EXTRA']")).to_have_count(0)
    shot(page, "01-set-thickness-loud", journey=JOURNEY)

    # Engine truth for the unset state: no variable sent, quantity computes 0
    # (the engine substitutes 0 for the unknown token — visibly, not silently).
    with page.expect_response("**/api/calculate") as r0:
        page.locator("#f-margin").fill("0")   # any input change → debounced recalc
    res0 = r0.value.json()
    assert f"{MARK} FLOOR PU" not in (res0.get("body_variables") or {})
    it0 = _ins_item(res0)
    assert it0 is not None and float(it0.get("quantity") or 0) == 0.0

    # Click-to-edit through the in-page prompt (never a native prompt).
    suffix.click()
    expect(page.locator("#modal-prompt")).to_be_visible(timeout=T)
    page.locator("#prompt-input").fill("0.05")
    with page.expect_response("**/api/calculate") as r1:
        page.locator("#modal-prompt button.btn-primary").click()
    expect(page.locator("#modal-prompt")).to_be_hidden(timeout=T)
    expect(page.locator(f".flag-var-edit[data-flag-var='{MARK} FLOOR PU']")).to_have_text("(0.050 m)", timeout=T)
    res1 = r1.value.json()
    assert (res1.get("body_variables") or {}).get(f"{MARK} FLOOR PU") == 0.05
    it1 = _ins_item(res1)
    # width*height*{VAR}*75 = 2*2*0.05*75
    assert it1 is not None and abs(float(it1.get("quantity") or 0) - 15.0) < 1e-6
    shot(page, "02-thickness-set-and-computing", journey=JOURNEY)

    # Persistence: a fresh page load keeps the value (cfg_user_state store).
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(staged["trailer"]))
    expect(page.locator(f".flag-var-edit[data-flag-var='{MARK} FLOOR PU']")).to_have_text("(0.050 m)", timeout=T)


def test_excel_paste_applies_wired_thickness(page: Page, live_server: str, staged) -> None:
    _open_body(page, live_server, staged["trailer"])
    page.locator("#excel-paste-btn").click()
    expect(page.locator("#modal-excel-paste")).to_be_visible(timeout=T)
    page.locator("#excel-paste-input").fill("\n".join([
        f"{MARK} FLOOR PU\t\t0.076\tY",
        f"{MARK} EXTRA\t\t0.05\tY",
    ]))
    preview = page.locator("#excel-paste-preview")
    # Wired flag: the thickness is a real planned action, not a keep-note.
    expect(preview.locator(f"[data-xp-row='draftvar'][data-xp-label='{MARK} FLOOR PU thickness']")).to_contain_text("76 mm", timeout=T)
    # Unwired flag: honest skip — the value would never reach a formula.
    expect(preview.locator(f"[data-xp-row='skip'][data-xp-label='{MARK} EXTRA thickness']")).to_contain_text("no formula on this body references it")
    shot(page, "03-paste-preview-wired-vs-unwired", journey=JOURNEY)

    with page.expect_response("**/api/calculate") as r:
        page.locator("#excel-paste-apply").click()
    expect(page.locator("#modal-excel-paste")).to_be_hidden(timeout=T)
    expect(page.locator(f".flag-var-edit[data-flag-var='{MARK} FLOOR PU']")).to_have_text("(0.076 m)", timeout=T)
    res = r.value.json()
    assert (res.get("body_variables") or {}).get(f"{MARK} FLOOR PU") == 0.076
    it = _ins_item(res)
    # 2*2*0.076*75 = 22.8
    assert it is not None and abs(float(it.get("quantity") or 0) - 22.8) < 1e-6
    shot(page, "04-paste-applied-thickness", journey=JOURNEY)
