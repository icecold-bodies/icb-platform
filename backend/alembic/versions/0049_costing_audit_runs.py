"""Costing audit runs (Migration 0049).

Revision ID: 0049
Revises: 0048
Create Date: 2026-09-27

WO v1.59 costing audit admin (BA ruling 1, 27 Sep). An admin runs the Excel <-> MES
costing audit from Admin -> Costing audit; every run is recorded here so the history
survives restarts, is queryable, and "changed since the previous run" can compare two
runs of the same pack in the same environment. Files on the server are out: the service
runs under ProtectSystem=strict.

  icb_costings.costing_audit_runs  (NEW)
    - id                   INTEGER PK
    - started_at           TIMESTAMPTZ NOT NULL DEFAULT now()
    - finished_at          TIMESTAMPTZ               NULL while running
    - started_by_user_id   INTEGER FK -> users.id ondelete=SET NULL
    - started_by           VARCHAR(100) NOT NULL     username snapshot (house idiom)
    - pack                 VARCHAR(32)  NOT NULL     smoke | chillers | ... | all
    - environment          VARCHAR(8)   NOT NULL     'dev' | 'prod' (from the database name)
    - db_name              VARCHAR(100) NOT NULL     the database the run audited
    - accepted_list        VARCHAR(100) NOT NULL     accepted-differences file in use
    - golden_fingerprint   VARCHAR(64)               sha256 of the GRP workbook behind the golden
    - golden_generated_at  TIMESTAMPTZ               when that golden was generated
    - tolerance_pct        FLOAT        NOT NULL
    - status               VARCHAR(12)  NOT NULL     running | passed | flagged | failed
    - progress_done        INTEGER      NOT NULL DEFAULT 0   scenarios costed so far
    - progress_total       INTEGER      NOT NULL DEFAULT 0   (the page polls these; any
                                                             of the four workers may answer)
    - count_pass / count_flag / count_accepted / count_expired / count_unverifiable
                           INTEGER                   NULL until finished. count_flag is every
                                                     UNACCEPTED difference (FLAG + PRESENCE +
                                                     UNMAPPED + NO_GOLDEN); EXPIRED has its own.
    - report_json_gz       BYTEA                     gzip of the report JSON; the HTML and CSV
                                                     are rendered from it on request, never stored
    - error                TEXT                      why a run failed
    - ck_costing_audit_runs_status / _environment    CHECK the two enumerations
    - ix_costing_audit_runs_pack_env_started (pack, environment, started_at)
                           — "the previous run of this pack in this environment"
    - ix_costing_audit_runs_started (started_at) — the history list, newest first

Nothing else changes: no data written, no backfill. The permission key this feature adds
(admin.costing_audit) needs no migration — the boot-time _bootstrap_permissions seeds
catalogue keys. No retention cap (a run is small; see the PR for the size per run).

Inspector-guarded (table + indexes) -> idempotent on re-run; purely additive;
up->down->up round-trips clean (mirrors 0048).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0049"
down_revision: Union[str, Sequence[str], None] = "0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "costing_audit_runs"
IX_PACK_ENV_STARTED = "ix_costing_audit_runs_pack_env_started"
IX_STARTED = "ix_costing_audit_runs_started"


def _tables(bind) -> set:
    return set(sa_inspect(bind).get_table_names(schema=COST))


def _indexes(bind) -> set:
    if TABLE not in _tables(bind):
        return set()
    return {i["name"] for i in sa_inspect(bind).get_indexes(TABLE, schema=COST)}


def upgrade() -> None:
    bind = op.get_bind()

    if TABLE not in _tables(bind):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_by_user_id", sa.Integer(), nullable=True),
            sa.Column("started_by", sa.String(length=100), nullable=False),
            sa.Column("pack", sa.String(length=32), nullable=False),
            sa.Column("environment", sa.String(length=8), nullable=False),
            sa.Column("db_name", sa.String(length=100), nullable=False),
            sa.Column("accepted_list", sa.String(length=100), nullable=False),
            sa.Column("golden_fingerprint", sa.String(length=64), nullable=True),
            sa.Column("golden_generated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tolerance_pct", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=12), nullable=False),
            sa.Column("progress_done", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("count_pass", sa.Integer(), nullable=True),
            sa.Column("count_flag", sa.Integer(), nullable=True),
            sa.Column("count_accepted", sa.Integer(), nullable=True),
            sa.Column("count_expired", sa.Integer(), nullable=True),
            sa.Column("count_unverifiable", sa.Integer(), nullable=True),
            sa.Column("report_json_gz", sa.LargeBinary(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["started_by_user_id"], [f"{COST}.users.id"],
                name="fk_costing_audit_runs_started_by_user_id", ondelete="SET NULL"),
            sa.CheckConstraint(
                "status IN ('running', 'passed', 'flagged', 'failed')",
                name="ck_costing_audit_runs_status"),
            sa.CheckConstraint(
                "environment IN ('dev', 'prod')",
                name="ck_costing_audit_runs_environment"),
            schema=COST,
        )

    existing = _indexes(bind)
    if IX_PACK_ENV_STARTED not in existing:
        op.create_index(IX_PACK_ENV_STARTED, TABLE, ["pack", "environment", "started_at"],
                        schema=COST)
    if IX_STARTED not in existing:
        op.create_index(IX_STARTED, TABLE, ["started_at"], schema=COST)


def downgrade() -> None:
    bind = op.get_bind()
    existing = _indexes(bind)
    if IX_STARTED in existing:
        op.drop_index(IX_STARTED, table_name=TABLE, schema=COST)
    if IX_PACK_ENV_STARTED in existing:
        op.drop_index(IX_PACK_ENV_STARTED, table_name=TABLE, schema=COST)
    if TABLE in _tables(bind):
        op.drop_table(TABLE, schema=COST)
