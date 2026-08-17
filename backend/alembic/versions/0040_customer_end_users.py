"""End user (the customer's customer) — table + costing snapshot (Migration 0040).

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-17

WO v1.47 lane B (Nadie, 17 Aug). ICB's customer is often a reseller or middleman —
the body is actually FOR someone else. The MES captured only customer + contact, so
the END USER never reached the quote documents and Nadie re-typed it in Outlook.

This migration is the exact twin of 0035 (customer-contacts in costings), one level
out: a per-customer end-user book, plus a write-time SNAPSHOT of the selected row on
the costing.

  icb_costings.customer_end_users  (NEW)
    - id                 INTEGER PK
    - customer_id        INTEGER NOT NULL, FK -> icb_costings.customers.id
                         ondelete=CASCADE (an end-user row is meaningless without
                         its customer; the costing keeps its own snapshot, so no
                         quote history is lost when a customer is hard-deleted)
    - company_name       VARCHAR(200) NOT NULL — the end-user COMPANY (required)
    - contact_name       VARCHAR(200) — and its contact PERSON (Nadie's "table that
    - contact_email      VARCHAR(300)   contains the end user and the contact
    - contact_telephone  VARCHAR(100)   person" — one row is the pair)
    - contact_role       VARCHAR(100)
    - notes              TEXT
    - is_primary         BOOLEAN NOT NULL DEFAULT FALSE
    - active             BOOLEAN NOT NULL DEFAULT TRUE — soft-delete only
    - created_at/created_by/updated_at/updated_by

  Partial unique index uq_customer_end_users_one_primary: one primary per customer,
  mirroring uq_customer_contacts_one_primary (migration 0022). Inactive rows still
  occupy the slot while primary, so the soft-delete path clears is_primary too —
  same discipline as delete_contact().

  icb_costings.calculations gains (all NULLABLE — additive, old rows unaffected):
    - end_user_id             INTEGER, FK -> icb_costings.customer_end_users.id,
                              ondelete=SET NULL (a hard delete must never cascade
                              away a quote; the snapshot columns below keep the
                              display values regardless — ADR 0034's reasoning)
    - end_user_company        VARCHAR(200)  — snapshot at quote-save time
    - end_user_contact_name   VARCHAR(200)
    - end_user_contact_email  VARCHAR(300)
    - end_user_contact_telephone VARCHAR(100)
    - end_user_contact_role   VARCHAR(100)

The contact snapshot's own columns are NOT touched: this sits beside it.

Inspector-guarded (table + index + columns + FK) -> idempotent on re-run; purely
additive; up->down->up round-trips clean (mirrors 0026/0031/0034/0035/0039).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0040"
down_revision: Union[str, Sequence[str], None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "customer_end_users"
IX_CUSTOMER = "ix_customer_end_users_customer"
UQ_ONE_PRIMARY = "uq_customer_end_users_one_primary"
FK_END_USER = "fk_calculations_end_user_id_customer_end_users"

_SNAPSHOT_COLS = (
    ("end_user_company", sa.String(length=200)),
    ("end_user_contact_name", sa.String(length=200)),
    ("end_user_contact_email", sa.String(length=300)),
    ("end_user_contact_telephone", sa.String(length=100)),
    ("end_user_contact_role", sa.String(length=100)),
)


def _tables(bind) -> set:
    return set(sa_inspect(bind).get_table_names(schema=COST))


def _indexes(bind) -> set:
    if TABLE not in _tables(bind):
        return set()
    return {i["name"] for i in sa_inspect(bind).get_indexes(TABLE, schema=COST)}


def _calc_cols(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns("calculations", schema=COST)}


def _calc_fks(bind) -> set:
    return {f["name"] for f in sa_inspect(bind).get_foreign_keys("calculations", schema=COST)}


def upgrade() -> None:
    bind = op.get_bind()

    if TABLE not in _tables(bind):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("company_name", sa.String(length=200), nullable=False),
            sa.Column("contact_name", sa.String(length=200), nullable=True),
            sa.Column("contact_email", sa.String(length=300), nullable=True),
            sa.Column("contact_telephone", sa.String(length=100), nullable=True),
            sa.Column("contact_role", sa.String(length=100), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=False,
                      server_default=sa.text("false")),
            sa.Column("active", sa.Boolean(), nullable=False,
                      server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), nullable=True,
                      server_default=sa.text("now()")),
            sa.Column("created_by", sa.String(length=128), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True,
                      server_default=sa.text("now()")),
            sa.Column("updated_by", sa.String(length=128), nullable=True),
            sa.ForeignKeyConstraint(
                ["customer_id"], [f"{COST}.customers.id"],
                name="fk_customer_end_users_customer_id",
                ondelete="CASCADE",
            ),
            schema=COST,
        )

    existing = _indexes(bind)
    if IX_CUSTOMER not in existing:
        op.create_index(IX_CUSTOMER, TABLE, ["customer_id"], schema=COST)
    # One primary end user per customer (partial — mirrors customer_contacts).
    if UQ_ONE_PRIMARY not in existing:
        op.create_index(UQ_ONE_PRIMARY, TABLE, ["customer_id"], unique=True,
                        schema=COST, postgresql_where=sa.text("is_primary"))

    cols = _calc_cols(bind)
    if "end_user_id" not in cols:
        op.add_column("calculations",
                      sa.Column("end_user_id", sa.Integer(), nullable=True), schema=COST)
    for name, coltype in _SNAPSHOT_COLS:
        if name not in cols:
            op.add_column("calculations", sa.Column(name, coltype, nullable=True), schema=COST)
    if FK_END_USER not in _calc_fks(bind):
        op.create_foreign_key(
            FK_END_USER, "calculations", TABLE,
            ["end_user_id"], ["id"],
            source_schema=COST, referent_schema=COST,
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Drop the calculations-side FK first — the table it points at goes below.
    if FK_END_USER in _calc_fks(bind):
        op.drop_constraint(FK_END_USER, "calculations", type_="foreignkey", schema=COST)
    cols = _calc_cols(bind)
    for name, _ in reversed(_SNAPSHOT_COLS):
        if name in cols:
            op.drop_column("calculations", name, schema=COST)
    if "end_user_id" in cols:
        op.drop_column("calculations", "end_user_id", schema=COST)

    existing = _indexes(bind)
    if UQ_ONE_PRIMARY in existing:
        op.drop_index(UQ_ONE_PRIMARY, table_name=TABLE, schema=COST)
    if IX_CUSTOMER in existing:
        op.drop_index(IX_CUSTOMER, table_name=TABLE, schema=COST)
    if TABLE in _tables(bind):
        op.drop_table(TABLE, schema=COST)
