"""v1.45/v1.46 — Validated references, end to end (marker J145VR).

Nadie's whole loop in ONE browser session, driven through the costings-page
calculator embed:

  cost a body → Approve & Save → "Mark as validated reference" sits beside
  Approve & Save with the label prompt PREFILLED "{body} {L}x{W}x{H}" → the
  paired dropdown appears under Body Type → reload and recall it: the
  manufacturing total is IDENTICAL and the quiet green tick renders → bump the
  material price permanently (Nadie's costings.price_master_edit) → the RED
  drift warning with the percentage and the categories that moved → retire →
  the dropdown entry is gone, the verdict clears, and the row survives
  soft-retired.

Plus the v1.46 density check, and two negatives: a different body type shows no
dropdown at all, and the unrelated admin "BOM Snapshots" page is untouched
(naming isolation).

WHY ONE BIG TEST: the loop is inherently stateful, and splitting it across
pytest tests gave each phase a brand-new browser profile that had to re-derive
the previous phase's state. That coupling produced two CI-only reds which
reproduced nowhere else — not on windows-latest, not locally, not at 6x CPU
throttling. A user reloads a page; they do not get a fresh profile.

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


def _stay_on_calculator_after_save(page) -> None:
    """v1.49 — after a save, /costings/new shows a 5s countdown to the costings
    board (the new row highlighted). Flows that keep working the SAVED costing on
    this page — export, validated references — click "Stay here", exactly as a
    user doing that work would. No-op if the banner never appears (the save was
    refused, or a no-customer modal is up and the save has not happened yet)."""
    try:
        page.locator("[data-testid='saved-stay']").click(timeout=8_000)
    except Exception:
        pass


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
                                 attempts: int = 4, expect_length: str = "7.5") -> None:
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

    A re-select is ALSO how the body's default dimensions get applied. loadBOM
    only writes them once `trailerDefaults` (fetched from /api/trailers at
    DOMContentLoaded) has resolved; pick a body before that request lands — easy
    on a slow runner — and the inputs keep the template's own 13.6 x 2.5 x 2.7,
    so the costing and the label prefilled from it are built on the wrong dims.
    Selecting again after the fetch lands fixes it, so both conditions are
    checked inside the one bounded loop. Reproduced locally with
    MES_JOURNEY_CPU_THROTTLE=6.
    """
    row = frame.locator("[data-material-id]").first
    length = frame.locator("#f-length")
    last = ""
    for _ in range(attempts):
        frame.locator("#trailer-select").select_option(trailer_id)
        try:
            expect(row).to_be_attached(timeout=8_000)
            expect(length).to_have_value(expect_length, timeout=6_000)
            return
        except AssertionError:
            last = length.input_value()
            continue
    shot(page, "zz-body-never-settled", journey=JOURNEY)
    raise AssertionError(
        f"body did not settle after {attempts} selects "
        f"(rows attached={row.count()}, length={last!r}, wanted {expect_length!r})")


def _wait_calc_idle(page: Page, frame, quiet_ms: int = 1_500,
                    timeout_s: int = 60) -> None:
    """Block until a calculation has COMPLETED with the values now on screen.

    `expect(#approve-btn).to_be_enabled()` on its own is a LEVEL check and is
    not enough: loadBOM and every dimension edit go through `scheduleCalc()`'s
    700 ms debounce, and `runCalc()` disables the button synchronously only
    once that timer fires. In the gap the button is still enabled from the
    PREVIOUS calc, so the assertion passes on a stale state — the same trap as
    the banked "`is-active` passes on a stale process" note.

    That gap is what made this journey red on ubuntu-latest. When
    `/api/trailers` lands after the first select, the body's defaults are not
    applied yet, so the first calc runs on the template's 13.6 x 2.5 x 2.7. The
    retry select then writes 7.5 x 2.5 x 2.6 into the inputs and schedules a
    fresh calc — but the helper returned the moment the INPUT read 7.5, and
    approve fired inside the debounce. The record was therefore saved with
    13.6 while the screen showed 7.5, and v1.46.3's dims guard (dims are
    reference IDENTITY) correctly refused to mark it and opened the Save-first
    CONFIRM dialog. `#modal-prompt` never appeared — the CI symptom.

    So: wait for the button to stay enabled across a window LONGER than the
    debounce. If a calc was pending, the timer fires inside the window and the
    button goes disabled; if one was in flight it is still disabled at the end
    of the window. Either way we loop. Only a genuinely idle calculator stays
    enabled for the whole window, and any calc that ran inside it used the
    settled values.

    Reproduced and verified by driving the same end-state directly: approve
    inside the debounce → saved 13.6 vs screen 7.5 → "SAVE FIRST" confirm and
    no prompt; with this wait → saved 7.5 and the prompt prefilled correctly.
    """
    import time
    approve = frame.locator("#approve-btn")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        expect(approve).to_be_enabled(timeout=30_000)
        page.wait_for_timeout(quiet_ms)
        if approve.is_enabled():
            return
    raise AssertionError(
        f"the calculator never went idle within {timeout_s}s "
        "(#approve-btn kept flipping back to disabled)")


