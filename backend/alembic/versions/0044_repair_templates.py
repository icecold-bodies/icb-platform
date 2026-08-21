"""Reusable repair templates (Migration 0044).

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-22

WO v1.50 P3 (Lezette, 22 Aug). The same repair usually needs the same familiar
bundle of lines (GLUE, RIVETS, LABOUR ...). This adds the two tables that let a
repair estimator save such a bundle once and reuse it: a template header and its
lines. Ratified shape:

  * SHARED TEAM-WIDE — any estimator may use one; create/edit/retire is gated by
    the costings.repair_templates_manage catalogue key ({admin, full}), enforced
    in the router, not here.
  * SOFT-RETIRE, never hard delete — retired_at NULL = active. The list filters
    on it on every read, so it is indexed (mirrors 0043's deleted_at reasoning).
  * NO PRICES STORED, by design. A template stores the ITEM LIST and DEFAULT
    QUANTITIES only; prices resolve LIVE from the materials master at the moment
    of use, so a template can never quote a stale price.

  icb_costings.repair_templates  (NEW)
    - id           INTEGER PK
    - name         VARCHAR(200) NOT NULL
    - description  TEXT
    - created_at / created_by, updated_at / updated_by — the *_by columns are
      username SNAPSHOTS (house audit idiom, feedback-audit-denormalize-name-
      snapshot): who made a template must survive that user being renamed.
    - retired_at   TIMESTAMPTZ  NULL = active (indexed)
    - retired_by   VARCHAR(120)

  icb_costings.repair_template_lines  (NEW)
    - id           INTEGER PK
    - template_id  INTEGER NOT NULL FK -> icb_costings.repair_templates.id
                   ondelete=CASCADE (a line is meaningless without its template;
                   templates themselves are only ever soft-retired, so the
                   cascade exists for hygiene, not for a workflow)
    - sort_order   INTEGER NOT NULL DEFAULT 0
    - kind         VARCHAR(16) NOT NULL DEFAULT 'free_hand'  ('stock'|'free_hand')
    - material_id  INTEGER FK -> icb_costings.materials.id ondelete=SET NULL —
                   a stock line's material reference; on a free_hand line it is
                   provenance metadata from a body-category pull, used to offer
                   a live list price at use time. SET NULL so a removed material
                   degrades the line to description-only instead of losing it.
    - description  VARCHAR(200) NOT NULL — display snapshot / free-hand identity
    - qty          FLOAT — the DEFAULT quantity (editable at use)
    - unit         VARCHAR(32)
    - notes        TEXT
    - origin       VARCHAR(200) — the body-category chip (e.g. "SIDES")

Inspector-guarded (tables + index + FKs) -> idempotent on re-run; purely
additive; up->down->up round-trips clean (mirrors 0040/0043).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0044"
down_revision: Union[str, Sequence[str], None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
T_TPL = "repair_templates"
T_LINE = "repair_template_lines"
IX_RETIRED = "ix_repair_templates_retired_at"
IX_LINE_TPL = "ix_repair_template_lines_template"


def _tables(bind) -> set:
    return set(sa_inspect(bind).get_table_names(schema=COST))


def _indexes(bind, table: str) -> set:
    if table not in _tables(bind):
        return set()
    return {i["name"] for i in sa_inspect(bind).get_indexes(table, schema=COST)}


def upgrade() -> None:
    bind = op.get_bind()

    if T_TPL not in _tables(bind):
        op.create_table(
            T_TPL,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True,
                      server_default=sa.text("now()")),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_by", sa.String(length=120), nullable=True),
            sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("retired_by", sa.String(length=120), nullable=True),
            schema=COST,
        )
    if IX_RETIRED not in _indexes(bind, T_TPL):
        op.create_index(IX_RETIRED, T_TPL, ["retired_at"], schema=COST)

    if T_LINE not in _tables(bind):
        op.create_table(
            T_LINE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("template_id", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False,
                      server_default=sa.text("0")),
            sa.Column("kind", sa.String(length=16), nullable=False,
                      server_default=sa.text("'free_hand'")),
            sa.Column("material_id", sa.Integer(), nullable=True),
            sa.Column("description", sa.String(length=200), nullable=False),
            sa.Column("qty", sa.Float(), nullable=True),
            sa.Column("unit", sa.String(length=32), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("origin", sa.String(length=200), nullable=True),
            sa.ForeignKeyConstraint(
                ["template_id"], [f"{COST}.{T_TPL}.id"],
                name="fk_repair_template_lines_template_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["material_id"], [f"{COST}.materials.id"],
                name="fk_repair_template_lines_material_id",
                ondelete="SET NULL",
            ),
            schema=COST,
        )
    if IX_LINE_TPL not in _indexes(bind, T_LINE):
        op.create_index(IX_LINE_TPL, T_LINE, ["template_id"], schema=COST)


def downgrade() -> None:
    bind = op.get_bind()
    if T_LINE in _tables(bind):
        if IX_LINE_TPL in _indexes(bind, T_LINE):
            op.drop_index(IX_LINE_TPL, table_name=T_LINE, schema=COST)
        op.drop_table(T_LINE, schema=COST)
    if T_TPL in _tables(bind):
        if IX_RETIRED in _indexes(bind, T_TPL):
            op.drop_index(IX_RETIRED, table_name=T_TPL, schema=COST)
        op.drop_table(T_TPL, schema=COST)
