"""Nadie WO (16 Jul) — first direct coverage of app/quote_numbering.py.

The duplicate-modal's new save_as_new mode leans on assign_quote_number allocating
the next number off the running QuoteCounter (the single call site at the end of
api_approve's insert path — the same one every fresh save uses). These tests pin
that contract at unit level: the
counter is a persisted running sequence (N9950 → N9951, date parts are template
decoration only) and assignment is exactly-once per record. The /api/approve
pipeline itself needs the full BOM universe the test DB doesn't have
(test_calculation_contact_api.py precedent), so the three-way modal flow is
exercised in the live click-through instead.
"""
import pytest


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


@pytest.fixture
def two_recs(app_mod):
    from app.database import CalculationRecord, SessionLocal
    ids = []
    with SessionLocal() as db:
        for _ in range(2):
            rec = CalculationRecord(dimensions_json="{}", result_json='{"items": []}',
                                    status="pending")
            db.add(rec)
            db.commit()
            db.refresh(rec)
            ids.append(rec.id)
    yield ids
    with SessionLocal() as db:
        for rid in ids:
            r = db.get(CalculationRecord, rid)
            if r:
                db.delete(r)
        db.commit()


def _counter_value(db) -> int:
    """The BODY-costing counter's next value.

    v1.47 Lane D: this used to read `db.get(QuoteCounter, 1)`, which baked in the
    old singleton ("id=1 always"). Migration 0042 keys the table by `series`, and
    on a database built after it the row at id=1 is the seeded 'repair_doc' one —
    so an id lookup silently measured the WRONG sequence. The assertions in this
    file are unchanged; only the way the counter row is found is.
    """
    from app.quote_numbering import get_or_create_counter, SERIES_QUOTE
    row = get_or_create_counter(db, SERIES_QUOTE)
    return int(row.next_value or 1) if row is not None else 1


def test_running_counter_allocates_sequential_numbers(app_mod, two_recs):
    """Two fresh records get distinct numbers embedding consecutive counter values,
    and the singleton counter advances by exactly 2 — running sequence, not
    date-derived (template renders {counter}; month/year are cosmetic suffix)."""
    from app.database import CalculationRecord, SessionLocal
    from app.quote_numbering import assign_quote_number

    with SessionLocal() as db:
        before = _counter_value(db)
        r1, r2 = (db.get(CalculationRecord, rid) for rid in two_recs)
        q1 = assign_quote_number(r1, db=db)
        q2 = assign_quote_number(r2, db=db)
        db.commit()
        assert q1 and q2 and q1 != q2
        assert str(before) in q1, f"{q1!r} should embed counter value {before}"
        assert str(before + 1) in q2, f"{q2!r} should embed counter value {before + 1}"
        assert _counter_value(db) == before + 2


def test_assignment_is_idempotent_and_counter_untouched(app_mod, two_recs):
    """Re-assigning a record that already has a number returns the SAME number and
    does not advance the counter — the guard api_approve's revision reuse path
    relies on ('assign_quote_number below is idempotent — it returns early when
    rec.quote_number is set')."""
    from app.database import CalculationRecord, SessionLocal
    from app.quote_numbering import assign_quote_number

    with SessionLocal() as db:
        r1 = db.get(CalculationRecord, two_recs[0])
        first = assign_quote_number(r1, db=db)
        db.commit()
        mid = _counter_value(db)
        again = assign_quote_number(r1, db=db)
        db.commit()
        assert again == first
        assert _counter_value(db) == mid, "idempotent re-assign must not advance the counter"
