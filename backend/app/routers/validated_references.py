"""Validated references API (WO v1.45, Nadie — ratified by Michael).

A thin POINTER layer over saved costings. Nadie marks a costing that balanced
with her Excel as a VALIDATED REFERENCE with a friendly label; she can recall it
as a starting point from the costings page; and whenever a live costing EXACTLY
matches a reference's configuration but the manufacturing cost has drifted
beyond tolerance, the calculator warns her.

Routes (all under /api/validated-references — deliberately distinct from the
unrelated admin-level /api/bom-snapshots feature):

    POST   /api/validated-references              mark a saved costing   [perm]
    GET    /api/validated-references              list (recall dropdown / manage)
    POST   /api/validated-references/{id}/retire  soft retire            [perm]
    POST   /api/validated-references/match        drift verdict for a live costing
    GET    /api/validated-references/settings     read the drift tolerance
    PUT    /api/validated-references/settings     tune the drift tolerance [admin]

Permission split (ratified): creating and retiring need
`costings.validated_refs_manage` ({admin, full}); reading, recalling and the
drift warning need nothing beyond a costings login.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import CalculationRecord, TrailerType, ValidatedReference, get_db
from ..deps import require_admin, require_perm, require_user, user_can
from ..services.validated_references import (
    compare_to_reference,
    config_fingerprint,
    fingerprint_from_result,
    get_tolerance_pct,
    manufacturing_total,
    set_tolerance_pct,
)

router = APIRouter()

MANAGE_PERM = "costings.validated_refs_manage"
LABEL_MAX = 120


def _load_result(rec: CalculationRecord) -> dict:
    try:
        return json.loads(rec.result_json) if rec.result_json else {}
    except (TypeError, ValueError):
        return {}


def _load_dims(rec: CalculationRecord) -> dict:
    try:
        return json.loads(rec.dimensions_json) if rec.dimensions_json else {}
    except (TypeError, ValueError):
        return {}


def _serialize(ref: ValidatedReference, rec: CalculationRecord | None,
               trailer_name: str | None) -> dict:
    result = _load_result(rec) if rec else {}
    dims = _load_dims(rec) if rec else {}
    return {
        "id": ref.id,
        "calculation_id": ref.calculation_id,
        "label": ref.label,
        "config_fingerprint": ref.config_fingerprint,
        "trailer_type_id": ref.trailer_type_id,
        "trailer_name": trailer_name,
        "created_by": ref.created_by,
        "created_at": ref.created_at.isoformat() if ref.created_at else None,
        "active": bool(ref.active),
        "quote_number": rec.quote_number if rec else None,
        "status": (rec.status if rec else None),
        "dims": {k: dims.get(k) for k in ("length", "width", "height")},
        "reference_total": round(manufacturing_total(result), 2),
    }


# ── Settings ─────────────────────────────────────────────────────────────────
# Declared BEFORE the /{ref_id}/retire route so "settings" can never be read as
# a reference id (it could not anyway — the path shapes differ — but keeping the
# literal route first is the habit that survives future edits).

@router.get("/api/validated-references/settings")
async def get_settings(db: Session = Depends(get_db),
                       user=Depends(require_user)):
    """The drift tolerance plus this user's capabilities.

    Readable by any costings user — the calculator shows the tolerance in the
    warning banner ("beyond the 2% tolerance"). The two flags let the legacy
    calculator page hide controls it would only get a 403 from: that page has no
    client-side permission list of its own, and this call is one it already
    makes.
    """
    return {
        "tolerance_pct": get_tolerance_pct(db),
        "can_manage": user_can(user, MANAGE_PERM, db),
        "can_tune": (getattr(user, "role", None) == "admin"),
    }


@router.put("/api/validated-references/settings")
async def put_settings(request: Request, db: Session = Depends(get_db),
                       _admin=Depends(require_admin)):
    body = await request.json()
    raw = body.get("tolerance_pct")
    try:
        pct = float(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="tolerance_pct must be a number")
    try:
        pct = set_tolerance_pct(db, pct)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return {"tolerance_pct": pct}


# ── Create / list / retire ───────────────────────────────────────────────────

@router.post("/api/validated-references", status_code=201)
async def create_reference(request: Request, db: Session = Depends(get_db),
                           user=Depends(require_perm(MANAGE_PERM))):
    """Mark a SAVED costing as a validated reference.

    A reference must point at a saved record — there are no shadow copies. The
    caller (calculator or costing detail page) is responsible for chaining into
    the normal save flow first; an unsaved costing simply has no id to send.
    """
    body = await request.json()
    calc_id = body.get("calculation_id")
    label = (body.get("label") or "").strip()
    if not calc_id:
        raise HTTPException(status_code=400, detail="calculation_id is required")
    if not label:
        raise HTTPException(status_code=400, detail="A label is required")
    if len(label) > LABEL_MAX:
        label = label[:LABEL_MAX]

    rec = db.query(CalculationRecord).filter_by(id=int(calc_id)).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Costing not found")

    result = _load_result(rec)
    # v1.47 — a REPAIRS costing has no body behind it (trailer_type_id is NULL, no
    # dimensions, no body options), so there is no configuration to fingerprint.
    # Refuse cleanly instead of letting config_fingerprint's int(None) 500. The
    # match path needs no counterpart guard: it requires a trailer_type_id, so a
    # repair simply never matches.
    if rec.trailer_type_id is None:
        raise HTTPException(
            status_code=409,
            detail=("A repair quote has no body configuration, so it cannot be used "
                    "as a validated reference."),
        )
    # Pre-v1.39.9 records carry no input_state, so their configuration cannot be
    # reconstructed — fingerprinting one would store a near-empty hash that
    # would then match every other legacy record. Refuse, loudly.
    if not (result.get("input_state") or {}):
        raise HTTPException(
            status_code=409,
            detail=("This costing was saved before the configuration snapshot existed, "
                    "so it cannot be used as a validated reference. Re-save it (or cost "
                    "it again) and mark the new one."),
        )

    existing = (db.query(ValidatedReference)
                  .filter_by(calculation_id=rec.id, active=True).first())
    if existing:
        # Idempotent: re-marking an already-referenced costing relabels it rather
        # than creating a silent duplicate (the partial unique index would reject
        # the insert anyway).
        existing.label = label
        db.commit()
        db.refresh(existing)
        tt = db.query(TrailerType).filter_by(id=existing.trailer_type_id).first()
        return _serialize(existing, rec, tt.name if tt else None)

    ref = ValidatedReference(
        calculation_id=rec.id,
        label=label,
        config_fingerprint=fingerprint_from_result(rec.trailer_type_id,
                                                   _load_dims(rec), result),
        trailer_type_id=rec.trailer_type_id,
        # Display-name snapshot at write time (ADR 0016 / chassis_records
        # edited_by_name pattern) — a later rename must not rewrite who
        # validated this. `username` IS the display name on this User model.
        created_by=(getattr(user, "username", None) or "")[:100] or None,
        active=True,
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)
    tt = db.query(TrailerType).filter_by(id=ref.trailer_type_id).first()
    return _serialize(ref, rec, tt.name if tt else None)


@router.get("/api/validated-references")
async def list_references(trailer_type_id: int | None = None,
                          calculation_id: int | None = None,
                          include_retired: bool = False,
                          db: Session = Depends(get_db),
                          _user=Depends(require_user)):
    """Active references, newest first.

    `trailer_type_id` powers the recall dropdown (only the selected body type);
    `calculation_id` answers the costing detail page's one question ("is THIS
    costing a reference?"); omitting both powers the manage list.
    `include_retired` is the manage list's audit view — retired references never
    reach the dropdown.
    """
    q = db.query(ValidatedReference)
    if trailer_type_id is not None:
        q = q.filter(ValidatedReference.trailer_type_id == trailer_type_id)
    if calculation_id is not None:
        q = q.filter(ValidatedReference.calculation_id == calculation_id)
    if not include_retired:
        q = q.filter(ValidatedReference.active.is_(True))
    refs = q.order_by(ValidatedReference.created_at.desc(),
                      ValidatedReference.id.desc()).all()
    if not refs:
        return []

    calc_ids = {r.calculation_id for r in refs}
    tt_ids = {r.trailer_type_id for r in refs}
    recs = {c.id: c for c in db.query(CalculationRecord)
                                .filter(CalculationRecord.id.in_(calc_ids)).all()}
    names = {t.id: t.name for t in db.query(TrailerType)
                                     .filter(TrailerType.id.in_(tt_ids)).all()}
    return [_serialize(r, recs.get(r.calculation_id), names.get(r.trailer_type_id))
            for r in refs]


@router.post("/api/validated-references/{ref_id}/retire")
async def retire_reference(ref_id: int, db: Session = Depends(get_db),
                           _user=Depends(require_perm(MANAGE_PERM))):
    """Soft retire. The row stays (audit); it stops matching and leaves the
    recall dropdown. Idempotent — retiring an already-retired reference is a
    no-op, not an error."""
    ref = db.query(ValidatedReference).filter_by(id=ref_id).first()
    if not ref:
        raise HTTPException(status_code=404, detail="Validated reference not found")
    if ref.active:
        ref.active = False
        db.commit()
        db.refresh(ref)
    rec = db.query(CalculationRecord).filter_by(id=ref.calculation_id).first()
    tt = db.query(TrailerType).filter_by(id=ref.trailer_type_id).first()
    return _serialize(ref, rec, tt.name if tt else None)


# ── Match + compare ──────────────────────────────────────────────────────────

@router.post("/api/validated-references/match")
async def match_reference(request: Request, db: Session = Depends(get_db),
                          _user=Depends(require_user)):
    """Drift verdict for the costing currently on screen.

    The client posts the SAME configuration fields it already sent to
    /api/calculate plus the live totals from that response, so no recompute
    happens here — this is a hint for the banner, never an input to a write.
    /api/calculate itself is left untouched (hot path, shared contract).

    Returns `{matched: false}` when no ACTIVE reference shares the fingerprint;
    otherwise the reference plus the comparison (`within_tolerance` decides the
    green tick vs the red warning).
    """
    body = await request.json()
    trailer_id = body.get("trailer_type_id")
    if not trailer_id:
        raise HTTPException(status_code=400, detail="trailer_type_id is required")

    # Mirror /api/approve's extraction (routers/calculator.py) EXACTLY, so the
    # match path canonicalises identically to the write path.
    input_state = {
        "body_option_selections": {str(k): bool(v) for k, v in
                                   (body.get("body_option_selections") or {}).items()},
        "excluded_categories": body.get("excluded_categories") or [],
        "flag_overrides": {str(k): bool(v) for k, v in
                           (body.get("flag_overrides") or {}).items()},
        "user_excluded_bom_ids": body.get("user_excluded_bom_ids") or [],
        "optional_sections_enabled": body.get("optional_sections_enabled") or [],
        "body_variables": body.get("body_variables") or {},
    }
    fingerprint = config_fingerprint(int(trailer_id), body.get("dimensions") or {},
                                     input_state)

    ref = (db.query(ValidatedReference)
             .filter(ValidatedReference.config_fingerprint == fingerprint,
                     ValidatedReference.active.is_(True))
             .order_by(ValidatedReference.created_at.desc(),
                       ValidatedReference.id.desc())
             .first())
    tolerance = get_tolerance_pct(db)
    if not ref:
        return {"matched": False, "fingerprint": fingerprint,
                "tolerance_pct": tolerance}

    rec = db.query(CalculationRecord).filter_by(id=ref.calculation_id).first()
    if not rec:
        # The FK is ON DELETE CASCADE, so this is unreachable in practice; treat
        # a dangling reference as "no match" rather than 500-ing the calculator.
        return {"matched": False, "fingerprint": fingerprint,
                "tolerance_pct": tolerance}

    tt = db.query(TrailerType).filter_by(id=ref.trailer_type_id).first()
    live = {
        "grand_total": body.get("grand_total"),
        "category_totals": body.get("category_totals") or {},
    }
    comparison = compare_to_reference(_load_result(rec), live, tolerance)
    return {
        "matched": True,
        "fingerprint": fingerprint,
        "reference": _serialize(ref, rec, tt.name if tt else None),
        "comparison": comparison,
    }
