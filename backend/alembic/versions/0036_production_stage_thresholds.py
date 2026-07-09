"""Production stage thresholds — admin-captured per-stage duration targets (Migration 0036).

Revision ID: 0036
Revises: 0035
Create Date: 2026-07-09

Admin Master-Data WO: capture how long panels should spend in a production stage
(vacuum=8h, press=4h — Michael's examples, seeded below); the planning board turns a
scheduled V/P day-slot into elapsed-vs-threshold progress bars. The table is
STAGE-GENERIC (future stages = new rows, no schema change); the clock semantics
(start at workday_start on the slot's scheduled day, wall-clock 24/7) live in
services/planning.build_board, not here.

NEW icb_mes.production_stage_thresholds via the model-driven guarded create_all
(0018 fridge_units idiom) — includes the stage_code UNIQUE and the
threshold_hours > 0 CHECK from the model's __table_args__. Seed is idempotent
(ON CONFLICT DO NOTHING on stage_code), so CI's up→down→up round-trip re-seeds
cleanly and a re-run on a seeded DB is a no-op. Downgrade drops the table guarded.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect as sa_inspect, text as sa_text

revision: str = "0036"
down_revision: Union[str, Sequence[str], None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_obj():
    from app.database import Base
    import app.models.mes  # noqa: F401  (registers ProductionStageThreshold)
    return Base.metadata.tables["icb_mes.production_stage_thresholds"]


def _have(bind) -> bool:
    return "production_stage_thresholds" in sa_inspect(bind).get_table_names(schema="icb_mes")


def upgrade() -> None:
    bind = op.get_bind()
    if not _have(bind):
        from app.database import Base
        Base.metadata.create_all(bind=bind, tables=[_table_obj()])
    # Seed the two ratified stages (Michael's example values). ON CONFLICT keeps
    # re-runs and already-seeded DBs untouched — admin edits are never clobbered.
    op.execute(sa_text(
        "INSERT INTO icb_mes.production_stage_thresholds "
        "(stage_code, label, threshold_hours, workday_start, is_active, version, created_by) VALUES "
        "('vacuum', 'Vacuum', 8.00, '07:00:00', true, 1, 'migration_0036'), "
        "('press',  'Press',  4.00, '07:00:00', true, 1, 'migration_0036') "
        "ON CONFLICT (stage_code) DO NOTHING"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    if _have(bind):
        from app.database import Base
        Base.metadata.drop_all(bind=bind, tables=[_table_obj()])
