"""Customer VAT number (Migration 0041).

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-17

WO v1.47 Lane D (the ICB repair-quotation document, addendum D8). The ICB
letterhead prints the CUSTOMER's VAT number in the header block — the sample
quote shows it as "Vat Num - Partner  477 026 7526".

The costing system has never held it: `icb_costings.customers` carries
bp_code / name / email / telephone / is_active / is_dealer and nothing else.
D8 ratified adding it to the CUSTOMER RECORD rather than re-typing it on every
quote, which is right — a VAT number belongs to the company, not to one quote,
and typing it per quote would guarantee drift between two quotes for the same
customer.

  icb_costings.customers gains (NULLABLE — additive, every existing row is
  unaffected and simply prints nothing until someone fills it in):
    - vat_number  VARCHAR(50)

Deliberately NOT validated as a SARS VAT number here: ICB quotes cross-border
customers too (the sample's own terms carry four cross-border clauses), so the
field has to hold whatever the customer's jurisdiction issues. It is a display
string on a document, not a computed input.

No snapshot column on `calculations`: unlike the contact (0035) and the end user
(0040), the VAT number is not a chosen ROW that can be re-pointed or deleted —
it is a single attribute of the customer already linked to the costing, and the
document renders the customer's current one. If quote-history freezing is ever
wanted for it, that is a separate change with its own ratification.

Inspector-guarded -> idempotent on re-run; purely additive; up->down->up
round-trips clean (mirrors 0035/0039/0040).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0041"
down_revision: Union[str, Sequence[str], None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "customers"
COLUMN = "vat_number"


def _customer_cols(bind) -> set:
    return {c["name"] for c in sa_inspect(bind).get_columns(TABLE, schema=COST)}


def upgrade() -> None:
    bind = op.get_bind()
    if COLUMN not in _customer_cols(bind):
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=50), nullable=True),
                      schema=COST)


def downgrade() -> None:
    bind = op.get_bind()
    if COLUMN in _customer_cols(bind):
        op.drop_column(TABLE, COLUMN, schema=COST)
