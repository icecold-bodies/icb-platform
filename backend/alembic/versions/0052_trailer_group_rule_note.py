"""Body families: a rule note on trailer_groups (Migration 0052).

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-05

RT5 (RT5_DISPATCH design 1, RT5_RULING_1). Burt's product rules for a family of bodies ("No PU insulation for
Chillers"; "Freezers: EPS insulation in the ROOF and FLOOR only, ...") are shown in red under BODY OPTIONS on
every body of that family, and under the body's header in Body Templates. The rule lives on the family, not in
code, so a new chiller or freezer carries it automatically.

  icb_costings.trailer_groups.rule_note  (NEW)  TEXT NULL
    - plain text, multi-line allowed; NULL (or empty) = no note
    - edited by an administrator in Admin -> Quote templates (the family editor); never on a customer document

Schema only. The two notes are DATA, applied on prod by the guarded data step ops/prod-rt5/rt5_notes.sh
(dry-run -> apply -> journal -> revert), never here: a migration that wrote them by group id or name would change
groups on any database whose rows differ. Every existing group reads NULL. Nothing priced moves.

Inspector-guarded -> idempotent on re-run; purely additive; up->down->up round-trips clean (mirrors 0051).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0052"
down_revision: Union[str, Sequence[str], None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "trailer_groups"
COLUMN = "rule_note"


def _columns(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns(TABLE, schema=COST)}


def upgrade() -> None:
    if COLUMN not in _columns(op.get_bind()):
        op.add_column(TABLE, sa.Column(COLUMN, sa.Text(), nullable=True), schema=COST)


def downgrade() -> None:
    if COLUMN in _columns(op.get_bind()):
        op.drop_column(TABLE, COLUMN, schema=COST)
