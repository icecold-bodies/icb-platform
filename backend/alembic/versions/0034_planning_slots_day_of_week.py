"""A10 V/P day-slots — planning_slots.day_of_week (Migration 0034).

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-07

Adds day granularity to V/P planning (Simeon-ratified A10 v0.2, BA handover
2026-07-05): one job per bay per DAY instead of per week.

  - day_of_week  INTEGER, NULLABLE — 0=Mon .. 6=Sun (weekends 5/6 are the
                 skinny overtime slots). Guarded by a DB CHECK (NULL or 0..6).
  - Backfill: existing weekly slots become Monday (0) — a weekly booking's
    planned_start_date was already the week's Monday, so semantics carry over.

Cell exclusivity stays APP-enforced at the service `_occupied` chokepoint
(now (bay, week, day)-keyed), matching the existing "bay is free-text,
exclusivity is app-derived" pattern — no DB uniqueness added, and legacy
NULL-day rows (created by direct fixture inserts) normalise to Monday in code.

Inspector-guarded (column + CHECK) → idempotent on re-run; purely additive
ALTER; up→down→up round-trips clean (mirrors the proven 0026/0031 pattern).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0034"
down_revision: Union[str, Sequence[str], None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MES = "icb_mes"
CK_DOW = "planning_slots_day_of_week_range"


def _cols(bind, table, schema) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns(table, schema=schema)}


def _checks(bind, table, schema) -> set:
    return {c["name"] for c in sa_inspect(bind).get_check_constraints(table, schema=schema)}


def upgrade() -> None:
    bind = op.get_bind()
    if "day_of_week" not in _cols(bind, "planning_slots", MES):
        op.add_column("planning_slots",
                      sa.Column("day_of_week", sa.Integer(), nullable=True), schema=MES)
    if CK_DOW not in _checks(bind, "planning_slots", MES):
        op.create_check_constraint(
            CK_DOW, "planning_slots",
            "day_of_week IS NULL OR (day_of_week >= 0 AND day_of_week <= 6)", schema=MES,
        )
    # Backfill existing weekly slots to Monday (0) for backward compatibility.
    op.execute(f"UPDATE {MES}.planning_slots SET day_of_week = 0 WHERE day_of_week IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if CK_DOW in _checks(bind, "planning_slots", MES):
        op.drop_constraint(CK_DOW, "planning_slots", type_="check", schema=MES)
    if "day_of_week" in _cols(bind, "planning_slots", MES):
        op.drop_column("planning_slots", "day_of_week", schema=MES)
