"""v1.45 §3.4 — Validated references, end to end (marker J145VR).

Nadie's whole loop, driven through the costings-page calculator embed:

1. Cost a body → Approve & Save → "Mark as validated reference" sits beside
   Approve & Save, the label prompt is PREFILLED with "{body} {L}x{W}x{H}", and
   marking it makes the paired dropdown appear under Body Type.
2. A FRESH calculator on the same body type shows "Validated references (1)";
   recalling it reproduces the configuration — the manufacturing total is
   IDENTICAL and the quiet green tick renders.
3. Bump the material price permanently (Nadie's costings.price_master_edit) →
   recompute → the RED drift warning with the percentage and the categories
   that moved → retire the reference → the dropdown entry is gone, the warning
   clears, and the row survives as a soft-retired record.

Plus the two negatives: a different body type shows no dropdown at all, and the
unrelated admin "BOM Snapshots" page is untouched (naming isolation).

Selector policy: Jinja pages by element ID; React by data-testid. No
wait_for_function (CSP has no unsafe-eval).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from _common import role_session, shot  # noqa: E402  (sys.path set in conftest)

T = 15_000
JOURNEY = "validated_references"
MARK = "J145VR"
FULL_USER = "journey_full_vref"     # role 'full' = Nadie: has BOTH new keys

_EMBED = "iframe[title='Calculator (live costing app)']"


def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text(
        "DELETE FROM icb_costings.validated_references WHERE trailer_type_id IN "
        "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text(
        "DELETE FROM icb_costings.bom_override_history WHERE bom_id IN "
        "(SELECT id FROM icb_costings.bill_of_materials WHERE material_id IN "
        " (SELECT id FROM icb_costings.materials WHERE name LIKE :m))"), {"m": f"{MARK}%"})
    db.execute(text(
        "DELETE FROM icb_costings.calculations WHERE trailer_type_id IN "
        "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text(
        "DELETE FROM icb_costings.bill_of_materials WHERE material_id IN "
        "(SELECT id FROM icb_costings.materials WHERE name LIKE :m)"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def staged():
    """Two calculable marker bodies (one is the never-referenced control) with a
    single flat BOM row each, plus Nadie's role-'full' journey user."""
    from app.database import (BillOfMaterial, Material, SessionLocal,
                              TrailerType, User)
    created_user = False
    with SessionLocal() as db:
        _purge(db)

        def body(suffix, price):
            tt = TrailerType(name=f"{MARK} {suffix}", is_active=True,
                             default_length=7.5, default_width=2.5, default_height=2.6)
            db.add(tt)
            db.flush()
            mat = Material(name=f"{MARK} {suffix} PANEL", unit_of_measure="m2",
                           price_per_unit=price)
            db.add(mat)
            db.flush()
            bom = BillOfMaterial(trailer_type_id=tt.id, material_id=mat.id,
                                 formula_expression="1", waste_percentage=0,
                                 bom_section="PANELS", sort_order=1)
            db.add(bom)
            db.flush()
            return {"trailer": tt.id, "name": tt.name, "bom": bom.id}

        ids = {"ref": body("CHILLER", 1000.0), "other": body("FREEZER", 800.0)}
        if db.query(User).filter_by(username=FULL_USER).first() is None:
            db.add(User(username=FULL_USER, password_hash="x", role="full"))
            created_user = True
        db.commit()

    yield ids

    with SessionLocal() as db:
        _purge(db)
        if created_user:
            u = db.query(User).filter_by(username=FULL_USER).first()
            if u is not None:
                db.delete(u)
        db.commit()


def _select_trailer_and_wait_bom(page: Page, frame, trailer_id: str,
                                 attempts: int = 4) -> None:
    """select_option is one-shot: while the embed is still settling the
    change→loadBOM→fetch chain can be lost and no BOM row ever renders (banked
    embed-journey flake class). Re-select, bounded.

    Waits for ATTACHED, not visible. Once the first calc lands, the post-calc
    table regroups by category and remembers a COLLAPSED state, so a rendered
    row is routinely present-but-hidden — waiting on visibility made the retry
    loop fire spurious re-selects on a slow runner, each one restarting
    loadBOM + a fresh calc. That storm is what made the drift banner
    non-deterministic on ubuntu-latest. Attachment alone proves loadBOM
    rendered; the approve-btn wait in _open_embed proves a calc completed.
    """
    row = frame.locator("[data-material-id]").first
    for _ in range(attempts):
        frame.locator("#trailer-select").select_option(trailer_id)
        try:
            expect(row).to_be_attached(timeout=8_000)
            return
        except AssertionError:
            continue
    shot(page, "zz-bom-never-rendered", journey=JOURNEY)
    raise AssertionError(f"BOM rows never rendered after {attempts} selects")


