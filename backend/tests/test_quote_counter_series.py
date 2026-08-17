"""v1.47 Lane D — the quote-counter SERIES (migration 0042).

The repair QUOTATION DOCUMENT carries its own R-prefixed number. D6 requires
that series to be INDEPENDENT of the body-costing quote sequence and never to
perturb it, so these pin exactly that:

  * the two series are separate rows with their OWN templates
  * issuing R-numbers never moves the body counter
  * R-numbers increment, and the body sequence keeps its own format
  * ⚠ the regression this file exists for: `get_or_create_counter('quote')` used
    to adopt whatever row happened to be `id=1` as the body series. On any
    database created after 0042 the SEEDED 'repair_doc' row IS id=1, so the body
    series silently became the repair series and body costings started numbering
    themselves "R-1", "R-2"... The adoption now keys on a BLANK series (a genuine
    pre-0042 row), never on an id.
"""
import pytest


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as _c:
        yield m


@pytest.fixture()
def clean_counters(app_mod):
    """Reproduce a FRESH post-0042 database: the only counter row is the seeded
    'repair_doc' one, and it holds **id=1**.

    ⚠ The id matters and must be forced. Deleting rows leaves the identity
    sequence where it was, so a re-inserted row gets some high id — and with a
    high id the old `filter_by(id=1)` adoption simply finds nothing and the bug
    hides. Pinning id=1 is what makes these tests load-bearing: with the buggy
    lookup restored they go red, with the fix they pass.
    """
    from sqlalchemy import text
    from app.database import SessionLocal, QuoteCounter
    from app.quote_numbering import SERIES_REPAIR_DOC
    with SessionLocal() as db:
        db.query(QuoteCounter).delete()
        db.flush()
        db.add(QuoteCounter(id=1, next_value=1, series=SERIES_REPAIR_DOC,
                            format_template="R-{counter}"))
        db.commit()
        # Realign the identity sequence so the NEXT insert does not collide with
        # the explicit id=1 we just forced.
        try:
            db.execute(text(
                "SELECT setval(pg_get_serial_sequence('icb_costings.quote_counter','id'), "
                "(SELECT COALESCE(MAX(id),1) FROM icb_costings.quote_counter))"))
            db.commit()
        except Exception:
            db.rollback()          # non-postgres backend: nothing to realign
    yield
    with SessionLocal() as db:
        db.query(QuoteCounter).delete()
        db.commit()


def test_the_two_series_are_separate_rows_with_their_own_templates(clean_counters):
    from app.database import SessionLocal
    from app.quote_numbering import (get_or_create_counter, SERIES_QUOTE,
                                     SERIES_REPAIR_DOC)
    with SessionLocal() as db:
        q = get_or_create_counter(db, SERIES_QUOTE)
        r = get_or_create_counter(db, SERIES_REPAIR_DOC)
        db.commit()
        assert q.id != r.id, "the body series adopted the repair series' row"
        assert q.series == SERIES_QUOTE
        assert r.series == SERIES_REPAIR_DOC
        # The body series must keep the BODY format, not inherit "R-{counter}".
        assert "R-" not in q.format_template
        assert "{counter}" in q.format_template
        assert r.format_template.startswith("R-")


def test_issuing_repair_numbers_never_moves_the_body_counter(clean_counters):
    """D6's actual requirement, asserted directly."""
    from app.database import SessionLocal
    from app.quote_numbering import (get_or_create_counter, allocate_series_number,
                                     SERIES_QUOTE, SERIES_REPAIR_DOC)
    with SessionLocal() as db:
        body = get_or_create_counter(db, SERIES_QUOTE)
        before = int(body.next_value)
        issued = [allocate_series_number(db, SERIES_REPAIR_DOC) for _ in range(3)]
        db.commit()
        db.refresh(body)
        assert body.next_value == before, "the body quote sequence was perturbed"
    assert issued == ["R-1", "R-2", "R-3"], issued


def test_body_quote_numbers_are_unaffected_by_the_series_split(clean_counters):
    """A body costing still numbers itself the way it always did."""
    from app.database import SessionLocal, CalculationRecord
    from app.quote_numbering import assign_quote_number, allocate_series_number, SERIES_REPAIR_DOC
    with SessionLocal() as db:
        allocate_series_number(db, SERIES_REPAIR_DOC)     # burn one on the other series
        rec = CalculationRecord(result_json="{}", dimensions_json="{}")
        db.add(rec)
        db.flush()
        number = assign_quote_number(rec, db=db)
        db.rollback()
    assert not number.startswith("R-"), (
        f"body quote number came off the repair series: {number!r}")
    assert "/" in number, f"body quote number lost its date format: {number!r}"


def test_allocation_is_not_idempotent_and_callers_must_persist(clean_counters):
    """allocate_series_number has no record field to be idempotent against, so
    it consumes a number on EVERY call. Pinned so nobody later assumes otherwise
    — the repair-save path guards on the stored number for exactly this reason."""
    from app.database import SessionLocal
    from app.quote_numbering import allocate_series_number, SERIES_REPAIR_DOC
    with SessionLocal() as db:
        a = allocate_series_number(db, SERIES_REPAIR_DOC)
        b = allocate_series_number(db, SERIES_REPAIR_DOC)
        db.commit()
    assert a != b
