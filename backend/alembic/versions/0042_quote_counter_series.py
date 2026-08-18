"""Quote-counter SERIES — a second, independent numbering line (Migration 0042).

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-17

WO v1.47 Lane D (the ICB repair-quotation document, addendum D6). The repair
quotation carries its own R-prefixed document number (the sample shows
"R-231035462"), which must be INDEPENDENT of the body-costing quote number and
must never perturb that sequence.

`quote_counter` was built as an explicit SINGLETON — `get_or_create_counter()`
hardcodes `filter_by(id=1)` and its docstring says "id=1 always". There is no
series key, so a second numbering line cannot exist without this change. D6
ratified reusing the existing machinery rather than inventing a parallel one, so
this generalises the table by ONE column instead of adding a second table:

  icb_costings.quote_counter gains
    - series  VARCHAR(32) NOT NULL DEFAULT 'quote'

  and a unique index uq_quote_counter_series, so a series can never end up with
  two counter rows racing each other.

The existing row is backfilled to series='quote', which is exactly what it has
always been, so every current caller (assign_quote_number → the body-costing
sequence) keeps its counter, its next_value and its admin format template
untouched. `get_or_create_counter(db, series=...)` defaults to 'quote', so no
existing call site changes.

A second row for series='repair_doc' is seeded here with format "R-{counter}"
and next_value 1. Both are admin-editable afterwards, which is deliberate: if
ICB wants the MES series to CONTINUE from SAP's last issued number rather than
start at 1 (so no two documents in the filing system share a number), that is a
number only Michael can supply — it is set in admin, not guessed in a migration.

Idempotent (inspector-guarded on the column, the index and the seed row);
up->down->up round-trips clean. Downgrade drops the index and the column and
deletes any non-'quote' rows — the body-costing counter is never touched.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0042"
down_revision: Union[str, Sequence[str], None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "quote_counter"
COLUMN = "series"
UQ_SERIES = "uq_quote_counter_series"

DEFAULT_SERIES = "quote"
REPAIR_SERIES = "repair_doc"
REPAIR_TEMPLATE = "R-{counter}"


def _cols(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns(TABLE, schema=COST)}


def _indexes(bind) -> set:
    return {i["name"] for i in sa_inspect(bind).get_indexes(TABLE, schema=COST)}


def upgrade() -> None:
    bind = op.get_bind()

    if COLUMN not in _cols(bind):
        # server_default so the existing singleton row is backfilled to the
        # series it has always been, in the same statement.
        op.add_column(
            TABLE,
            sa.Column(COLUMN, sa.String(length=32), nullable=False,
                      server_default=sa.text(f"'{DEFAULT_SERIES}'")),
            schema=COST,
        )

    # Defensive: any row that predates the column (or a hand-inserted NULL).
    bind.execute(sa.text(
        f"UPDATE {COST}.{TABLE} SET {COLUMN} = :s WHERE {COLUMN} IS NULL"),
        {"s": DEFAULT_SERIES})

    if UQ_SERIES not in _indexes(bind):
        op.create_index(UQ_SERIES, TABLE, [COLUMN], unique=True, schema=COST)

    # Seed the repair-document series. next_value starts at 1 and is
    # admin-editable — see the module docstring on continuing SAP's sequence.
    existing = bind.execute(sa.text(
        f"SELECT 1 FROM {COST}.{TABLE} WHERE {COLUMN} = :s"),
        {"s": REPAIR_SERIES}).first()
    if existing is None:
        bind.execute(sa.text(
            f"INSERT INTO {COST}.{TABLE} (next_value, format_template, {COLUMN}) "
            "VALUES (1, :tpl, :s)"),
            {"tpl": REPAIR_TEMPLATE, "s": REPAIR_SERIES})


def downgrade() -> None:
    bind = op.get_bind()
    if COLUMN in _cols(bind):
        # Drop every series except the original body-costing one, so the table
        # goes back to the singleton it was.
        bind.execute(sa.text(
            f"DELETE FROM {COST}.{TABLE} WHERE {COLUMN} <> :s"), {"s": DEFAULT_SERIES})
    if UQ_SERIES in _indexes(bind):
        op.drop_index(UQ_SERIES, table_name=TABLE, schema=COST)
    if COLUMN in _cols(bind):
        op.drop_column(TABLE, COLUMN, schema=COST)
