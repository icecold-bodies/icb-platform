"""PU insulation foam type — 32D PU FOAM (default) vs 4G FOAM.  (v1.51)

Burt hand-edited his workbook to switch a body between the two PU grades, which
is how single bodies ended up with mixed pricing (Meat Body and Explosive 4.9-up
each carried one row still on the 32D cell; the Meat Body front row also divided
by 2.99 instead of 2.98).  The MES replaces that with ONE explicit selection per
costing, under BODY OPTIONS — every PU-consuming line follows it.

Burt's price list prices a 1.22 x 2.44 PU sheet at R4310 for 32D PU FOAM
(cell C17) and R5875 for 4G FOAM (cell C19), and both divide by the same 2.98.
The grade therefore scales a row's unit price by exactly 5875/4310 = 1.36311 —
independent of the row's thickness, location or body category.

The MES stores ONE price per PU line — the 32D one, after migration 0046 — and
DERIVES the 4G price from it at calculation time.  Deriving rather than storing
a second number is what keeps the pair exact when Burt's next price list moves
the 32D side: this lane is deliberately not the August price update, so a stored
4G number would silently go stale against its own 32D sibling.

Nothing here touches weight, thickness or any derived value: foam grade is a
price-only choice.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..database import AdminSetting

# ── The two grades ───────────────────────────────────────────────────────────
FOAM_32D = "32D"
FOAM_4G = "4G"

#: Material names exactly as Burt's price list spells them.
FOAM_LABELS = {
    FOAM_32D: "32D PU FOAM",
    FOAM_4G: "4G FOAM",
}

#: Ratified default: every new costing, and every body category, starts on 32D —
#: including the categories Burt had baked at 4G (migration 0046 normalises them).
FOAM_DEFAULT = FOAM_32D

# ── The ratio ────────────────────────────────────────────────────────────────
#: PRICE 2017 MARCH.xlsx, sheet PU — C17 (32D PU FOAM) and C19 (4G FOAM),
#: both per 1.22 x 2.44 sheet, both divided by 2.98.
SHEET_PRICE_32D = 4310.0
SHEET_PRICE_4G = 5875.0
FACTOR_4G_DEFAULT = SHEET_PRICE_4G / SHEET_PRICE_32D  # 1.3631090487238979

#: Admin-tunable so the ratio can follow a price list without a deploy. Seeded by
#: migration 0046, guarded there so it never clobbers a value someone has set.
FACTOR_KEY = "costings.pu_foam_4g_factor"

#: A cost line is priced in PU foam when its material IS the section's PU foam
#: row.  Exact names only — "PU INJECTION" is a different product (R60 each) and
#: "FRONT PU" / "SIDES PU" etc. are the EPS-vs-PU toggles, not cost lines.
PU_FOAM_MATERIAL_NAMES = frozenset({"PU", "PU FOAM"})


def normalise(value) -> str:
    """Coerce anything the client (or an old saved record) sends to a known grade.

    Unrecognised, missing or malformed → 32D. A record saved before this lane
    has no foam key at all, and must read as 32D (ratified default 7)."""
    text = str(value or "").strip().upper()
    if text in (FOAM_4G, "4G FOAM", "4GFOAM"):
        return FOAM_4G
    return FOAM_32D


def label(value) -> str:
    """Display name for a grade, spelled as Burt's price list spells it."""
    return FOAM_LABELS[normalise(value)]


def get_4g_factor(db: Session | None) -> float:
    """The 4G/32D price ratio. Falls back to the price-list ratio when the setting
    row is missing or unparseable — a broken setting must never break the
    calculator, and must never silently price 4G at 32D either."""
    if db is None:
        return FACTOR_4G_DEFAULT
    try:
        row = db.query(AdminSetting).filter_by(key=FACTOR_KEY).first()
    except Exception:
        return FACTOR_4G_DEFAULT
    if row is None:
        return FACTOR_4G_DEFAULT
    try:
        val = float(str(row.value).strip())
    except (TypeError, ValueError):
        return FACTOR_4G_DEFAULT
    return val if val > 0 else FACTOR_4G_DEFAULT


def is_pu_foam_row(row) -> bool:
    """True when this BOM row's cost is PU foam, i.e. the grade applies to it.

    Body-option master rows are excluded: they are the EPS/PU toggles and the
    thickness carriers, never the foam itself."""
    if getattr(row, "is_body_option", False):
        return False
    mat = getattr(row, "material", None)
    name = getattr(mat, "name", None) if mat is not None else None
    if not name:
        return False
    return name.strip().upper() in PU_FOAM_MATERIAL_NAMES


def price_multiplier(foam, factor: float | None = None) -> float:
    """Multiplier to apply to a PU foam row's stored (32D) unit price."""
    if normalise(foam) != FOAM_4G:
        return 1.0
    return FACTOR_4G_DEFAULT if factor is None else float(factor)