def _open_embed(page: Page, live_server: str, trailer_id: str):
    """Nadie's surface: /mes-app/costings/new with the calculator embed."""
    role_session(page, FULL_USER, base=live_server)
    page.goto("/mes-app/costings/new")
    frame = page.frame_locator(_EMBED)
    expect(frame.locator("#trailer-select")).to_be_visible(timeout=30_000)
    _select_trailer_and_wait_bom(page, frame, trailer_id)
    expect(frame.locator("#approve-btn")).to_be_enabled(timeout=30_000)
    return frame


def _reference_row(trailer_id: int):
    from app.database import SessionLocal, ValidatedReference
    with SessionLocal() as db:
        return (db.query(ValidatedReference)
                  .filter_by(trailer_type_id=trailer_id, active=True).first())


# ── 0. v1.46 density: captions left, controls right, no dead buttons ─────────
def test_parameter_panel_is_compact_and_footer_is_trimmed(
        page: Page, live_server: str, staged) -> None:
    """Michael, 11 Aug 2026: the parameters block and the summary footer were
    eating the panel and squashing the category totals. Captions now sit LEFT of
    their control on one line, and Print / Full Report / the Selling Price line
    are gone. Asserted on GEOMETRY, not pixel counts — a font change must not
    fail this, but a regression to the stacked layout must."""
    ids = staged["ref"]
    frame = _open_embed(page, live_server, str(ids["trailer"]))

    for field in ("f-length", "f-width", "f-height", "f-margin", "f-ratio"):
        label = frame.locator(f"#btp-body label[for='{field}']").bounding_box()
        control = frame.locator(f"#{field}").bounding_box()
        assert label and control, field
        # same row (baselines within a line-height) and the control to the RIGHT
        assert abs(label["y"] - control["y"]) < 14, f"{field}: caption is not on the control's row"
        assert control["x"] > label["x"], f"{field}: control is not right of its caption"

    # The three things Michael asked to reclaim.
    expect(frame.locator("#print-btn")).to_have_count(0)
    expect(frame.locator("#view-btn")).to_have_count(0)
    assert "Selling Price" not in frame.locator(".panel-footer").last.inner_text()

    # Total Cost caption and amount share one line.
    cap = frame.locator(".grand-total-inline .grand-total-label").bounding_box()
    amt = frame.locator(".grand-total-inline .grand-total-amount").bounding_box()
    assert abs(cap["y"] - amt["y"]) < 20 and amt["x"] > cap["x"], \
        "Total Cost caption and amount are not on one line"
    shot(page, "00-compact-parameters", journey=JOURNEY)


