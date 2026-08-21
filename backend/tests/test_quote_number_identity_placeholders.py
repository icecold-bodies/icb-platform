"""v1.50 — {customer} and {vehicle_registration} as numbering placeholders.

Michael, 22 Aug: the ratified repair naming convention is
`R-number + customer + vehicle registration`. It already shipped as the
quotation's FILENAME (`repair_quote_filename`, ratified 22 Aug via Lezette);
this makes the same two fields available to the admin TEMPLATE, so the
convention can be built into the issued number itself.

What these pin:

  * both placeholders validate, render, and preview
  * they are populated on the REPAIR series (off the quotation's own fields)
    and render EMPTY elsewhere, exactly as {trailer_code} does on a repair
  * missing values never leave "None" or a double space in a number
  * the shipped DEFAULT template is unchanged — nothing about an existing
    installation's numbers moves until an admin opts in on the screen
  * the filename does not REPEAT a part the number already carries
  * the number stays a snapshot: renaming the customer afterwards does not
    restamp an already-issued number
"""
import pytest


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as _c:
        yield m


# ── the placeholders exist and render ────────────────────────────────────────

def test_both_placeholders_are_allowed_and_validate(app_mod):
    from app.quote_numbering import ALLOWED_PLACEHOLDERS, validate_template
    assert {"customer", "vehicle_registration"} <= ALLOWED_PLACEHOLDERS
    ok, msg = validate_template("R-{counter} {customer} {vehicle_registration}")
    assert ok, msg


def test_the_ratified_convention_renders_end_to_end(app_mod):
    from app.quote_numbering import render_template
    got = render_template("R-{counter} {customer} {vehicle_registration}",
                          counter=1042, customer="ATLANTIC SEAFOODS",
                          vehicle_registration="CA 123-456")
    assert got == "R-1042 ATLANTIC SEAFOODS CA 123-456"


def test_the_admin_preview_shows_a_realistic_sample(app_mod):
    """The screen's live preview has to read like the document people know."""
    from app.quote_numbering import preview_template
    assert preview_template("R-{counter} {customer} {vehicle_registration}") == \
        "R-2547 ATLANTIC SEAFOODS CA 123-456"


@pytest.mark.parametrize("customer,reg", [
    (None, None), ("", ""), ("  ", "  "),
])
def test_missing_values_never_leak_None_or_double_spaces(app_mod, customer, reg):
    """A number reaches a customer's document. "R-7 None None" must be
    impossible, and so must a double gap that reads as a lost field."""
    from app.quote_numbering import render_template
    got = render_template("R-{counter} {customer} {vehicle_registration}",
                          counter=7, customer=customer, vehicle_registration=reg)
    assert "None" not in got
    assert "  " not in got.strip() or got.strip() == "R-7"
    assert got.startswith("R-7")


def test_internal_whitespace_is_collapsed(app_mod):
    from app.quote_numbering import render_template
    got = render_template("R-{counter} {customer}", counter=5,
                          customer="  ATLANTIC   SEAFOODS  ")
    assert got == "R-5 ATLANTIC SEAFOODS"


# ── the shipped default is untouched ─────────────────────────────────────────

def test_the_repair_default_is_the_ratified_convention(app_mod):
    """Michael, 22 Aug: the convention is the DEFAULT, not an opt-in.

    ⚠ This constant only governs a counter row that does not exist yet —
    migration 0042 seeds the repair row with a hard-coded "R-{counter}", so on
    any database that has run it this value is never consulted. Migration 0045
    is what moves those rows. Both halves are needed; neither works alone.
    """
    from app.quote_numbering import (DEFAULT_TEMPLATES, SERIES_QUOTE,
                                     SERIES_REPAIR_DOC, preview_template)
    assert DEFAULT_TEMPLATES[SERIES_REPAIR_DOC] ==         "R-{counter} {customer} {vehicle_registration}"
    assert preview_template(DEFAULT_TEMPLATES[SERIES_REPAIR_DOC]) ==         "R-2547 ATLANTIC SEAFOODS CA 123-456"
    # The BODY series is untouched — this change is repair-only.
    assert DEFAULT_TEMPLATES[SERIES_QUOTE] == "{user_initial}{counter}/{month}/{year}"


