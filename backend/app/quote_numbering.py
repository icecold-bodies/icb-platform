"""Quote-number assignment.

A single global counter (`QuoteCounter` row) feeds an admin-editable format
template. Numbers are assigned exactly once per CalculationRecord and never
change after — re-saves and edits keep the original. Changing the template
in admin only affects records numbered *after* the change.

Format placeholders (allow-list):
  {user_initial} - first letter of username, uppercase
  {user}         - full username
  {counter}      - the integer (supports format specs like {counter:04d})
  {month}        - 2-digit month  ('04')
  {month_name}   - full month name ('April')
  {year}         - 4-digit year   ('2026')
  {year_short}   - 2-digit year   ('26')
  {trailer_code} - trailer type name, or empty
  {customer}     - customer name, or empty
  {vehicle_registration} - the repair's vehicle registration, or empty

⚠ {customer} and {vehicle_registration} are only ever populated on the REPAIR
series — they come off the repair quotation's own capture fields. On the body
series they render empty, exactly as {trailer_code} does on a repair.
"""
from __future__ import annotations

from datetime import datetime, timezone
from string import Formatter
from typing import Any, Optional

from sqlalchemy.orm import Session

from .database import QuoteCounter, CalculationRecord, User, TrailerType


ALLOWED_PLACEHOLDERS = {
    "user_initial", "user", "counter",
    "month", "month_name", "year", "year_short",
    "trailer_code",
    # v1.50 — the repair quotation's own identity fields, so an admin can build
    # the ratified R-number + customer + vehicle-registration convention into
    # the NUMBER as well as the filename. Both render empty when absent; the
    # shipped default template deliberately still uses neither.
    "customer", "vehicle_registration",
}

# Numbering SERIES (v1.47 Lane D, migration 0042). 'quote' is the original
# body-costing line; 'repair_doc' is the R-prefixed repair QUOTATION DOCUMENT
# number, which must never perturb the body sequence.
SERIES_QUOTE = "quote"
SERIES_REPAIR_DOC = "repair_doc"

DEFAULT_TEMPLATES = {
    SERIES_QUOTE:      "{user_initial}{counter}/{month}/{year}",
    # v1.50 — the ratified repair convention: R-number + customer + vehicle
    # registration (Michael, 22 Aug 2026), the same one the quotation FILENAME
    # already follows.
    # ⚠ This governs a counter row that does not exist yet. Migration 0042
    # SEEDS the repair row with a hard-coded "R-{counter}", so on every database
    # that has run it this constant is never consulted — migration 0045 is what
    # moves those existing rows forward, and only where the admin has not
    # customised the template.
    SERIES_REPAIR_DOC: "R-{counter} {customer} {vehicle_registration}",
}


def get_or_create_counter(db: Session, series: str = SERIES_QUOTE) -> QuoteCounter:
    """The counter row for one numbering SERIES, created on first use.

    v1.47 Lane D: this was a singleton keyed on id=1. It is now keyed on
    `series` (unique — migration 0042) so a second numbering line can exist.
    `series` defaults to 'quote', which IS the original line, so every existing
    caller keeps its counter, its next_value and its admin template untouched.

    The legacy id=1 row is ADOPTED as the 'quote' series rather than duplicated:
    0042 backfills it, and the fallback below covers any database where that
    backfill has not run yet.
    """
    qc = db.query(QuoteCounter).filter_by(series=series).first()
    if qc is not None:
        return qc
    if series == SERIES_QUOTE:
        # Adopt a genuine PRE-0042 row — one whose series was never set. Keyed on
        # the blank series, NOT on id=1: on any database created after 0042 the
        # seeded 'repair_doc' row IS id=1, and claiming it here silently made the
        # repair series double as the body series (body quotes numbering
        # themselves "R-1", "R-2"...). Caught by a direct check of the two series
        # on a fresh database.
        legacy = (db.query(QuoteCounter)
                    .filter((QuoteCounter.series.is_(None)) | (QuoteCounter.series == ""))
                    .order_by(QuoteCounter.id)
                    .first())
        if legacy is not None:
            legacy.series = SERIES_QUOTE
            db.flush()
            return legacy
    qc = QuoteCounter(
        next_value=1, series=series,
        format_template=DEFAULT_TEMPLATES.get(series, DEFAULT_TEMPLATES[SERIES_QUOTE]),
    )
    db.add(qc)
    db.flush()
    return qc


# Trailing/leading debris an EMPTY placeholder leaves behind. A number is an
# identifier that reaches a customer's document and a PDF filename, so
# "R-1043 ATLANTIC SEAFOODS " (empty registration) or "R-1043 -" (empty
# customer on a dash convention) must never escape the renderer.
# ⚠ "/" is deliberately NOT in this set: the body series' shipped convention is
# {user_initial}{counter}/{month}/{year} and this must not touch its output.
_NUMBER_EDGE_CHARS = " 	-,"


def _tidy_number(rendered: str) -> str:
    """Collapse whitespace runs and trim separator debris left by empty fields."""
    return " ".join(str(rendered or "").split()).strip(_NUMBER_EDGE_CHARS)


