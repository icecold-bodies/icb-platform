"""Body families: a colour and an order on trailer_groups (Migration 0051).

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-02

RT3 (RT3_RULING_1). A body's family IS its trailer group: the group that already decides its
default quote template. Sales recognise a family by its colour, and the BODY TYPE dropdown
lists the families in Michael's order (Explosive, Chiller, Freezer, Meat, Ice cream, Other).

  icb_costings.trailer_groups.colour      (NEW)  VARCHAR(7) NULL
    - ck_trailer_groups_colour: NULL or '#RRGGBB'
    - NULL = no colour yet: the UI shows the fallback grey
  icb_costings.trailer_groups.sort_order  (NEW)  INTEGER NOT NULL DEFAULT 100

Schema only. The six families, their colours and every body's family are DATA, applied on
prod by the guarded data step ops/prod-rt3/rt3_families.sh (dry-run -> apply -> journal ->
revert), never here: a migration that wrote them by id or by name would change groups on any
database whose rows differ. Every existing group reads colour NULL, sort_order 100. No
template binding changes.

Inspector-guarded (columns + constraint) -> idempotent on re-run; purely additive;
up->down->up round-trips clean (mirrors 0050).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0051"
down_revision: Union[str, Sequence[str], None] = "0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "trailer_groups"
CK = "ck_trailer_groups_colour"


def _columns(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns(TABLE, schema=COST)}


def _checks(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_check_constraints(TABLE, schema=COST)}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind)
    if "colour" not in cols:
        op.add_column(TABLE, sa.Column("colour", sa.String(length=7), nullable=True), schema=COST)
    if "sort_order" not in cols:
        op.add_column(TABLE, sa.Column("sort_order", sa.Integer(), nullable=False,
                                       server_default="100"), schema=COST)
    if CK not in _checks(bind):
        op.create_check_constraint(CK, TABLE, "colour IS NULL OR colour ~ '^#[0-9A-Fa-f]{6}$'", schema=COST)


def downgrade() -> None:
    bind = op.get_bind()
    if CK in _checks(bind):
        op.drop_constraint(CK, TABLE, type_="check", schema=COST)
    cols = _columns(bind)
    if "sort_order" in cols:
        op.drop_column(TABLE, "sort_order", schema=COST)
    if "colour" in cols:
        op.drop_column(TABLE, "colour", schema=COST)
