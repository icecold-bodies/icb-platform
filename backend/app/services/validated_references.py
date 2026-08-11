"""Validated references — configuration fingerprinting and drift comparison.

WO v1.45 (Nadie, ratified by Michael). A VALIDATED REFERENCE is a pointer at a
saved costing that balanced with Nadie's Excel. Two jobs live here:

  1. `config_fingerprint()` — the ONE canonicalisation. Both the write path
     (marking a costing) and the match path (every recompute) call it, so a
     reference can never be stored under a hash the matcher would not produce.

  2. `compare_to_reference()` — the drift verdict: percentage move of the TOTAL
     MANUFACTURING COST (pre-margin, pre-ratio) plus the per-category deltas
     that tell Nadie WHERE it moved.

Deliberately unrelated to the admin-level "BOM Snapshots" feature
(services/… + routers/bom_snapshots.py) — no shared names, storage or wording.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from sqlalchemy.orm import Session

from ..database import AdminSetting

# ── Tolerance setting ────────────────────────────────────────────────────────
# Stored in the generic icb_costings.admin_settings key/value store (seeded by
# migration 0039) rather than global_variables: global variables are injected
# into the formula-evaluation namespace and echoed into every saved result_json,
# and a UI tuning knob has no business in the pricing engine's variable space.
TOLERANCE_KEY = "costings.validated_ref_tolerance_pct"
TOLERANCE_DEFAULT_PCT = 2.0

# Dimensions that form part of a body's identity. Normalised to 3 decimals so
# 13.6 and 13.600 fingerprint alike (the calculator's number inputs step by
# 0.05/0.1, so 3 decimals is well below any meaningful difference).
_DIM_KEYS = ("length", "width", "height")
_DIM_PRECISION = 3

# Body-variable values (EPS/PU insulation thicknesses etc.) are cost-DETERMINING
# inputs, like dims — an 80 mm and a 100 mm body are different configurations,
# not the same one that drifted. Same rounding treatment as dims.
_BODYVAR_PRECISION = 3


def get_tolerance_pct(db: Session) -> float:
    """Admin-tunable drift tolerance, as a percentage. Falls back to the ratified
    2% when the setting row is missing or unparseable (never raises — a broken
    setting must not break the calculator)."""
    row = db.query(AdminSetting).filter_by(key=TOLERANCE_KEY).first()
    if row is None:
        return TOLERANCE_DEFAULT_PCT
    try:
        val = float(str(row.value).strip())
    except (TypeError, ValueError):
        return TOLERANCE_DEFAULT_PCT
    return val if val >= 0 else TOLERANCE_DEFAULT_PCT


def set_tolerance_pct(db: Session, pct: float) -> float:
    """Persist a new tolerance. Caller owns the commit."""
    pct = float(pct)
    if pct < 0:
        raise ValueError("Tolerance must be zero or greater")
    row = db.query(AdminSetting).filter_by(key=TOLERANCE_KEY).first()
    if row is None:
        db.add(AdminSetting(key=TOLERANCE_KEY, value=str(pct)))
    else:
        row.value = str(pct)
    return pct


# ── Fingerprint ──────────────────────────────────────────────────────────────

def _round(value: Any, places: int) -> float:
    try:
        return round(float(value or 0), places)
    except (TypeError, ValueError):
        return 0.0


def _sorted_true_keys(mapping: Any) -> list[str]:
    """Keys of a {id/name: bool} map whose value is truthy, sorted — so the
    fingerprint is invariant to the order the user ticked the options in and to
    JSON key ordering."""
    if not isinstance(mapping, dict):
        return []
    return sorted(str(k) for k, v in mapping.items() if bool(v))


def _sorted_ids(values: Iterable | None) -> list[str]:
    if not values:
        return []
    try:
        return sorted({str(v) for v in values})
    except TypeError:
        return []


def canonical_config(trailer_type_id: int, dims: dict | None,
                     input_state: dict | None) -> dict:
    """The canonical, order-invariant view of a costing's CONFIGURATION.

    Identity = what was BUILT, not what it was priced at. Deliberately EXCLUDED
    (ratified): price overrides, override reasons, profit margin, ratio,
    discount, customer/contact, chassis — those move the money without changing
    the body, and drift in them is exactly what the warning must be able to see.

    Included beyond the ratified base list, and why:
      - `flag_overrides` — on v2-configurator bodies the DRD/SRD/FRONT
        EPS-vs-PU choice lives here, NOT in body_option_selections. Without it
        an EPS body and a PU body hash identically and mis-warn each other.
      - `body_variables` — insulation thicknesses. Cost-determining inputs like
        dims; omitting them turns "80 mm vs 100 mm" into a false drift warning.
    """
    input_state = input_state or {}
    dims = dims or {}
    body_vars = input_state.get("body_variables") or {}
    if not isinstance(body_vars, dict):
        body_vars = {}
    return {
        "trailer_type_id": int(trailer_type_id),
        "dims": {k: _round(dims.get(k), _DIM_PRECISION) for k in _DIM_KEYS},
        "body_options": _sorted_true_keys(input_state.get("body_option_selections")),
        "optional_sections": _sorted_ids(input_state.get("optional_sections_enabled")),
        "excluded_categories": _sorted_ids(input_state.get("excluded_categories")),
        "excluded_bom_ids": _sorted_ids(input_state.get("user_excluded_bom_ids")),
        "flags": _sorted_true_keys(input_state.get("flag_overrides")),
        "body_variables": {str(k): _round(v, _BODYVAR_PRECISION)
                           for k, v in sorted(body_vars.items(), key=lambda kv: str(kv[0]))},
    }


def config_fingerprint(trailer_type_id: int, dims: dict | None,
                       input_state: dict | None) -> str:
    """sha256 hex of the canonical configuration. THE exact-match key.

    `sort_keys=True` + the sorting inside canonical_config make this stable
    across dict ordering, tick order and float formatting.
    """
    canonical = canonical_config(trailer_type_id, dims, input_state)
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def fingerprint_from_result(trailer_type_id: int, dims: dict | None,
                            result: dict | None) -> str:
    """Fingerprint a saved costing's stored result_json (which nests the
    v1.39.9 input_state snapshot). `body_variables` sits alongside input_state
    at the result root, so it is folded in here — keeping canonical_config's
    contract to a single dict."""
    result = result or {}
    input_state = dict(result.get("input_state") or {})
    if "body_variables" not in input_state:
        input_state["body_variables"] = result.get("body_variables") or {}
    return config_fingerprint(trailer_type_id, dims, input_state)


# ── Drift comparison ─────────────────────────────────────────────────────────

def manufacturing_total(result: dict | None) -> float:
    """The comparison basis (ratified): TOTAL MANUFACTURING COST — pre-margin,
    pre-ratio, pre-discount. That is `grand_total` on both the live /api/calculate
    response and the stored result_json."""
    try:
        return float((result or {}).get("grand_total") or 0)
    except (TypeError, ValueError):
        return 0.0


def category_deltas(reference: dict | None, live: dict | None,
                    limit: int = 3) -> list[dict]:
    """Per-category movement, largest absolute move first — the "where did it
    move" detail on the warning banner. Categories present on only one side are
    included with the missing side treated as zero (a section that appeared or
    vanished IS the interesting case)."""
    ref_cats = (reference or {}).get("category_totals") or {}
    live_cats = (live or {}).get("category_totals") or {}
    out: list[dict] = []
    for name in set(ref_cats) | set(live_cats):
        before = _round(ref_cats.get(name), 2)
        after = _round(live_cats.get(name), 2)
        delta = round(after - before, 2)
        if abs(delta) < 0.005:
            continue
        out.append({"category": name, "reference": before, "live": after,
                    "delta": delta})
    out.sort(key=lambda d: abs(d["delta"]), reverse=True)
    return out[:limit] if limit else out


def compare_to_reference(reference_result: dict | None, live_result: dict | None,
                         tolerance_pct: float) -> dict:
    """Drift verdict for a live costing against a matched reference.

    `within_tolerance` False ⇒ show the red warning; True ⇒ the quiet green tick.
    A reference total of zero can't produce a percentage, so it is reported as
    a 0% (quiet) match rather than dividing by zero.
    """
    ref_total = manufacturing_total(reference_result)
    live_total = manufacturing_total(live_result)
    delta = round(live_total - ref_total, 2)
    pct = round(abs(delta) / ref_total * 100, 4) if ref_total else 0.0
    return {
        "reference_total": round(ref_total, 2),
        "live_total": round(live_total, 2),
        "delta": delta,
        # Signed, for the banner's "+2.4%" / "−2.4%" text.
        "delta_pct": round((delta / ref_total * 100), 4) if ref_total else 0.0,
        "abs_delta_pct": pct,
        "tolerance_pct": round(float(tolerance_pct), 4),
        "within_tolerance": pct <= float(tolerance_pct),
        "category_deltas": category_deltas(reference_result, live_result),
    }