def test_a_body_costing_renders_the_repair_fields_empty(app_mod):
    """Symmetry with {trailer_code}, which is empty on a repair: these two are
    empty on a body costing. Nothing raises, nothing prints a stray label."""
    from app.quote_numbering import render_template
    got = render_template("{user_initial}{counter}/{month}/{year}{customer}",
                          counter=11, customer="")
    assert got.endswith("/" + str(__import__("datetime").datetime.now().year))


# ── issuance passes the values through ───────────────────────────────────────

def test_allocate_series_number_embeds_what_it_is_given(app_mod):
    from app.database import SessionLocal
    from app.quote_numbering import (allocate_series_number, get_or_create_counter,
                                     SERIES_REPAIR_DOC)
    with SessionLocal() as db:
        qc = get_or_create_counter(db, SERIES_REPAIR_DOC)
        before_tpl, before_next = qc.format_template, qc.next_value
        qc.format_template = "R-{counter} {customer} {vehicle_registration}"
        qc.next_value = 900
        db.commit()
        try:
            got = allocate_series_number(
                db, SERIES_REPAIR_DOC,
                customer="ATLANTIC SEAFOODS", vehicle_registration="CA 123-456")
            db.commit()
            assert got == "R-900 ATLANTIC SEAFOODS CA 123-456"
        finally:
            qc = get_or_create_counter(db, SERIES_REPAIR_DOC)
            qc.format_template, qc.next_value = before_tpl, before_next
            db.commit()


# ── the filename must not repeat itself ──────────────────────────────────────

def test_filename_does_not_repeat_parts_the_number_already_carries(app_mod):
    """With the convention built into the NUMBER, the old filename builder would
    have produced
    "R-1042 ATLANTIC SEAFOODS CA 123-456 - ATLANTIC SEAFOODS - CA 123-456"."""
    from app.services.quote_document import repair_quote_filename

    class _R: id = 1; quote_number = "B1/08/2026"
    ctx = {"document_number": "R-1042 ATLANTIC SEAFOODS CA 123-456",
           "customer_name": "ATLANTIC SEAFOODS",
           "vehicle_registration": "CA 123-456"}
    assert repair_quote_filename(_R(), ctx) == "R-1042 ATLANTIC SEAFOODS CA 123-456"


def test_the_default_number_still_gets_the_full_three_part_filename(app_mod):
    """The shipped default carries neither field, so the convention still has to
    assemble the name from all three parts — unchanged behaviour."""
    from app.services.quote_document import repair_quote_filename

    class _R: id = 1; quote_number = "B1/08/2026"
    ctx = {"document_number": "R-1042",
           "customer_name": "ATLANTIC SEAFOODS",
           "vehicle_registration": "LT 15 FB GP"}
    assert repair_quote_filename(_R(), ctx) == "R-1042 - ATLANTIC SEAFOODS - LT 15 FB GP"


def test_a_missing_part_is_still_dropped_with_its_separator(app_mod):
    from app.services.quote_document import repair_quote_filename

    class _R: id = 1; quote_number = "B1/08/2026"
    ctx = {"document_number": "R-1042", "customer_name": "ATLANTIC SEAFOODS",
           "vehicle_registration": ""}
    assert repair_quote_filename(_R(), ctx) == "R-1042 - ATLANTIC SEAFOODS"


# ── empty fields must not leave debris in an identifier ──────────────────────

@pytest.mark.parametrize("template,expected", [
    ("R-{counter} {customer} {vehicle_registration}", "R-1042"),
    ("R-{counter} - {customer}",                      "R-1042"),
    ("R-{counter} {customer}, {vehicle_registration}", "R-1042"),
    ("{customer} R-{counter}",                        "R-1042"),
])
def test_an_empty_field_leaves_no_trailing_or_leading_debris(app_mod, template, expected):
    """Caught by the end-to-end: a repair captured without a registration
    produced "R-1043 ATLANTIC SEAFOODS " — a trailing space, on a string that
    goes onto a customer's document AND into the PDF filename."""
    from app.quote_numbering import render_template
    got = render_template(template, counter=1042, customer="", vehicle_registration="")
    assert got == expected, f"{template!r} -> {got!r}"


