"""Chassis-type pictures (Migration 0033).

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-03

Two additive columns, one feature in two stages (Michael, 3 Jul):
  • chassis_records.type_image — the picture a user picked manually on the chassis
    detail page (stage 1, live now). Stays as the per-chassis OVERRIDE later.
  • chassis_models.image_file — the catalog default per chassis type (stage 2, the
    planned auto-link: choosing a chassis type in the DDM dropdown attaches its
    picture automatically). Column lands now so the resolution order
    (record override → catalog default) is wired from day one.
Both store a bare filename under app/static/chassis-types/ (no paths).
Inspector-guarded; additive; up→down→up clean.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0033"
down_revision: Union[str, Sequence[str], None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MES = "icb_mes"


def _cols(bind, table: str) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns(table, schema=MES)}


def upgrade() -> None:
    bind = op.get_bind()
    if "type_image" not in _cols(bind, "chassis_records"):
        op.add_column("chassis_records", sa.Column("type_image", sa.String(128), nullable=True), schema=MES)
    if "image_file" not in _cols(bind, "chassis_models"):
        op.add_column("chassis_models", sa.Column("image_file", sa.String(128), nullable=True), schema=MES)


def downgrade() -> None:
    bind = op.get_bind()
    if "type_image" in _cols(bind, "chassis_records"):
        op.drop_column("chassis_records", "type_image", schema=MES)
    if "image_file" in _cols(bind, "chassis_models"):
        op.drop_column("chassis_models", "image_file", schema=MES)
