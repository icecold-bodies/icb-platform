"""Costing soft delete (Migration 0043).

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-18

v1.49. An admin can delete a repair costing from the costings board. Ratified by
Michael on 18 Aug: it "only disappears from the costing board. It will only show
if the user selects a 'Deleted' pill" — so this is a SOFT delete. The row stays,
and everything that references it keeps resolving.

That choice is what makes the feature safe rather than merely convenient. The
alternative, a real DELETE, is genuinely dangerous here: exactly three things in
either schema reference a costing, and they fail in opposite ways —

    icb_costings.validated_references.calculation_id   ON DELETE CASCADE
    icb_mes.prejob_cards.calculation_id                ON DELETE RESTRICT
    icb_mes.production_jobs.calculation_record_id      NO FOREIGN KEY AT ALL

the last of which would NOT raise anything. The FK that migration 0003 describes
is absent from the live database (production_jobs carries only branch,
chassis_record and current_bom FKs, plus a UNIQUE on calculation_record_id whose
"_key" name reads like an FK but is not). A hard delete would therefore succeed
and leave a job on the floor pointing at a costing that no longer exists.

  icb_costings.calculations gains (both NULLABLE — additive, every existing row
  is untouched and reads as not-deleted):
    - deleted_at  TIMESTAMPTZ   when it was deleted; NULL = live
    - deleted_by  VARCHAR(120)  the actor's USERNAME, snapshotted at write time

deleted_by is a denormalised username rather than a users FK, following the house
audit idiom (feedback-audit-denormalize-name-snapshot): the record of who deleted
a costing must survive that user later being removed or renamed.

An index on deleted_at because the costings list filters on it on EVERY read —
the board shows live costings by default, and the "Deleted" pill is the only way
to see the others.

Deliberately NOT a status value: `status` already carries the quote's own
lifecycle (pending / accepted / declined / pre_job_sent / pre_job_confirmed /
planning). Overwriting it would destroy the state the costing was in, and an
undelete could not put it back.

Inspector-guarded -> idempotent on re-run; purely additive; up->down->up
round-trips clean (mirrors 0035/0039/0040/0041).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0043"
down_revision: Union[str, Sequence[str], None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "calculations"
COL_AT = "deleted_at"
COL_BY = "deleted_by"
INDEX = "ix_calculations_deleted_at"


def _cols(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns(TABLE, schema=COST)}


def _indexes(bind) -> set:
    return {i["name"] for i in sa_inspect(bind).get_indexes(TABLE, schema=COST)}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _cols(bind)
    if COL_AT not in cols:
        op.add_column(TABLE, sa.Column(COL_AT, sa.DateTime(timezone=True), nullable=True),
                      schema=COST)
    if COL_BY not in cols:
        op.add_column(TABLE, sa.Column(COL_BY, sa.String(length=120), nullable=True),
                      schema=COST)
    if INDEX not in _indexes(bind):
        op.create_index(INDEX, TABLE, [COL_AT], schema=COST)


def downgrade() -> None:
    bind = op.get_bind()
    if INDEX in _indexes(bind):
        op.drop_index(INDEX, table_name=TABLE, schema=COST)
    cols = _cols(bind)
    if COL_BY in cols:
        op.drop_column(TABLE, COL_BY, schema=COST)
    if COL_AT in cols:
        op.drop_column(TABLE, COL_AT, schema=COST)
