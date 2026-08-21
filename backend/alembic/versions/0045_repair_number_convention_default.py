"""v1.50 — move the repair series' DEFAULT template to the ratified convention.

Michael, 22 Aug 2026: the repair naming convention is
`R-number + customer + vehicle registration`, and it must be the DEFAULT, not
an opt-in.

Why a migration is needed at all
--------------------------------
Flipping `DEFAULT_TEMPLATES[SERIES_REPAIR_DOC]` in `app/quote_numbering.py`
only governs a counter row that does not exist yet. Migration 0042 SEEDS the
`repair_doc` row with a hard-coded `"R-{counter}"`, so every database that has
run 0042 — dev, prod, CI, icb_test — already holds that string and would never
see the new default. The code change alone would silently do nothing on every
existing installation.

Why it is guarded
-----------------
`format_template` is an ADMIN-OWNED setting: the whole point of the v1.50
Quote Numbering screen is that someone can set it. So this only moves rows
still holding the exact untouched 0042 seed. A template anyone has customised
— including one already carrying the convention — is left alone. Moving the
default forward must never overwrite a decision somebody made.

Already-issued numbers are untouched by construction: they are frozen into
each costing's `result_json.repair_document_number` and are never re-derived
from the counter.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0045"
down_revision: Union[str, Sequence[str], None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
REPAIR_SERIES = "repair_doc"
OLD_TEMPLATE = "R-{counter}"
NEW_TEMPLATE = "R-{counter} {customer} {vehicle_registration}"


def _move(from_tpl: str, to_tpl: str) -> None:
    """Rewrite the repair series' template, but ONLY where it still holds
    `from_tpl` — never clobber a customised one."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("quote_counter", schema=COST):
        return                      # nothing seeded yet; the code default applies
    bind.execute(
        sa.text(f"""
            UPDATE {COST}.quote_counter
               SET format_template = :to_tpl
             WHERE series = :series
               AND format_template = :from_tpl
        """),
        {"to_tpl": to_tpl, "from_tpl": from_tpl, "series": REPAIR_SERIES},
    )


def upgrade() -> None:
    _move(OLD_TEMPLATE, NEW_TEMPLATE)


def downgrade() -> None:
    # Symmetric and equally guarded: only a row still holding the exact new
    # default goes back, so an admin who has since edited it keeps their value.
    _move(NEW_TEMPLATE, OLD_TEMPLATE)