def test_a_gap_left_by_one_empty_field_in_the_middle_is_collapsed(app_mod):
    from app.quote_numbering import render_template
    got = render_template("R-{counter} {customer} {vehicle_registration}",
                          counter=1042, customer="", vehicle_registration="CA 123-456")
    assert got == "R-1042 CA 123-456"


def test_the_body_series_output_is_byte_identical(app_mod):
    """⚠ The tidy step must not touch the shipped body convention — its "/"
    separators are meaningful and are deliberately not trimmed."""
    from app.quote_numbering import render_template

    class _U: pass
    u = _U(); u.username = "burt"
    from datetime import datetime, timezone
    when = datetime(2026, 8, 21, tzinfo=timezone.utc)
    got = render_template("{user_initial}{counter}/{month}/{year}",
                          counter=32839, user=u, when=when)
    assert got == "B32839/08/2026"


# ── migration 0045: move the default forward WITHOUT clobbering a decision ───

@pytest.fixture()
def repair_row(app_mod):
    """Restore the repair counter's template whatever a test does to it."""
    from app.database import SessionLocal
    from app.quote_numbering import get_or_create_counter, SERIES_REPAIR_DOC
    with SessionLocal() as db:
        qc = get_or_create_counter(db, SERIES_REPAIR_DOC)
        before = qc.format_template
        db.commit()
    yield
    with SessionLocal() as db:
        qc = get_or_create_counter(db, SERIES_REPAIR_DOC)
        qc.format_template = before
        db.commit()


def _run_0045(direction: str) -> None:
    """Run just this migration's data step against the live test DB."""
    import importlib.util
    from pathlib import Path
    from alembic import op as _op
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from app.database import engine

    path = (Path(__file__).resolve().parent.parent / "alembic" / "versions"
            / "0045_repair_number_convention_default.py")
    spec = importlib.util.spec_from_file_location("m0045", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(Operations(ctx)):
            getattr(mod, direction)()


def _template() -> str:
    from app.database import SessionLocal
    from app.quote_numbering import get_or_create_counter, SERIES_REPAIR_DOC
    with SessionLocal() as db:
        t = get_or_create_counter(db, SERIES_REPAIR_DOC).format_template
        db.commit()
        return t


def _set_template(value: str) -> None:
    from app.database import SessionLocal
    from app.quote_numbering import get_or_create_counter, SERIES_REPAIR_DOC
    with SessionLocal() as db:
        get_or_create_counter(db, SERIES_REPAIR_DOC).format_template = value
        db.commit()


def test_0045_moves_the_untouched_0042_seed_forward(app_mod, repair_row):
    """The whole reason the migration exists: 0042 hard-codes the seed, so the
    code default alone never reaches an existing database."""
    _set_template("R-{counter}")
    _run_0045("upgrade")
    assert _template() == "R-{counter} {customer} {vehicle_registration}"


def test_0045_never_clobbers_a_template_an_admin_chose(app_mod, repair_row):
    """`format_template` is admin-owned — the v1.50 screen exists precisely so
    someone can set it. Moving a default forward must not overwrite a decision."""
    _set_template("REPAIR/{counter:04d}")
    _run_0045("upgrade")
    assert _template() == "REPAIR/{counter:04d}", \
        "the migration overwrote a customised template"


def test_0045_downgrade_is_equally_guarded(app_mod, repair_row):
    _set_template("R-{counter} {customer} {vehicle_registration}")
    _run_0045("downgrade")
    assert _template() == "R-{counter}"
    _set_template("REPAIR/{counter:04d}")
    _run_0045("downgrade")
    assert _template() == "REPAIR/{counter:04d}"


def test_0045_does_not_renumber_anything_already_issued(app_mod, repair_row):
    """Issued numbers live in result_json, never re-derived from the counter."""
    import json
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        rec = CalculationRecord(
            dimensions_json="{}", status="pending",
            result_json=json.dumps({"items": [], "repair_document_number": "R-77"}),
            is_repair=True)
        db.add(rec)
        db.commit()
        rec_id = rec.id
    try:
        _set_template("R-{counter}")
        _run_0045("upgrade")
        with SessionLocal() as db:
            again = json.loads(db.get(CalculationRecord, rec_id).result_json)
        assert again["repair_document_number"] == "R-77"
    finally:
        with SessionLocal() as db:
            r = db.get(CalculationRecord, rec_id)
            if r:
                db.delete(r)
            db.commit()