def render_template(template: str, *,
                    counter: int,
                    user: Optional[User] = None,
                    trailer: Optional[TrailerType] = None,
                    when: Optional[datetime] = None,
                    customer: str = "",
                    vehicle_registration: str = "") -> str:
    """Render the template with the allow-listed placeholders. Unknown
    placeholders are replaced with the empty string (never raise) so an admin
    typo doesn't break record creation."""
    when = when or datetime.now(timezone.utc)
    username = (user.username if user else "") or ""

    ctx: dict[str, Any] = {
        "user_initial": (username[:1].upper() if username else ""),
        "user":         username,
        "counter":      int(counter),
        "month":        when.strftime("%m"),
        "month_name":   when.strftime("%B"),
        "year":         when.strftime("%Y"),
        "year_short":   when.strftime("%y"),
        "trailer_code": (trailer.name if trailer else "") or "",
        # Collapsed, never None: a number is an identifier, and a stray double
        # space or a literal "None" in one is the kind of thing that reaches a
        # customer's document before anyone notices.
        "customer":             " ".join(str(customer or "").split()),
        "vehicle_registration": " ".join(str(vehicle_registration or "").split()),
    }

    class _SafeDict(dict):
        def __missing__(self, key):
            return ""

    try:
        return _tidy_number(template.format_map(_SafeDict(ctx)))
    except (ValueError, KeyError, IndexError):
        # Malformed template — fall back to a sensible default so saves still work.
        return _tidy_number(
            f"{ctx['user_initial']}{counter}/{ctx['month']}/{ctx['year']}")


def preview_template(template: str, *, sample_user: str = "Burt",
                     sample_counter: int = 2547,
                     sample_trailer: str = "EXPLOSIVE",
                     sample_customer: str = "ATLANTIC SEAFOODS",
                     sample_vehicle_registration: str = "CA 123-456") -> str:
    """Render a deterministic sample for the admin UI preview.

    The customer/registration samples match the ones the repair quotation's
    filename convention is documented with, so what the admin screen previews
    reads like the document they already know.
    """
    class _U: pass
    u = _U(); u.username = sample_user
    class _T: pass
    t = _T(); t.name = sample_trailer
    return render_template(template, counter=sample_counter, user=u, trailer=t,
                           when=datetime.now(timezone.utc),
                           customer=sample_customer,
                           vehicle_registration=sample_vehicle_registration)


def validate_template(template: str) -> tuple[bool, str]:
    """Return (ok, message). Rejects unknown placeholders and unparseable specs."""
    if not template or not template.strip():
        return False, "Template cannot be empty."
    try:
        fields = [fname for _, fname, _, _ in Formatter().parse(template) if fname]
    except Exception as e:
        return False, f"Could not parse template: {e}"
    bad = [f for f in fields if f not in ALLOWED_PLACEHOLDERS]
    if bad:
        return False, f"Unknown placeholder(s): {', '.join(sorted(set(bad)))}"
    if "counter" not in fields:
        return False, "Template must include {counter} so numbers stay unique."
    # Try a render to catch format-spec errors (e.g. {counter:zzz}).
    try:
        preview_template(template)
    except Exception as e:
        return False, f"Template render failed: {e}"
    return True, "OK"


def assign_quote_number(rec: CalculationRecord, *, db: Session,
                        user: Optional[User] = None,
                        trailer: Optional[TrailerType] = None) -> str:
    """Atomically allocate the next counter value, format it, stamp the
    record, and return the assigned string. Idempotent: if rec.quote_number
    is already set, returns it without bumping the counter."""
    if rec.quote_number:
        return rec.quote_number

    qc = get_or_create_counter(db)

    # Lock the row to make the increment safe under concurrent saves.
    # SQLite ignores FOR UPDATE but its default serialised writes still
    # protect us; MySQL InnoDB honours it.
    locked = (db.query(QuoteCounter)
                .filter_by(id=qc.id)
                .with_for_update()
                .first())
    if locked is None:
        locked = qc

    counter_value = int(locked.next_value or 1)
    locked.next_value = counter_value + 1
    db.flush()

    user = user or rec.user
    trailer = trailer or rec.trailer_type
    rendered = render_template(
        locked.format_template or "{user_initial}{counter}/{month}/{year}",
        counter=counter_value, user=user, trailer=trailer,
        when=rec.created_at or datetime.now(timezone.utc),
    )
    rec.quote_number = rendered
    db.flush()
    return rendered


def allocate_series_number(db: Session, series: str, *,
                           user: Optional[User] = None,
                           when: Optional[datetime] = None,
                           customer: str = "",
                           vehicle_registration: str = "") -> str:
    """Atomically allocate + format the next number on any SERIES.

    The row-locking, the increment and the template rendering are the SAME as
    assign_quote_number's — this is that function with the CalculationRecord
    stamping factored out, so a document number can be issued for a series that
    has no quote_number column of its own to be idempotent against.

    ⚠ NOT idempotent by itself, precisely because there is no record field to
    check: every call consumes a number. Callers must persist what they get and
    return early when it is already set (see the repair-document path), exactly
    as assign_quote_number's `if rec.quote_number` guard does.
    """
    qc = get_or_create_counter(db, series)
    locked = (db.query(QuoteCounter)
                .filter_by(id=qc.id)
                .with_for_update()
                .first())
    if locked is None:
        locked = qc

    counter_value = int(locked.next_value or 1)
    locked.next_value = counter_value + 1
    db.flush()

    rendered = render_template(
        locked.format_template or DEFAULT_TEMPLATES.get(series, "{counter}"),
        counter=counter_value, user=user, trailer=None,
        when=when or datetime.now(timezone.utc),
        customer=customer, vehicle_registration=vehicle_registration,
    )
    db.flush()
    return rendered
