"""v1.51 — normalise baked-in 4G PU foam prices back to 32D (Migration 0046).

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-25

WO v1.51 (Michael, 25 Aug). Burt hand-edited his workbook to switch a body
between 32D PU FOAM and the better-insulating 4G FOAM, and that manual process
left the grade FROZEN INTO the stored unit price of some categories. The MES
replaces it with one explicit per-costing selection, which requires every PU
line to store the 32D price and derive 4G from it (x 5875/4310 = 1.36311) at
calculation time. This migration moves the baked-4G rows down onto their 32D
value so the toggle has a correct pair to swing between.

How a row is classified
-----------------------
Every PU price in the workbook is `sheet_price x (1.22*2.44 / 2.98) x thickness`,
so dividing a row's stored unit price by its linked insulation thickness yields a
RATE that identifies the grade outright:

    32D            4310 * 2.9768 / 2.98 = 4305.3718
    4G             5875 * 2.9768 / 2.98 = 5868.6913
    4G, 2.99 typo  5875 * 2.9768 / 2.99 = 5849.0635   (Burt's Meat Body front row)
    32D, 2.99 typo 4310 * 2.9768 / 2.99 = 4290.9726

The tolerance is 0.1%: observed data sits within 0.002% of its rate, while the
CLOSEST pair of classes (4G vs the 2.99 typo) is 0.335% apart — so the band both
absorbs the real rounding and cannot confuse two grades.

What is rewritten, and what is not
----------------------------------
ONLY rows that classify as 4G. A 4G row is divided by the exact price ratio
(the 2.99 typo is corrected on the way, per the ratified default that the MES
normalisation supersedes Burt's typo rather than replicating it). Everything
else is left byte-identical:

  * rows already on 32D — nothing to do;
  * rows with no unit_price_override — they read the SHARED per-section material
    price, which is common to every body; rewriting it would silently reprice
    categories this lane never classified;
  * rows with no linked insulation thickness — unclassifiable, untouched;
  * rows whose rate matches NOTHING — untouched and reported. On the dev data
    that is RHINORANGE TRAILER, whose five rows agree on a coherent internal rate
    of 6373.80 that is derived from neither sheet price. Guard: a default never
    overwrites a decision, and an unrecognised number is not ours to reinterpret.

This is NOT the August price update. A stale 32D price stays stale; only the
GRADE is normalised, so relative 32D/4G pricing is exact either way.

Reversibility
-------------
Every rewrite is journalled into `icb_costings.pu_foam_normalisation` (bom_id,
old/new price, classification, context). downgrade() replays the old prices back
and drops the table, so up -> down -> up is exact. The journal doubles as the
BEFORE/AFTER audit table published in docs/audit/.

Also seeds `admin_settings['costings.pu_foam_4g_factor']` with the price-list
ratio, guarded so it never clobbers a value someone has set — when Burt's next
price list moves BOTH sheet prices, that one row is the thing to update.
"""
from typing import Sequence, Union
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect


