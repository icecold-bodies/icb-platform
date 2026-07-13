"""A11 Pre-Assembly Chute — pre_assembly threshold placeholder 40h → the ratified 2h.

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-13

Simeon's ratified A11 spec: a panel-set dropped into a Pre-Assembly bay takes ~2h to
become an assembled body, uniform across body types. Migration 0036 seeded the
downstream-stage thresholds as admin-editable PLACEHOLDERS (pre_assembly = 40.00 h);
this data migration realizes the ratified value.

GUARDED like the 0031/0034 pattern: the UPDATE only fires while the row still holds
the untouched 40.00 placeholder — a value Michael has already tuned through the
Admin → Production Stage Thresholds surface is never overwritten (prod precedent:
he re-tuned panels_ready there on 9 Jul). Idempotent on re-run; downgrade restores
the placeholder only if the row still holds exactly 2.00.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0038"
down_revision: Union[str, Sequence[str], None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MES = "icb_mes"


def upgrade() -> None:
    op.execute(
        f"UPDATE {MES}.production_stage_thresholds "
        f"SET threshold_hours = 2.00, version = version + 1, "
        f"    updated_at = now(), updated_by = 'migration_0038' "
        f"WHERE stage_code = 'pre_assembly' AND threshold_hours = 40.00"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE {MES}.production_stage_thresholds "
        f"SET threshold_hours = 40.00, version = version + 1, "
        f"    updated_at = now(), updated_by = 'migration_0038_down' "
        f"WHERE stage_code = 'pre_assembly' AND threshold_hours = 2.00"
    )