# ── 1. Mark: the action sits beside Approve & Save, prefilled label ───────────
def test_cost_save_and_mark_as_validated_reference(page: Page, live_server: str,
                                                   staged) -> None:
    ids = staged["ref"]
    frame = _open_embed(page, live_server, str(ids["trailer"]))

    # The mark action is visible (role 'full' HAS costings.validated_refs_manage)
    # and enabled only because a computed result exists.
    mark = frame.locator("#vref-mark-btn")
    expect(mark).to_be_visible(timeout=T)
    expect(mark).to_be_enabled(timeout=T)
    shot(page, "01-mark-action-beside-approve", journey=JOURNEY)

    # Approve & Save first — a reference must point at a SAVED costing.
    frame.locator("#approve-btn").click()
    no_cust = frame.locator("#modal-no-customer")
    try:
        expect(no_cust).to_be_visible(timeout=4_000)
        frame.locator("#modal-no-customer .btn-outline").click()
    except AssertionError:
        pass    # a customer was already attached — nothing to dismiss
    expect(frame.locator("#toast-container .toast-msg",
                         has_text="Costing approved").first).to_be_visible(timeout=T)

    mark.click()
    prompt = frame.locator("#modal-prompt")
    expect(prompt).to_be_visible(timeout=T)
    # Prefilled "{body type} {L}x{W}x{H}".
    expect(frame.locator("#prompt-input")).to_have_value(
        f"{ids['name']} 7.5x2.5x2.6", timeout=T)
    shot(page, "02-label-prompt-prefilled", journey=JOURNEY)
    frame.locator("#prompt-input").fill(f"{MARK} balanced baseline")
    frame.locator("#modal-prompt button.btn-primary").click()

    expect(frame.locator("#toast-container .toast-msg",
                         has_text="Marked as validated reference").first
           ).to_be_visible(timeout=T)

    # The paired dropdown appears under Body Type, labelled with the count.
    expect(frame.locator("#vref-picker-wrap")).to_be_visible(timeout=T)
    expect(frame.locator("#vref-picker-label")).to_have_text(
        "Validated references (1)", timeout=T)
    shot(page, "03-references-dropdown-appears", journey=JOURNEY)

    ref = _reference_row(ids["trailer"])
    assert ref is not None, "no validated_references row was written"
    assert ref.label == f"{MARK} balanced baseline"
    assert ref.active is True
    assert len(ref.config_fingerprint) == 64
    # A POINTER, never a copy: it names a saved costing on this body type.
    assert ref.calculation_id and ref.trailer_type_id == ids["trailer"]


# ── 2. Recall: fresh calculator → dropdown → identical totals + green tick ────
def test_recall_reproduces_the_configuration_with_a_green_tick(
        page: Page, live_server: str, staged) -> None:
    ids = staged["ref"]
    frame = _open_embed(page, live_server, str(ids["trailer"]))

    expect(frame.locator("#vref-picker-label")).to_have_text(
        "Validated references (1)", timeout=T)
    baseline = frame.locator("#grand-total").inner_text()

    frame.locator("#vref-select").select_option(label=None, index=1)
    expect(frame.locator("#toast-container .toast-msg",
                         has_text="Loaded from validated reference").first
           ).to_be_visible(timeout=30_000)
    expect(frame.locator("#vref-recalled-note")).to_contain_text(
        f"{MARK} balanced baseline", timeout=T)

    # Totals reproduce EXACTLY, and the quiet green tick confirms the match.
    expect(frame.locator("#grand-total")).to_have_text(baseline, timeout=30_000)
    expect(frame.locator("[data-testid='vref-tick']")).to_be_visible(timeout=30_000)
    expect(frame.locator("[data-testid='vref-tick']")).to_contain_text(
        f"{MARK} balanced baseline")
    expect(frame.locator("[data-testid='vref-warning']")).to_have_count(0)
    shot(page, "04-recalled-green-tick", journey=JOURNEY)

    # COPY semantics: recall must never bind to the reference's own record, so
    # no edit chrome appears and the reference costing is left alone.
    expect(frame.locator("#edit-mode-banner")).to_be_hidden()


