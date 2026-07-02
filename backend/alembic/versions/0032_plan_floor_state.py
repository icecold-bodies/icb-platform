"""A09 Plan module (Phase 2) — persisted Production Flow floor state (Migration 0032).

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-02

Adds icb_mes.plan_floor_state — a single-row (id=1) JSON document holding the Plan
module's Production Flow floor (bodies on bays, merge blocks, consumed/merged sets).
Phase-2 hardening of the prototype: the floor was session-local; it now survives
reloads and is shared between users (last-write-wins, poll-refreshed). One physical
factory → one row; deliberately a coarse document store so the prototype's state
shape can evolve freely — event-level integration with the existing chassis/bay
chokepoints is a later phase. Inspector-guarded; additive; up→down→up clean.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0032"
down_revision: Union[str, Sequence[str], None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MES = "icb_mes"


def _tables(bind) -> set:
    return set(sa_inspect(bind).get_table_names(schema=MES))


def upgrade() -> None:
    bind = op.get_bind()
    if "plan_floor_state" not in _tables(bind):
        op.create_table(
            "plan_floor_state",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("state", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            schema=MES,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "plan_floor_state" in _tables(bind):
        op.drop_table("plan_floor_state", schema=MES)