revision: str = "0046"
down_revision: Union[str, Sequence[str], None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST = "icb_costings"
T_JOURNAL = "pu_foam_normalisation"

SHEET_32D = 4310.0
SHEET_4G = 5875.0
SHEET_AREA = 1.22 * 2.44          # 2.9768 m2 — one PU sheet
DIVISOR = 2.98                    # Burt's divisor
DIVISOR_TYPO = 2.99               # the Meat Body sheet's typo

RATIO_4G = SHEET_4G / SHEET_32D   # 1.3631090487238979

RATE_32D = SHEET_32D * SHEET_AREA / DIVISOR
RATE_4G = SHEET_4G * SHEET_AREA / DIVISOR
RATE_32D_TYPO = SHEET_32D * SHEET_AREA / DIVISOR_TYPO
RATE_4G_TYPO = SHEET_4G * SHEET_AREA / DIVISOR_TYPO

TOLERANCE = 0.001                 # 0.1% — see the module docstring

FACTOR_KEY = "costings.pu_foam_4g_factor"
FACTOR_SEED = repr(RATIO_4G)

#: The section-level PU foam cost lines. Exact names only: "PU INJECTION" is a
#: different product and "FRONT PU"/"SIDES PU"/... are the EPS-vs-PU toggles.
PU_NAMES = ("PU", "PU FOAM")

log = logging.getLogger("alembic.runtime.migration")


# ── shape helpers ────────────────────────────────────────────────────────────

def _tables(bind) -> set:
    return set(sa_inspect(bind).get_table_names(schema=COST))


# The PU cost rows, each with the insulation thickness its linked toggle carries.
_SCAN_SQL = f"""
    SELECT b.id                                   AS bom_id,
           t.name                                 AS trailer_name,
           t.is_active                            AS trailer_active,
           COALESCE(b.bom_section, mc.name, '')   AS section,
           b.unit_price_override                  AS override,
           (SELECT bo.variable_value
              FROM {COST}.bill_of_materials bo
             WHERE bo.trailer_type_id = b.trailer_type_id
               AND bo.is_body_option
               AND bo.body_option_subgroup = 'INSULATION'
               AND bo.material_id = b.body_option_linked_id
             LIMIT 1)                             AS thickness
      FROM {COST}.bill_of_materials b
      JOIN {COST}.materials m           ON m.id = b.material_id
      LEFT JOIN {COST}.material_categories mc ON mc.id = m.category_id
      LEFT JOIN {COST}.trailer_types t  ON t.id = b.trailer_type_id
     WHERE UPPER(BTRIM(m.name)) IN :pu_names
       AND COALESCE(b.is_body_option, FALSE) = FALSE
     ORDER BY t.name, COALESCE(b.bom_section, mc.name, '')
"""


def _classify(override, thickness):
    """(classification, new_price). new_price is None when nothing is rewritten."""
    if override is None:
        # Reads the shared per-section material price — common to every body.
        return "SHARED-DEFAULT", None
    if not thickness:
        return "NO-THICKNESS", None
    rate = float(override) / float(thickness)
    for name, ref in (("32D", RATE_32D),
                      ("4G", RATE_4G),
                      ("32D~2.99", RATE_32D_TYPO),
                      ("4G~2.99", RATE_4G_TYPO)):
        if abs(rate / ref - 1.0) <= TOLERANCE:
            if name == "4G":
                return name, float(override) / RATIO_4G
            if name == "4G~2.99":
                # Correct the divisor typo on the way down, so the row lands on
                # the same 32D value its correctly-typed siblings hold.
                return name, float(override) * (DIVISOR_TYPO / DIVISOR) / RATIO_4G
            return name, None      # already 32D (typo or not) — leave the price
    return "UNCLASSIFIED", None


# ── upgrade ──────────────────────────────────────────────────────────────────

def upgrade() -> None:
    bind = op.get_bind()

    if T_JOURNAL not in _tables(bind):
        op.create_table(
            T_JOURNAL,
            sa.Column("bom_id", sa.Integer(), primary_key=True),
            sa.Column("trailer_name", sa.String(length=200), nullable=True),
            sa.Column("bom_section", sa.String(length=100), nullable=True),
            sa.Column("thickness_m", sa.Float(), nullable=True),
            sa.Column("old_price", sa.Float(), nullable=False),
            sa.Column("new_price", sa.Float(), nullable=False),
            sa.Column("classification", sa.String(length=32), nullable=False),
            sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True,
                      server_default=sa.text("now()")),
            schema=COST,
        )

    # Admin-tunable ratio. Guarded: seed only when the key is absent, so a value
    # someone has set is never overwritten (the 0045 rule).
    bind.execute(
        sa.text(f"""
            INSERT INTO {COST}.admin_settings (key, value, updated_at)
            SELECT :k, :v, now()
             WHERE NOT EXISTS (SELECT 1 FROM {COST}.admin_settings WHERE key = :k)
        """),
        {"k": FACTOR_KEY, "v": FACTOR_SEED},
    )

    if "bill_of_materials" not in _tables(bind):
        return

    rows = bind.execute(
        sa.text(_SCAN_SQL).bindparams(sa.bindparam("pu_names", expanding=True)),
        {"pu_names": list(PU_NAMES)},
    ).mappings().all()

    tally: dict[str, int] = {}
    rewrites, unclassified = [], []
    for r in rows:
        kind, new_price = _classify(r["override"], r["thickness"])
        tally[kind] = tally.get(kind, 0) + 1
        if kind == "UNCLASSIFIED":
            unclassified.append(r)
        if new_price is None:
            continue
        rewrites.append({
            "bom_id": r["bom_id"],
            "trailer_name": r["trailer_name"],
            "bom_section": r["section"],
            "thickness_m": float(r["thickness"]),
            "old_price": float(r["override"]),
            "new_price": round(new_price, 6),
            "classification": kind,
        })

    log.info("0046 PU foam: scanned %d PU cost rows — %s", len(rows),
             ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))

    for r in unclassified:
        log.warning(
            "0046 PU foam: UNCLASSIFIED, left untouched — bom_id=%s %s / %s "
            "price=%.4f thickness=%.4f rate=%.2f (32D=%.2f, 4G=%.2f)",
            r["bom_id"], r["trailer_name"], r["section"], float(r["override"]),
            float(r["thickness"] or 0),
            float(r["override"]) / float(r["thickness"]) if r["thickness"] else 0.0,
            RATE_32D, RATE_4G,
        )

    for r in rewrites:
        log.info("0046 PU foam: %s -> 32D  bom_id=%s %s / %s  %.4f -> %.4f",
                 r["classification"], r["bom_id"], r["trailer_name"],
                 r["bom_section"], r["old_price"], r["new_price"])
        bind.execute(
            sa.text(f"UPDATE {COST}.bill_of_materials "
                    f"SET unit_price_override = :p WHERE id = :i"),
            {"p": r["new_price"], "i": r["bom_id"]},
        )
        # Journalled so downgrade is exact. ON CONFLICT keeps the ORIGINAL
        # old_price if this ever runs twice against a part-applied database.
        bind.execute(
            sa.text(f"""
                INSERT INTO {COST}.{T_JOURNAL}
                       (bom_id, trailer_name, bom_section, thickness_m,
                        old_price, new_price, classification, applied_at)
                VALUES (:bom_id, :trailer_name, :bom_section, :thickness_m,
                        :old_price, :new_price, :classification, now())
                ON CONFLICT (bom_id) DO NOTHING
            """),
            r,
        )

    log.info("0046 PU foam: rewrote %d row(s); %d unclassified left untouched",
             len(rewrites), len(unclassified))


# ── downgrade ────────────────────────────────────────────────────────────────

def downgrade() -> None:
    bind = op.get_bind()

    if T_JOURNAL in _tables(bind):
        restored = bind.execute(sa.text(f"""
            UPDATE {COST}.bill_of_materials b
               SET unit_price_override = j.old_price
              FROM {COST}.{T_JOURNAL} j
             WHERE b.id = j.bom_id
        """)).rowcount
        log.info("0046 PU foam downgrade: restored %s row(s)", restored)
        op.drop_table(T_JOURNAL, schema=COST)

    # Remove the seed only while it still holds the exact seeded value.
    bind.execute(
        sa.text(f"DELETE FROM {COST}.admin_settings "
                f"WHERE key = :k AND value = :v"),
        {"k": FACTOR_KEY, "v": FACTOR_SEED},
    )