def _open_embed(page: Page, live_server: str, trailer_id: str):
    """Nadie's surface: /mes-app/costings/new with the calculator embed."""
    role_session(page, FULL_USER, base=live_server)
    page.goto("/mes-app/costings/new")
    frame = page.frame_locator(_EMBED)
    expect(frame.locator("#trailer-select")).to_be_visible(timeout=30_000)
    _select_trailer_and_wait_bom(page, frame, trailer_id)
    # NOT just `to_be_enabled()` — see _wait_calc_idle for why that passes on
    # the previous calc's result and what it cost.
    _wait_calc_idle(page, frame)
    return frame


def _why_no_prompt(page: Page, frame) -> str:
    """Explain a missing label prompt after clicking "Mark as validated reference".

    markAsValidatedReference() has three exits that produce no prompt, and they
    look identical through `#modal-prompt` alone:
      * the Save-first CONFIRM — the bound record is unsaved, points at another
        body type, or its dims differ from the screen (v1.46.1 / v1.46.3);
      * a toast — no computed result, or the mark POST failed;
      * nothing at all — the caps call said can_manage is false.
    """
    shot(page, "zz-mark-produced-no-prompt", journey=JOURNEY)
    bits = ["clicking #vref-mark-btn did not open the label prompt."]
    if frame.locator("#modal-confirm:not(.hidden)").count():
        title = (frame.locator("#confirm-title").inner_text() or "").strip()
        body = (frame.locator("#confirm-message").inner_text() or "").strip()
        bits.append(
            f"The {title!r} CONFIRM opened instead: {body!r} — the costing the "
            "mark would bind to is not the one on screen. Usual cause: approve "
            "ran before a calculation had completed with the settled "
            "dimensions, so the record holds the previous calc's dims "
            "(see _wait_calc_idle)."
        )
        bits.append(f"Screen dims now: "
                    f"{frame.locator('#f-length').input_value()}x"
                    f"{frame.locator('#f-width').input_value()}x"
                    f"{frame.locator('#f-height').input_value()}")
    toasts = frame.locator("#toast-container .toast-msg")
    if toasts.count():
        seen = [(toasts.nth(i).inner_text() or "").strip() for i in range(toasts.count())]
        bits.append(f"Toasts on screen: {seen}")
    if not frame.locator("#vref-mark-btn").is_visible():
        bits.append("#vref-mark-btn is no longer visible — the caps call "
                    "(GET /api/validated-references/settings) reported "
                    "can_manage=false.")
    return " ".join(bits)


def _reference_row(trailer_id: int):
    from app.database import SessionLocal, ValidatedReference
    with SessionLocal() as db:
        return (db.query(ValidatedReference)
                  .filter_by(trailer_type_id=trailer_id, active=True).first())


def _verdict(page: Page, frame, expect_state: str, timeout_s: int = 40) -> str:
    """Wait for the drift banner to settle, then assert WHICH state it reached.

    `expect_state` is 'tick', 'warning' or 'none'. On failure this raises with
    the banner's ACTUAL text. The previous `expect(tick).to_be_visible()` form
    failed with only "element(s) not found", which could not distinguish "no
    match", "verdict flipped to a warning" and "the call never landed" — two
    CI-only reds were spent on that ambiguity.
    """
    banner = frame.locator("#vref-banner")
    text, actual = "", "none"
    for _ in range(timeout_s):
        text = (banner.inner_text() or "").strip()
        actual = ("tick" if frame.locator("[data-testid='vref-tick']").count()
                  else "warning" if frame.locator("[data-testid='vref-warning']").count()
                  else "none")
        # Poll on the STATE, not merely on "is there any text". The banner keeps
        # its previous verdict on screen while the next recompute + match are in
        # flight, so a "has text?" check hands back the stale one — which is
        # exactly how this helper first failed, reading the pre-bump tick.
        if actual == expect_state:
            return text
        page.wait_for_timeout(1_000)
    raise AssertionError(
        f"expected the {expect_state} verdict within {timeout_s}s, got {actual}. "
        f"Banner said: {text!r}")


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


