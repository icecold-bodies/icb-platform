"""Validated references — Nadie's balanced-with-Excel costings (Migration 0039).

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-10

WO v1.45 "Validated references" (Nadie, ratified by Michael). When a costing
balances with her Excel (or is approved) she marks it as a VALIDATED REFERENCE
with a friendly label. Later she recalls it as a starting point, and whenever a
LIVE costing exactly matches a reference's configuration but the manufacturing
cost has drifted beyond tolerance, the app warns her.

Design principle (BA-ratified): a THIN LAYER over saved costings. The costing
record already stores dims, body options, overrides and category totals inside
result_json.input_state (v1.39.9), so this table stores a POINTER + label +
fingerprint — never a copy of the costing data.

  icb_costings.validated_references
    - id                 INTEGER PK
    - calculation_id     INTEGER NOT NULL, FK -> icb_costings.calculations.id
                         ondelete=CASCADE (a reference is meaningless without
                         the costing it points at; there is no copied data to
                         orphan, unlike the contact snapshot of 0035)
    - label              VARCHAR(120) NOT NULL — Nadie's friendly name
    - config_fingerprint VARCHAR(64)  NOT NULL — sha256 hex, INDEXED (the
                         exact-match key; see services/validated_references.py
                         for the one canonicalisation used by write AND match)
    - trailer_type_id    INTEGER NOT NULL, FK -> icb_costings.trailer_types.id
                         (denormalised from the calculation so the recall
                         dropdown filters by body type with no join)
    - created_by         VARCHAR(100) — display-name snapshot at write time
                         (ADR 0016 / chassis_records.edited_by_name pattern)
    - created_at         TIMESTAMP
    - active             BOOLEAN NOT NULL DEFAULT TRUE — SOFT retire only.
                         Retired references stop matching and leave the
                         dropdown; the row is never hard-deleted.

  Partial unique index uq_validated_refs_active_calc: one ACTIVE reference per
  costing. Re-marking the same costing is a no-op instead of a silent duplicate;
  retiring frees the slot so it can be re-marked later.

NAMING: deliberately distinct from the unrelated admin-level "BOM Snapshots"
feature (icb_costings.bom_snapshots, routers/bom_snapshots.py) — no shared
table names, routes or UI wording.

Also seeds the admin-tunable drift tolerance into the existing generic
icb_costings.admin_settings key/value store (2% ratified default):

    costings.validated_ref_tolerance_pct = '2'

Stored there rather than in global_variables because global_variables rows are
injected into the formula-evaluation namespace and echoed into every saved
result_json's debug block — a UI tuning knob does not belong in the pricing
engine's variable space. Admin still tunes it without code, via
GET/PUT /api/validated-references/settings.

Inspector-guarded (table + index + setting row) → idempotent on re-run;
up->down->up round-trips clean (mirrors the proven 0026/0031/0034/0035 pattern).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "0039"
down_revision: Union[str, Sequence[str], None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
TABLE = "validated_references"
IX_FINGERPRINT = "ix_validated_refs_fingerprint"
IX_TRAILER_ACTIVE = "ix_validated_refs_trailer_active"
UQ_ACTIVE_CALC = "uq_validated_refs_active_calc"

TOLERANCE_KEY = "costings.validated_ref_tolerance_pct"
TOLERANCE_DEFAULT = "2"


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
            sa.Column("calculation_id", sa.Integer(), nullable=False),
            sa.Column("label", sa.String(length=120), nullable=False),
            sa.Column("config_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("trailer_type_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True,
                      server_default=sa.text("now()")),
            sa.Column("active", sa.Boolean(), nullable=False,
                      server_default=sa.text("true")),
            sa.ForeignKeyConstraint(
                ["calculation_id"], [f"{COST}.calculations.id"],
                name="fk_validated_refs_calculation_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["trailer_type_id"], [f"{COST}.trailer_types.id"],
                name="fk_validated_refs_trailer_type_id",
            ),
            schema=COST,
        )

    existing = _indexes(bind)
    # Match path: fingerprint lookups are the hot read (every recompute).
    if IX_FINGERPRINT not in existing:
        op.create_index(IX_FINGERPRINT, TABLE, ["config_fingerprint"], schema=COST)
    # Recall dropdown: active references for the selected body type.
    if IX_TRAILER_ACTIVE not in existing:
        op.create_index(IX_TRAILER_ACTIVE, TABLE, ["trailer_type_id", "active"],
                        schema=COST)
    # One ACTIVE reference per costing (partial — retired rows are unconstrained).
    if UQ_ACTIVE_CALC not in existing:
        op.create_index(UQ_ACTIVE_CALC, TABLE, ["calculation_id"], unique=True,
                        schema=COST, postgresql_where=sa.text("active"))

    # Seed the admin-tunable tolerance (idempotent; never overwrites a tuned value).
    op.execute(
        sa.text(
            f"INSERT INTO {COST}.admin_settings (key, value) "
            "VALUES (:k, :v) ON CONFLICT (key) DO NOTHING"
        ).bindparams(k=TOLERANCE_KEY, v=TOLERANCE_DEFAULT)
    )


def downgrade() -> None:
    bind = op.get_bind()

    # Only remove the setting while it still holds the untouched seeded default —
    # a value Michael has tuned through the admin surface is never discarded
    # (the 0038 guarded-data-migration precedent).
    op.execute(
        sa.text(
            f"DELETE FROM {COST}.admin_settings WHERE key = :k AND value = :v"
        ).bindparams(k=TOLERANCE_KEY, v=TOLERANCE_DEFAULT)
    )

    existing = _indexes(bind)
    for name in (UQ_ACTIVE_CALC, IX_TRAILER_ACTIVE, IX_FINGERPRINT):
        if name in existing:
            op.drop_index(name, table_name=TABLE, schema=COST)
    if TABLE in _tables(bind):
        op.drop_table(TABLE, schema=COST)
