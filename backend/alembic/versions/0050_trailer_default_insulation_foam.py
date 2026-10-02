"""Per-body default PU foam grade (Migration 0050).

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-01

RT2 Part 1c (RT2_RULING_1 R6). Burt prices four bodies' PU at 4G FOAM on his sheets
(MEAT HANGER LARGE, MEAT HANGER SMALL-MEDIUM, EXPLOSIVE 4.9 AND UP, RHINORANGE TRAILER).
Once Manifest P moves their PU lines onto the shared 32D price, a new costing on them
must OPEN on 4G — the body's own default, set by an administrator in Body Templates —
instead of 32D or whatever foam the user's browser last remembered.

  icb_costings.trailer_types.default_insulation_foam  (NEW)
    - VARCHAR(8) NOT NULL DEFAULT '32D'
    - ck_trailer_types_default_insulation_foam: IN ('32D', '4G')

Every existing body reads '32D' — exactly what every new costing opened on before (v1.51
ratified default 7). The four 4G defaults are DATA, set in the v1.59.3 window (runbook),
never here: a migration that wrote them by id would change bodies on any database whose
ids differ. Nothing else changes; no backfill.

Inspector-guarded (column + constraint) -> idempotent on re-run; purely additive;
up->down->up round-trips clean (mirrors 0049).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0050"
down_revision: Union[str, Sequence[str], None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "trailer_types"
COLUMN = "default_insulation_foam"
CK = "ck_trailer_types_default_insulation_foam"


def _columns(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns(TABLE, schema=COST)}


def _checks(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_check_constraints(TABLE, schema=COST)}


def upgrade() -> None:
    bind = op.get_bind()
    if COLUMN not in _columns(bind):
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=8), nullable=False,
                                       server_default="32D"), schema=COST)
    if CK not in _checks(bind):
        op.create_check_constraint(CK, TABLE, f"{COLUMN} IN ('32D', '4G')", schema=COST)


def downgrade() -> None:
    bind = op.get_bind()
    if CK in _checks(bind):
        op.drop_constraint(CK, TABLE, type_="check", schema=COST)
    if COLUMN in _columns(bind):
        op.drop_column(TABLE, COLUMN, schema=COST)