# ── 1. Nadie's whole loop, in ONE browser session ────────────────────────────
# mark → reload → recall (green tick) → price bump (red warning) → retire.
# Deliberately one test: each phase depends on the previous phase's state, and
# splitting them across pytest tests gave every phase a brand-new browser
# profile that had to re-derive it. That coupling produced two CI-only reds
# that reproduced nowhere else (not on Windows, not locally, not even at 6x CPU
# throttling). One session is also exactly how Nadie works.
def test_mark_recall_drift_and_retire(page: Page, live_server: str,
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
    _stay_on_calculator_after_save(page)   # v1.49 - this flow keeps working the saved costing here
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
    try:
        expect(prompt).to_be_visible(timeout=T)
    except AssertionError:
        # "#modal-prompt never became visible" has three quite different causes
        # and the bare locator timeout cannot tell them apart — one CI-only red
        # was spent on exactly that ambiguity. Name the branch instead.
        raise AssertionError(_why_no_prompt(page, frame)) from None
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

    # v1.49 — recalling one right here, with NO reload, must hand the save button
    # back. The costing was saved a moment ago, so the save-once gate is on; a
    # recall is a fresh COPY, which lifts it. The reload below would mask a gate
    # that stayed stuck in-session, so assert it on this side of the reload.
    expect(frame.locator("#approve-btn")).to_be_disabled()
    frame.locator("#vref-select").select_option(index=1)
    expect(frame.locator("#vref-recalled-note")).to_be_visible(timeout=T)
    expect(frame.locator("#approve-btn")).to_be_enabled(timeout=30_000)

    # ── recall: reload the page, pick the reference, expect the green tick ────
    # Same browser context on purpose. Splitting this across pytest tests meant
    # each step started from a BRAND-NEW browser profile and had to re-derive
    # the previous step's state; that cost two CI-only reds. A user reloads a
    # page, they do not get a fresh profile — this models what Nadie does and
    # removes the cross-test coupling entirely. (That a reference marked WITH
    # extras still matches a genuinely fresh browser is pinned by the unit test
    # test_a_fresh_browser_matches_a_reference_marked_with_extras, which is a
    # far tighter place to assert it than a browser journey.)
    page.goto("/mes-app/costings/new")
    frame = page.frame_locator(_EMBED)
    expect(frame.locator("#trailer-select")).to_be_visible(timeout=30_000)
    _select_trailer_and_wait_bom(page, frame, str(ids["trailer"]))
    expect(frame.locator("#approve-btn")).to_be_enabled(timeout=30_000)

    expect(frame.locator("#vref-picker-label")).to_have_text(
        "Validated references (1)", timeout=T)
    baseline = frame.locator("#grand-total").inner_text()

    frame.locator("#vref-select").select_option(index=1)
    expect(frame.locator("#toast-container .toast-msg",
                         has_text="Loaded from validated reference").first
           ).to_be_visible(timeout=30_000)
    expect(frame.locator("#vref-recalled-note")).to_contain_text(
        f"{MARK} balanced baseline", timeout=T)

    # Totals reproduce EXACTLY, and the quiet green tick confirms the match.
    expect(frame.locator("#grand-total")).to_have_text(baseline, timeout=30_000)
    tick = _verdict(page, frame, "tick")
    assert f"{MARK} balanced baseline" in tick, tick
    shot(page, "04-recalled-green-tick", journey=JOURNEY)

    # COPY semantics: recall must never bind to the reference's own record, so
    # no edit chrome appears and the reference costing is left alone.
    expect(frame.locator("#edit-mode-banner")).to_be_hidden()

    # ── drift: a permanent price bump past tolerance turns the tick red ───────
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

    warning = _verdict(page, frame, "warning")
    for fragment in (f"{MARK} balanced baseline", "+20.0%", "Categories moved", "PANELS"):
        assert fragment in warning, f"{fragment!r} missing from: {warning!r}"
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

    # Gone from the dropdown, and no verdict survives.
    expect(frame.locator("#vref-picker-wrap")).to_be_hidden(timeout=T)
    _verdict(page, frame, "none")
    shot(page, "07-retired-no-dropdown", journey=JOURNEY)

    # SOFT retire — the row survives for the record.
    from app.database import SessionLocal, ValidatedReference
    with SessionLocal() as db:
        rows = (db.query(ValidatedReference)
                  .filter_by(trailer_type_id=ids["trailer"]).all())
    assert len(rows) == 1 and rows[0].active is False


# ── 2. The v1.46.1 defect: a mark must bind to the costing ON SCREEN ─────────
def test_switching_body_type_after_saving_does_not_mis_attach_a_reference(
        page: Page, live_server: str, staged) -> None:
    """Found on :8000. Save a costing, then pick a DIFFERENT body type without
    saving: "Mark as validated reference" still bound to the previous costing,
    so the reference was written against the wrong body — and its dropdown
    therefore never appeared under the body the user was looking at. The real
    row read `label='FREEZER MEDIUM 5.6x2.5x2.4'` on `trailer_type_id=CHILLER
    LARGE`.

    The mark must now refuse and offer the save flow instead.
    """
    ref_body, other_body = staged["ref"], staged["other"]

    def _ref_count() -> int:
        from app.database import SessionLocal, ValidatedReference
        with SessionLocal() as db:
            return db.query(ValidatedReference).filter(
                ValidatedReference.trailer_type_id.in_(
                    [ref_body["trailer"], other_body["trailer"]])).count()

    # The earlier test leaves one SOFT-RETIRED row behind, so compare a delta
    # rather than asserting zero.
    before = _ref_count()
    frame = _open_embed(page, live_server, str(ref_body["trailer"]))

    # Save a costing on the FIRST body.
    frame.locator("#approve-btn").click()
    _stay_on_calculator_after_save(page)   # v1.49 - this flow keeps working the saved costing here
    try:
        expect(frame.locator("#modal-no-customer")).to_be_visible(timeout=4_000)
        frame.locator("#modal-no-customer .btn-outline").click()
    except AssertionError:
        pass
    expect(frame.locator("#toast-container .toast-msg",
                         has_text="Costing approved").first).to_be_visible(timeout=T)

    # Now switch to a DIFFERENT body type, without saving it.
    _select_trailer_and_wait_bom(page, frame, str(other_body["trailer"]))
    expect(frame.locator("#approve-btn")).to_be_enabled(timeout=T)

    # Marking must NOT silently reuse the previous costing: it offers the save
    # flow (the "Save first" confirm), not the label prompt.
    frame.locator("#vref-mark-btn").click()
    expect(frame.locator("#modal-confirm")).to_be_visible(timeout=T)
    expect(frame.locator("#confirm-title")).to_have_text("Save first")
    expect(frame.locator("#modal-prompt")).to_be_hidden()
    frame.locator("#confirm-cancel").click()

    # …and nothing new was written against either body type.
    assert _ref_count() == before, \
        "a reference was written despite the body type having changed"

    # ── the SAME hazard through the ?edit= path ───────────────────────────────
    # Opening a costing for editing binds it just as firmly, and that binding
    # ALSO survives a body-type switch. The first cut of this fix guarded only
    # the saved-costing path and left this one open — the deploy check on :8000
    # caught it, so it is pinned here too.
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        pending = (db.query(CalculationRecord)
                     .filter_by(trailer_type_id=ref_body["trailer"], status="pending")
                     .order_by(CalculationRecord.id.desc()).first())
    if pending is not None:
        page.goto(f"/calculator?edit={pending.id}")
        expect(page.locator("#approve-btn")).to_be_enabled(timeout=60_000)
        _select_trailer_and_wait_bom(page, page, str(other_body["trailer"]))
        expect(page.locator("#approve-btn")).to_be_enabled(timeout=60_000)
        page.locator("#vref-mark-btn").click()
        expect(page.locator("#modal-confirm")).to_be_visible(timeout=T)
        expect(page.locator("#confirm-title")).to_have_text("Save first")
        expect(page.locator("#modal-prompt")).to_be_hidden()
        page.locator("#confirm-cancel").click()
        assert _ref_count() == before, \
            "an edit binding mis-attached a reference after a body-type switch"

    # ── v1.46.3: changed DIMS are the same hazard as a changed body type ──────
    # Dims feed the fingerprint, so "saved at 5.3, typed 5.6, marked" labels one
    # configuration while pointing at another (Michael's mislabelled row:
    # 'FREEZER MEDIUM 5.6x2.5x2.4' on a 5.3 record). Marking with screen dims
    # differing from the bound record must fall into the Save-first flow.
    if pending is not None:
        page.goto(f"/calculator?edit={pending.id}")
        expect(page.locator("#approve-btn")).to_be_enabled(timeout=60_000)
        page.locator("#f-length").fill("9.9")
        page.wait_for_timeout(3_000)                 # debounce + recompute
        expect(page.locator("#approve-btn")).to_be_enabled(timeout=60_000)
        page.locator("#vref-mark-btn").click()
        expect(page.locator("#modal-confirm")).to_be_visible(timeout=T)
        expect(page.locator("#confirm-title")).to_have_text("Save first")
        expect(page.locator("#modal-prompt")).to_be_hidden()
        page.locator("#confirm-cancel").click()
        assert _ref_count() == before, \
            "a reference was written although the screen dims differ from the record"


# ── 3. Negative: a body type with no references shows no dropdown ────────────
def test_a_body_type_without_references_shows_no_dropdown(
        page: Page, live_server: str, staged) -> None:
    frame = _open_embed(page, live_server, str(staged["other"]["trailer"]))
    expect(frame.locator("#vref-picker-wrap")).to_be_hidden(timeout=T)
    _verdict(page, frame, "none")


# ── 4. Naming isolation: the unrelated BOM Snapshots page is untouched ───────
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


# ── 5. The Save-first dialog names WHY it fired ──────────────────────────────
def test_save_first_dialog_names_the_dimension_change(
        page: Page, live_server: str, staged) -> None:
    """Michael's case: saved at one size, typed another, then pressed Mark.

    v1.46.3 correctly refuses — dimensions are part of a reference's IDENTITY,
    so marking would label one costing while pointing at another. But the
    dialog said only "a validated reference has to point at a saved costing",
    which is not the reason here and reads as a bug when the costing plainly
    HAS been saved. The refusal has to name the dimension change.

    Deterministic by construction: the guard compares the boxes against the
    BOUND RECORD, so typing a new length after the save is enough — no
    recompute has to land first.
    """
    ids = staged["other"]                 # the never-referenced control body
    frame = _open_embed(page, live_server, str(ids["trailer"]))

    frame.locator("#approve-btn").click()

    _stay_on_calculator_after_save(page)   # v1.49 - this flow keeps working the saved costing here
    try:
        expect(frame.locator("#modal-no-customer")).to_be_visible(timeout=4_000)
        frame.locator("#modal-no-customer .btn-outline").click()
    except AssertionError:
        pass
    expect(frame.locator("#toast-container .toast-msg",
                         has_text="Costing approved").first).to_be_visible(timeout=T)

    # Saved at 7.5; now the boxes say 5.6 — exactly Michael's sequence.
    frame.locator("#f-length").fill("5.6")
    frame.locator("#vref-mark-btn").click()

    confirm = frame.locator("#modal-confirm")
    expect(confirm).to_be_visible(timeout=T)
    expect(frame.locator("#confirm-title")).to_have_text("Save first", timeout=T)
    msg = frame.locator("#confirm-message").inner_text()
    assert "7.5" in msg and "5.6" in msg, \
        f"the dialog does not name the sizes it is refusing over: {msg!r}"
    assert "identity" in msg.lower(), \
        f"the dialog does not say WHY the dimensions matter: {msg!r}"
    shot(page, "09-save-first-names-the-dims", journey=JOURNEY)

    # It is still the Save-first flow: cancelling marks nothing.
    frame.locator("#confirm-cancel").click()
    expect(confirm).to_be_hidden(timeout=T)
    assert _reference_row(ids["trailer"]) is None, \
        "a reference was created despite the Save-first refusal"
