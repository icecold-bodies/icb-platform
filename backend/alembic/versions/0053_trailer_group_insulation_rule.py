"""Body families: a machine-readable insulation rule on trailer_groups (Migration 0053).

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-06

RT6 (RT6_DISPATCH default 1, RT6_RULING_1 Q1). Burt's two product rules ("No PU insulation for Chillers";
"Freezers: EPS insulation in the ROOF and FLOOR only") are ENFORCED from data on the family, beside RT5's free-text
rule note, so a new chiller or freezer carries them automatically.

  icb_costings.trailer_groups.insulation_rule  (NEW)  TEXT NULL
    - canonical JSON {"allowed": {"FRONT": [...], "SIDES": [...], "ROOF": [...], "FLOOR": [...], "DRD": [...],
      "SRD": [...]}} — which insulation (EPS, PU) is ALLOWED on each of the six panels; all six always listed
      (services/insulation_rules.normalise_rule refuses anything else)
    - NULL = no rule: nothing is enforced for that family
    - edited by an administrator in Admin -> Quote templates (the family editor's grid); admin-only in the API

Schema only. Burt's two rules are DATA, applied on prod by the guarded data step ops/prod-rt6/rt6_rules.sh
(dry-run -> apply -> journal -> revert), never here. Every existing group reads NULL. Nothing priced moves.

Inspector-guarded -> idempotent on re-run; purely additive; up->down->up round-trips clean (mirrors 0052).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0053"
down_revision: Union[str, Sequence[str], None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "trailer_groups"
COLUMN = "insulation_rule"


def _columns(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns(TABLE, schema=COST)}


def upgrade() -> None:
    if COLUMN not in _columns(op.get_bind()):
        op.add_column(TABLE, sa.Column(COLUMN, sa.Text(), nullable=True), schema=COST)


def downgrade() -> None:
    if COLUMN in _columns(op.get_bind()):
        op.drop_column(TABLE, COLUMN, schema=COST)