# ── 3. Drift, then retire — ONE continuous flow ──────────────────────────────
# Deliberately not split across two page loads. Nadie's actual sequence is
# "bump a price, see the warning, retire the reference" without leaving the
# page, and the split version made the second half depend on a warning being
# re-derived on a fresh load — timing-sensitive enough to go red on the slower
# CI runner while passing everywhere else. Fresh-load re-derivation is already
# proven by step 2 (a reload recomputes and paints the green tick from
# persisted state); nothing is given up by keeping this one continuous.
def test_price_bump_warns_then_retiring_clears_it(
        page: Page, live_server: str, staged) -> None:
    ids = staged["ref"]
    frame = _open_embed(page, live_server, str(ids["trailer"]))
    expect(frame.locator("[data-testid='vref-tick']")).to_be_visible(timeout=30_000)

    # Nadie's permanent BOM price save (costings.price_master_edit): 1000 → 1200
    # is +20%, an order of magnitude past the 2% tolerance.
    # The POST-calc table groups by category and remembers a collapsed state in
    # localStorage, so the row can be present-but-hidden — expand first.
    row = frame.locator("[data-material-id]").first
    if not row.is_visible():
        frame.locator(".calc-grp-hdr").first.click()
    expect(row).to_be_visible(timeout=T)
    row.click(button="right")
    frame.locator(".ctx-menu-item", has_text="Edit permanently (this section)").click()
    expect(frame.locator("#modal-section-price")).to_be_visible(timeout=T)
    frame.locator("#sprice-input").fill("1200")
    frame.locator("#sprice-save-btn").click()
    expect(frame.locator("#toast-container .toast-msg",
                         has_text="Section price saved").first).to_be_visible(timeout=T)

    warning = frame.locator("[data-testid='vref-warning']")
    expect(warning).to_be_visible(timeout=30_000)
    expect(warning).to_contain_text(f"{MARK} balanced baseline")
    expect(warning).to_contain_text("+20.0%")
    expect(warning).to_contain_text("Categories moved")
    expect(warning).to_contain_text("PANELS")
    expect(frame.locator("[data-testid='vref-tick']")).to_have_count(0)
    shot(page, "05-red-drift-warning", journey=JOURNEY)

    # ── retire, in the same page ──────────────────────────────────────────────
    frame.locator("#vref-manage-link").click()
    expect(frame.locator("#modal-validated-refs")).to_be_visible(timeout=T)
    shot(page, "06-manage-list", journey=JOURNEY)

    ref = _reference_row(ids["trailer"])
    assert ref is not None
    frame.locator(f"[data-testid='vref-retire-{ref.id}']").click()
    expect(frame.locator("#modal-confirm")).to_be_visible(timeout=T)
    frame.locator("#confirm-ok").click()
    expect(frame.locator("#toast-container .toast-msg",
                         has_text="Validated reference retired").first
           ).to_be_visible(timeout=T)
    frame.locator("#modal-validated-refs .modal-footer .btn").click()

    # Gone from the dropdown, and no warning survives.
    expect(frame.locator("#vref-picker-wrap")).to_be_hidden(timeout=T)
    expect(frame.locator("[data-testid='vref-warning']")).to_have_count(0)
    expect(frame.locator("[data-testid='vref-tick']")).to_have_count(0)
    shot(page, "07-retired-no-dropdown", journey=JOURNEY)

    # SOFT retire — the row survives for the record.
    from app.database import SessionLocal, ValidatedReference
    with SessionLocal() as db:
        rows = (db.query(ValidatedReference)
                  .filter_by(trailer_type_id=ids["trailer"]).all())
    assert len(rows) == 1 and rows[0].active is False


# ── 4. Negative: a body type with no references shows no dropdown ────────────
def test_a_body_type_without_references_shows_no_dropdown(
        page: Page, live_server: str, staged) -> None:
    frame = _open_embed(page, live_server, str(staged["other"]["trailer"]))
    expect(frame.locator("#vref-picker-wrap")).to_be_hidden(timeout=T)
    expect(frame.locator("[data-testid='vref-tick']")).to_have_count(0)
    expect(frame.locator("[data-testid='vref-warning']")).to_have_count(0)


# ── 5. Naming isolation: the unrelated BOM Snapshots page is untouched ───────
def test_bom_snapshots_admin_page_is_unchanged(page: Page, live_server: str,
                                               staged) -> None:
    """"BOM Snapshots" is a pre-existing, unrelated ADMIN feature (template-level).
    This lane must not have leaked its wording, routes or data into it."""
    from _common import admin_session
    admin_session(page, base=live_server)
    resp = page.goto("/admin/bom-snapshots")
    assert resp is not None and resp.status == 200, "BOM Snapshots page changed"
    text = page.locator("body").inner_text()
    assert "Snapshot" in text, "the BOM Snapshots page did not render"
    assert "Validated reference" not in text, "validated-reference wording leaked"
    assert MARK not in text, "this lane's data leaked into BOM Snapshots"
    shot(page, "08-bom-snapshots-untouched", journey=JOURNEY)

    # And nothing here wrote a BOM Snapshot row.
    from app.database import BomSnapshot, SessionLocal
    with SessionLocal() as db:
        assert db.query(BomSnapshot).filter_by(
            trailer_type_id=staged["ref"]["trailer"]).count() == 0
