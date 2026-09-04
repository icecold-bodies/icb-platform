"""BOM line price_updated_at stamp (Migration 0047).

Revision ID: 0047
Revises: 0046
Create Date: 2026-09-04

WO v1.52 (September price + description update). Sales must see an
"Updated Sep 2026" marker on every line the September import changed, self-
expiring 30 days after the apply. The existing markers are material-level
(`materials.last_updated` — 7-day chip; `materials.last_bulk_update_at` —
30-day amber chip), and material stamps cannot mark two whole classes of
September changes:

  * PU foam lines — their price lives in `unit_price_override` per the 0046
    architecture; the shared per-section PU materials are deliberately not
    touched, so nothing material-level moves when the override does;
  * SPLIT repoints — a changed line can be repointed to a material that
    already existed (created for an earlier line in the same run, or a
    pre-existing row that already carries the target name+price), whose own
    stamps say nothing about THIS line changing.

  icb_costings.bill_of_materials gains (NULLABLE — additive, existing rows
  unaffected; NULL renders no marker):
    - price_updated_at  TIMESTAMPTZ

The September import stamps it on every line it touches (price, description
or override reset); the calculator renders the marker while the stamp is
younger than 30 days. Nothing ever needs to clear it — expiry is read-side,
exactly like the last_bulk_update_at amber chip.

Inspector-guarded -> idempotent on re-run; purely additive; up->down->up
round-trips clean (mirrors 0041).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0047"
down_revision: Union[str, Sequence[str], None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "bill_of_materials"
COLUMN = "price_updated_at"


def _bom_cols(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns(TABLE, schema=COST)}


def upgrade() -> None:
    bind = op.get_bind()
    if COLUMN not in _bom_cols(bind):
        op.add_column(TABLE, sa.Column(COLUMN, sa.DateTime(timezone=True), nullable=True),
                      schema=COST)


def downgrade() -> None:
    bind = op.get_bind()
    if COLUMN in _bom_cols(bind):
        op.drop_column(TABLE, COLUMN, schema=COST)
