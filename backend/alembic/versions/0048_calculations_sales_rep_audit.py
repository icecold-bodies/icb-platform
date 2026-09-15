"""Capture-for-user journal (Migration 0048).

Revision ID: 0048
Revises: 0047
Create Date: 2026-09-15

WO v1.52 capture-for-user (Michael, 15 Sep). An admin captures costings on behalf of
sales staff. The ATTRIBUTION already has a column — calculations.sales_rep_user_id
(migration 0017, "the sales rep this quote is being done FOR") — and the creator stays
in calculations.user_id, which is never rewritten. What had no home was the JOURNAL the
WO requires: who captured or re-assigned a costing, when, and from whom to whom.

It cannot live on the costing itself. result_json is rebuilt from scratch by both
edit-overwrite paths of /api/approve, so a log kept there survives only for as long as
every one of those paths remembers to copy it forward; and a pair of *_by / *_at columns
holds one change, not a history. Hence one append-only table, in the house audit shape
(production_jobs_audit 0023, chassis_records_audit 0029, floor_events 0037).

  icb_costings.calculations_sales_rep_audit  (NEW)
    - id              INTEGER PK
    - calculation_id  INTEGER NOT NULL FK -> icb_costings.calculations.id
                      ondelete=CASCADE. The app only ever SOFT-deletes a costing
                      (0043); the hard deletes that remain — the save modal's
                      "Replace" and test teardown — must keep working on a costing
                      that carries a journal, which RESTRICT would break.
    - action          VARCHAR(16) NOT NULL  'capture' | 'reassign'
    - from_user_id    INTEGER FK -> users.id ondelete=SET NULL
    - from_username   VARCHAR(100)          snapshot
    - to_user_id      INTEGER FK -> users.id ondelete=SET NULL
    - to_username     VARCHAR(100)          snapshot
    - actor_user_id   INTEGER FK -> users.id ondelete=SET NULL
    - actor_username  VARCHAR(100)          snapshot
    - created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    - ix_calc_rep_audit_calc_created (calculation_id, created_at) — the only read is
      "this costing's journal, in order".

Every person is stored twice, id + USERNAME snapshot (house audit idiom): the id goes
NULL if the user is removed, the snapshot keeps "Captured for Nadie by admin" readable
after a rename or a delete.

Nothing else changes: no column on calculations, no data written, no backfill (existing
costings keep resolving their rep to the creator, exactly as today). The permission key
this feature adds (costings.capture_for_user) needs no migration — the boot-time
_bootstrap_permissions seeds catalogue keys.

Inspector-guarded (table + index) -> idempotent on re-run; purely additive;
up->down->up round-trips clean (mirrors 0039/0044).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0048"
down_revision: Union[str, Sequence[str], None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "calculations_sales_rep_audit"
IX_CALC_CREATED = "ix_calc_rep_audit_calc_created"


def _tables(bind) -> set:
    return set(sa_inspect(bind).get_table_names(schema=COST))


def _indexes(bind) -> set:
    if TABLE not in _tables(bind):
        return set()
    return {i["name"] for i in sa_inspect(bind).get_indexes(TABLE, schema=COST)}


def upgrade() -> None:
    bind = op.get_bind()

    if TABLE not in _tables(bind):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("calculation_id", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(length=16), nullable=False),
            sa.Column("from_user_id", sa.Integer(), nullable=True),
            sa.Column("from_username", sa.String(length=100), nullable=True),
            sa.Column("to_user_id", sa.Integer(), nullable=True),
            sa.Column("to_username", sa.String(length=100), nullable=True),
            sa.Column("actor_user_id", sa.Integer(), nullable=True),
            sa.Column("actor_username", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["calculation_id"], [f"{COST}.calculations.id"],
                name="fk_calc_rep_audit_calculation_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["from_user_id"], [f"{COST}.users.id"],
                name="fk_calc_rep_audit_from_user_id", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["to_user_id"], [f"{COST}.users.id"],
                name="fk_calc_rep_audit_to_user_id", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["actor_user_id"], [f"{COST}.users.id"],
                name="fk_calc_rep_audit_actor_user_id", ondelete="SET NULL"),
            schema=COST,
        )

    if IX_CALC_CREATED not in _indexes(bind):
        op.create_index(IX_CALC_CREATED, TABLE, ["calculation_id", "created_at"],
                        schema=COST)


def downgrade() -> None:
    bind = op.get_bind()
    if IX_CALC_CREATED in _indexes(bind):
        op.drop_index(IX_CALC_CREATED, table_name=TABLE, schema=COST)
    if TABLE in _tables(bind):
        op.drop_table(TABLE, schema=COST)
