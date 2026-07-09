"""§9 floor-doc event integration P1 — floor_events journal + plan_floor_state.version (0037).

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-09

v1.41.0: the /plan floor document becomes SERVER-authoritative. Every floor mutation
arrives as a typed transition (services/floor.apply_transition) that locks the singleton
plan_floor_state row, validates, applies, bumps `version`, and appends a floor_events
row — the floor's first audit trail, and the death of the whole-document PUT that let
two browsers clobber each other (and mock-mode sessions seed-stomp the shared floor).

  - plan_floor_state.version  INTEGER NOT NULL default 0 (the 0029 chassis_records.version idiom)
  - icb_mes.floor_events      via the model-driven guarded create_all (0018/0036 idiom) —
                              indexes ride the model; the same-schema production_job_id
                              FK (SET NULL) rides create_all
  - fk_floor_events_user      cross-schema FK → icb_costings.users (SET NULL), created
                              HERE per the 0023/0029 house idiom (cross-schema FKs are
                              excluded from autogenerate/create_all)

Inspector-guarded throughout; up→down→up round-trips clean.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0037"
down_revision: Union[str, Sequence[str], None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MES = "icb_mes"
FK_USER = "fk_floor_events_user"


def _table_obj():
    from app.database import Base
    import app.models.mes  # noqa: F401  (registers FloorEvent)
    return Base.metadata.tables["icb_mes.floor_events"]


def _have_table(bind) -> bool:
    return "floor_events" in sa_inspect(bind).get_table_names(schema=MES)


def _have_col(bind) -> bool:
    return any(c["name"] == "version"
               for c in sa_inspect(bind).get_columns("plan_floor_state", schema=MES))


def _have_fk(bind) -> bool:
    return any(f["name"] == FK_USER
               for f in sa_inspect(bind).get_foreign_keys("floor_events", schema=MES))


def upgrade() -> None:
    bind = op.get_bind()
    if not _have_col(bind):
        op.add_column("plan_floor_state",
                      sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
                      schema=MES)
    if not _have_table(bind):
        from app.database import Base
        Base.metadata.create_all(bind=bind, tables=[_table_obj()])
    if not _have_fk(bind):
        op.create_foreign_key(
            FK_USER, "floor_events", "users", ["user_id"], ["id"],
            source_schema=MES, referent_schema="icb_costings", ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _have_table(bind):
        if _have_fk(bind):
            op.drop_constraint(FK_USER, "floor_events", type_="foreignkey", schema=MES)
        from app.database import Base
        Base.metadata.drop_all(bind=bind, tables=[_table_obj()])
    if _have_col(bind):
        op.drop_column("plan_floor_state", "version", schema=MES)
