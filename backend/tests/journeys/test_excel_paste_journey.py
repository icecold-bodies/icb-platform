"""v1.42 §3.4 — Paste body options + dims from Excel (Calculator 1 journey).

Admin opens the legacy calculator on a staged flat-panel trailer, opens the
"Paste from Excel" modal, pastes a known TSV block, and asserts the preview
classifications (dims, pair side-flip with a DISCRIMINATING pasted thickness,
door FLIP via the paste, N-deselect, both-Y error chip, door-row guard,
unknown-label skip), then Applies and asserts the calculator adopted the
settings exactly as manual clicks would.

Review-hardened coverage (adversarial sweep, 17 Jul):
- FRONT EPS pastes 0.05 — differs from the 0.06 the copy-zero carry would
  produce, so the assertion proves the Excel-authoritative thickness write ran.
- The paste flips the DOOR (fixture starts DRD; block quotes SRD) — exercising
  _xpEnsureDoor's real work and the dims→door→pairs ordering.
- RICE GRAIN starts selected and pastes N — the deselect path + '✗ deselected'
  preview row; the kick plate pastes Y after it (kick-after-floor ordering).
- A non-pair row in the DRD group ("DRD DOOR SET") must take the door-row
  guard (skipped), never the tick path.

The staged trailer is flat-panel (configurator_v2=False) — CI has no v2
configurator draft; the v2 tree path was verified live on the dev DB's
"UP TO 4.8 MT FREEZER 2" during the WO (see PR body). Selector policy: the
calculator is Jinja (no React testids) — element IDs + the paste feature's own
data-xp-row/data-xp-label preview attributes (test_costing_cutover_journey.py
precedent). J142XP markers; purge at setup AND teardown.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from _common import admin_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "excel_paste"
MARK = "J142XP"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.bill_of_materials WHERE material_id IN "
        "(SELECT id FROM icb_costings.materials WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    """Flat-panel marker trailer with EPS/PU pairs (FRONT + ROOF + DRD + SRD),
    a pre-selected floor-type checkbox, a kick plate, and a non-pair DRD-group
    fitting row. DRD PU / FRONT PU / ROOF PU start selected (body_option_default)
    so the paste demonstrably FLIPS sides and the door itself."""
    from app.database import BillOfMaterial, Material, SessionLocal, TrailerType
    with SessionLocal() as db:
        _purge(db)
        trailer = TrailerType(name=f"{MARK} PASTE TRAILER", is_active=True,
                              default_length=4.0, default_width=2.0, default_height=2.0)
        db.add(trailer)
        db.flush()

        def _mat(name):
            m = Material(name=f"{MARK} {name}", unit_of_measure="each", price_per_unit=0.0)
            db.add(m)
            db.flush()
            return m

        def _bom(mat, group, sub, default=False, var=None):
            row = BillOfMaterial(trailer_type_id=trailer.id, material_id=mat.id,
                                 is_body_option=True, body_option_group=group,
                                 body_option_subgroup=sub, body_option_default=default,
                                 variable_value=var)
            db.add(row)
            db.flush()
            return row

        ids = {"trailer": trailer.id}
        ids["front_eps"] = _bom(_mat("FRONT EPS"), "FRONT", "INSULATION", False, 0.0).id
        ids["front_pu"] = _bom(_mat("FRONT PU"), "FRONT", "INSULATION", True, 0.06).id
        ids["roof_eps"] = _bom(_mat("ROOF EPS"), "ROOF", "INSULATION", False, 0.0).id
        ids["roof_pu"] = _bom(_mat("ROOF PU"), "ROOF", "INSULATION", True, 0.076).id
        ids["drd_eps"] = _bom(_mat("DRD EPS"), "DRD", "INSULATION", False, 0.0).id
        ids["drd_pu"] = _bom(_mat("DRD PU"), "DRD", "INSULATION", True, 0.06).id
        ids["srd_eps"] = _bom(_mat("SRD EPS"), "SRD", "INSULATION", False, 0.0).id
        ids["srd_pu"] = _bom(_mat("SRD PU"), "SRD", "INSULATION", False, 0.0).id
        ids["rice"] = _bom(_mat("RICE GRAIN ALU FLOOR"), "FLOOR", None, default=True).id
        ids["kick1"] = _bom(_mat("1ST ROW ALU KICK PLATE"), "FLOOR", "KICK - 1ST ROW ALU KICK PLATE").id
        ids["drd_fitting"] = _bom(_mat("DRD DOOR SET"), "DRD", None).id
        db.commit()
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _tsv(ids) -> str:
    """The pasted block: Excel puts TSV on the clipboard — labels equal the
    material names; LENGTH/WIDTH carry the internal + external numeric pair
    (second ignored). Cases: FRONT flips PU→EPS at a 0.05 thickness the carry
    could not produce; the door flips DRD→SRD (SRD EPS = the only door Y);
    ROOF is a both-Y data error; RICE deselects; the DRD fitting row must hit
    the door-row guard; one unknown label."""
    return "\n".join([
        "LENGTH\t\t6.5\t6.55",
        "WIDTH\t\t2.5\t2.55",
        "HEIGHT\t\t2.50",
        f"{MARK} FRONT EPS\t\t0.05\tY",
        f"{MARK} FRONT PU\t\t0.06\tN",
        f"{MARK} ROOF EPS\t\t0.076\tY",
        f"{MARK} ROOF PU\t\t0.076\tY",
        f"{MARK} DRD EPS\t\t0\tN",
        f"{MARK} DRD PU\t\t0.06\tN",
        f"{MARK} SRD EPS\t\t0.06\tY",
        f"{MARK} SRD PU\t\t0\tN",
        f"{MARK} RICE GRAIN ALU FLOOR\t\t\tN",
        f"{MARK} 1ST ROW ALU KICK PLATE\t\t\tY",
        f"{MARK} DRD DOOR SET\t\t\tY",
        f"{MARK} UNKNOWN THING\t\t\tY",
    ])


def test_excel_paste_preview_and_apply(page: Page, staged) -> None:
    ids = staged
    admin_session(page)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(ids["trailer"]))
    # Flat renderer attached = the staged FRONT pair's radio exists.
    expect(page.locator(f"#body-options-list input[data-bom-id='{ids['front_eps']}']")).to_be_attached(timeout=T)
    # Fixture sanity: RICE starts selected (the paste must DESELECT it).
    expect(page.locator(f"#body-options-list input[data-bom-id='{ids['rice']}']")).to_be_checked()

    # ── Open the modal + paste ────────────────────────────────────────────────
    page.locator("#excel-paste-btn").click()
    expect(page.locator("#modal-excel-paste")).to_be_visible(timeout=T)
    apply_btn = page.locator("#excel-paste-apply")
    expect(apply_btn).to_be_disabled()
    page.locator("#excel-paste-input").fill(_tsv(ids))  # fill fires input → live preview

    # ── Preview classifications (the HARD GATE — nothing applied yet) ────────
    preview = page.locator("#excel-paste-preview")
    expect(preview.locator("[data-xp-row='dim']")).to_have_count(3, timeout=T)
    expect(preview.locator("[data-xp-row='door']")).to_contain_text("SRD · EPS 60 mm")
    expect(preview.locator("[data-xp-row='pair'][data-xp-label='FRONT insulation']")).to_contain_text("EPS 50 mm")
    expect(preview.locator("[data-xp-row='error'][data-xp-label='ROOF insulation']")).to_contain_text("both EPS and PU marked Y")
    expect(preview.locator(f"[data-xp-row='tick'][data-xp-label='{MARK} RICE GRAIN ALU FLOOR']")).to_contain_text("deselected")
    expect(preview.locator(f"[data-xp-row='skip'][data-xp-label='{MARK} DRD DOOR SET']")).to_contain_text("door-type row")
    expect(preview.locator(f"[data-xp-row='skip'][data-xp-label='{MARK} UNKNOWN THING']")).to_contain_text("not recognised")
    expect(preview.locator("[data-xp-row='skip'][data-xp-label='DRD insulation']")).to_contain_text("left unchanged")
    expect(page.locator("#excel-paste-trailer")).to_contain_text(f"{MARK} PASTE TRAILER")
    # Preview alone changed nothing: FRONT PU still the selected side.
    expect(page.locator(f"#body-options-list input[data-bom-id='{ids['front_pu']}']")).to_be_checked()
    expect(apply_btn).to_be_enabled()
    shot(page, "01-preview", journey=JOURNEY)

    # ── Apply ─────────────────────────────────────────────────────────────────
    apply_btn.click()
    expect(page.locator("#modal-excel-paste")).to_be_hidden(timeout=T)

    # Dims (first numeric column only; recalc listeners fired by real events).
    expect(page.locator("#f-length")).to_have_value("6.5", timeout=T)
    expect(page.locator("#f-width")).to_have_value("2.5")
    expect(page.locator("#f-height")).to_have_value("2.5")

    # FRONT flipped PU→EPS at the PASTED 0.05 — not the 0.06 the carry would
    # have produced — proving the Excel-authoritative thickness write ran.
    expect(page.locator(f"#body-options-list input[data-bom-id='{ids['front_eps']}']")).to_be_checked(timeout=T)
    expect(page.locator(f"#body-options-list input[data-bom-id='{ids['front_pu']}']")).not_to_be_checked()
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['front_eps']}']")).to_have_text("(0.050 m)", timeout=T)
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['front_pu']}']")).to_have_text("(0.000 m)")

    # Door FLIPPED DRD→SRD: SRD pill on, SRD EPS selected at the pasted 0.06;
    # the DRD group is now the non-quoted door (its children unrender when off).
    expect(page.locator("#body-options-list input[onchange*=\"onDrdSrdToggle('SRD'\"]")).to_be_checked(timeout=T)
    expect(page.locator("#body-options-list input[onchange*=\"onDrdSrdToggle('DRD'\"]")).not_to_be_checked()
    expect(page.locator(f"#body-options-list input[data-bom-id='{ids['srd_eps']}']")).to_be_checked(timeout=T)
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['srd_eps']}']")).to_have_text("(0.060 m)", timeout=T)

    # ROOF was the both-Y data error → EXCLUDED from Apply, PU stays selected.
    expect(page.locator(f"#body-options-list input[data-bom-id='{ids['roof_pu']}']")).to_be_checked()
    expect(page.locator(f"span.bv-edit[data-bom-id='{ids['roof_pu']}']")).to_have_text("(0.076 m)")

    # Ticks: RICE deselected (explicit N), kick plate selected (explicit Y,
    # applied after floor types so it wins any coupling).
    expect(page.locator(f"#body-options-list input[data-bom-id='{ids['rice']}']")).not_to_be_checked(timeout=T)
    expect(page.locator(f"#body-options-list input[data-bom-id='{ids['kick1']}']")).to_be_checked()
    shot(page, "02-applied", journey=JOURNEY)


def test_excel_paste_garbage_is_inert(page: Page, staged) -> None:
    # Runs after the apply test mutated the fixture trailer's template — that is
    # deliberate: this test only asserts preview inertness on unrecognised text
    # (no state assertions), so template state cannot affect it.
    ids = staged
    admin_session(page)
    page.goto("/calculator")
    expect(page.locator("#trailer-select")).to_be_visible(timeout=T)
    page.select_option("#trailer-select", str(ids["trailer"]))
    expect(page.locator(f"#body-options-list input[data-bom-id='{ids['front_eps']}']")).to_be_attached(timeout=T)

    page.locator("#excel-paste-btn").click()
    expect(page.locator("#modal-excel-paste")).to_be_visible(timeout=T)
    page.locator("#excel-paste-input").fill("lorem ipsum dolor\nnothing useful 123\n%%%%")
    preview = page.locator("#excel-paste-preview")
    expect(preview.locator("[data-xp-row='skip']")).to_have_count(3, timeout=T)
    expect(page.locator("#excel-paste-apply")).to_be_disabled()
    shot(page, "03-garbage-inert", journey=JOURNEY)
