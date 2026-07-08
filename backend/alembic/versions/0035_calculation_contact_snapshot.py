"""Customer-contacts in costings — calculations contact snapshot (Migration 0035).

Revision ID: 0035
Revises: 0034
Create Date: 2026-07-08

Nadie picks a contact person when quoting (WO v4.34.1 §0.6 infra — this WO adds the
quote-flow UX). The costing row gets the selected contact as a DENORMALIZED WRITE-TIME
SNAPSHOT (mirrors ADR 0016 deprecate-not-drop + the chassis_records edited_by_name
pattern): if the contact is later renamed/re-emailed/soft-deleted, the quote keeps the
values that were true when it was sent.

  icb_costings.calculations gains (all NULLABLE — additive, old rows unaffected):
    - contact_id         INTEGER, FK → icb_costings.customer_contacts.id,
                         ondelete=SET NULL (a contact hard-delete must never
                         cascade-remove a quote's history; the snapshot columns
                         below keep the display values regardless)
    - contact_name       VARCHAR(200)   — snapshot at quote-save time
    - contact_email      VARCHAR(300)
    - contact_telephone  VARCHAR(100)
    - contact_role       VARCHAR(100)

Inspector-guarded (columns + FK) → idempotent on re-run; purely additive ALTER;
up→down→up round-trips clean (mirrors the proven 0026/0031/0034 pattern).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0035"
down_revision: Union[str, Sequence[str], None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
FK_CONTACT = "fk_calculations_contact_id_customer_contacts"

_SNAPSHOT_COLS = (
    ("contact_name", sa.String(length=200)),
    ("contact_email", sa.String(length=300)),
    ("contact_telephone", sa.String(length=100)),
    ("contact_role", sa.String(length=100)),
)


def _cols(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns("calculations", schema=COST)}


def _fks(bind) -> set:
    return {f["name"] for f in sa_inspect(bind).get_foreign_keys("calculations", schema=COST)}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _cols(bind)
    if "contact_id" not in cols:
        op.add_column("calculations",
                      sa.Column("contact_id", sa.Integer(), nullable=True), schema=COST)
    for name, coltype in _SNAPSHOT_COLS:
        if name not in cols:
            op.add_column("calculations", sa.Column(name, coltype, nullable=True), schema=COST)
    if FK_CONTACT not in _fks(bind):
        op.create_foreign_key(
            FK_CONTACT, "calculations", "customer_contacts",
            ["contact_id"], ["id"],
            source_schema=COST, referent_schema=COST,
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if FK_CONTACT in _fks(bind):
        op.drop_constraint(FK_CONTACT, "calculations", type_="foreignkey", schema=COST)
    cols = _cols(bind)
    for name, _ in reversed(_SNAPSHOT_COLS):
        if name in cols:
            op.drop_column("calculations", name, schema=COST)
    if "contact_id" in cols:
        op.drop_column("calculations", "contact_id", schema=COST)
