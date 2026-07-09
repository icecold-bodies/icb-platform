"""A09 Plan module (Phase 2) — persisted Production Flow floor state.

GET/PUT /api/plan/floor-state — a single JSON document (one physical factory →
one row, id=1). The Plan page saves on every floor mutation and polls for other
users' changes (last-write-wins; updated_at is the change stamp the client uses
for echo-avoidance). Deliberately isolated from the existing chassis/bay
chokepoints — event-level integration is a later phase.

GET /api/plan/job-card/{job_number} (3 Jul) — the standardized Plan drawer's
data bundle: the job core + the REAL costing-sheet BOM (result_json items,
grouped per category, costs gated on bom.view_full_cost, NO margins/ratios/
discounts — Michael's rule) + the full chassis-record header (the Chassis-page
fields incl. the resolved type picture) + the pre-job card state.
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import CalculationRecord, User, get_db
from ..deps import require_user, user_can
from ..models.mes import PlanFloorState, PrejobCard, ProductionJob
from ..services import chassis as chassis_svc

router = APIRouter(prefix="/api/plan", tags=["plan"])

ROW_ID = 1


class FloorStateIn(BaseModel):
    state: str  # opaque JSON document (the client owns the shape)


@router.get("/floor-state")
def get_floor_state(db: Session = Depends(get_db), user: User = Depends(require_user)):
    row = db.get(PlanFloorState, ROW_ID)
    if row is None:
        return {"state": None, "updated_at": None}
    return {"state": row.state, "updated_at": row.updated_at.isoformat() if row.updated_at else None}


@router.put("/floor-state")
def put_floor_state(payload: FloorStateIn, db: Session = Depends(get_db),
                    user: User = Depends(require_user)):
    row = db.get(PlanFloorState, ROW_ID)
    now = datetime.now(timezone.utc)
    if row is None:
        row = PlanFloorState(id=ROW_ID, state=payload.state, updated_at=now)
        db.add(row)
    else:
        row.state = payload.state
        row.updated_at = now
    db.commit()
    return {"ok": True, "updated_at": now.isoformat()}


def _stage_clock(db: Session, job_number: str):
    """v1.40.8 drawer stage-clock (Michael 9 Jul): elapsed-vs-threshold for the job's
    FLOOR stage (Panels Ready / Pre-Assembly / Pre-Merge / Merged / QC). Entry times are
    the engine's transition stamps in the floor document; unstamped legacy entries return
    elapsed_hours=None (the drawer shows no clock rather than a guessed one). V/P jobs
    return None here — their clock is slot-based and already lives on the cockpit card +
    CockpitSlotDetail. Stamps are UTC ISO (client toISOString), so the math stays aware."""
    from ..models.mes import ProductionStageThreshold
    from ..services.plan_status import FLOOR_STAGE_CODES, floor_stage_entry_info
    info = floor_stage_entry_info(db).get(str(job_number))
    if not info:
        return None
    code = FLOOR_STAGE_CODES.get(info["label"])
    if code is None:
        return None
    t = db.execute(select(ProductionStageThreshold).where(
        ProductionStageThreshold.stage_code == code,
        ProductionStageThreshold.is_active.is_(True))).scalars().first()
    if t is None:
        return None
    started_iso = elapsed = None
    if info.get("entered_at"):
        try:
            dt = datetime.fromisoformat(str(info["entered_at"]).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
            started_iso = dt.isoformat()
        except (ValueError, TypeError):
            pass
    return {"stage": t.stage_code, "label": t.label, "stage_label": info["label"],
            "threshold_hours": float(t.threshold_hours),
            "started_at": started_iso, "elapsed_hours": elapsed}


@router.get("/job-card/{job_number}")
def job_card(job_number: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """The Plan drawer bundle for one job. BOM = the costing sheet's live items (excluded lines
    dropped), grouped per category in sheet order; costs only with bom.view_full_cost (qty always).
    Chassis = the full chassis-page header via the same get_detail the Chassis screen uses."""
    job = db.execute(
        select(ProductionJob).where(ProductionJob.job_number == str(job_number))
        .order_by(ProductionJob.id.desc())).scalars().first()
    if job is None:
        raise HTTPException(status_code=404, detail="production job not found")

    out = {
        "job": {
            "id": job.id, "job_number": job.job_number, "customer": job.customer_name,
            "description": job.description, "status": job.status,
            "calculation_id": job.calculation_record_id,
        },
        "bom": None, "chassis": None, "prejob": None,
        # v1.40.8 — the drawer's floor stage-clock (None for V/P-stage or off-floor jobs).
        "stage_clock": _stage_clock(db, str(job_number)),
    }

    if job.calculation_record_id:
        rec = db.get(CalculationRecord, job.calculation_record_id)
        if rec is not None and rec.result_json:
            try:
                result = json.loads(rec.result_json)
            except Exception:
                result = {}
            show_cost = user_can(user, "bom.view_full_cost", db)
            cats: dict = {}
            order: list = []
            for it in result.get("items", []):
                if it.get("excluded"):
                    continue
                cat = (it.get("category") or "OTHER").upper()
                if cat not in cats:
                    cats[cat] = {"category": cat, "items": [], "total": 0.0}
                    order.append(cat)
                line = float(it.get("line_cost") or 0)
                cats[cat]["items"].append({
                    "code": it.get("material_code") or None,
                    "material": it.get("material") or "—",
                    "quantity": float(it.get("quantity") or 0),
                    "unit": it.get("unit") or "",
                    "unit_price": (float(it.get("unit_price") or 0) if show_cost else None),
                    "line_total": (line if show_cost else None),
                })
                cats[cat]["total"] += line
            categories = [{**cats[c], "count": len(cats[c]["items"]),
                           "total": (round(cats[c]["total"], 2) if show_cost else None)} for c in order]
            out["bom"] = {
                "quote_number": rec.quote_number,
                "version": int(result.get("version", 1) or 1),
                "show_cost": show_cost,
                "categories": categories,
                "grand_total": (round(sum(cats[c]["total"] for c in order), 2) if show_cost else None),
            }

    if job.chassis_record_id:
        try:
            detail = chassis_svc.get_detail(db, job.chassis_record_id)
            ch = detail.model_dump(exclude={"events"})
            ch["event_count"] = detail.event_count
            out["chassis"] = ch
        except HTTPException:
            pass                                     # tombstoned/missing — drawer shows no chassis tab

    if job.calculation_record_id:
        pj = db.execute(select(PrejobCard).where(PrejobCard.calculation_id == job.calculation_record_id)
                        .order_by(PrejobCard.id.desc())).scalars().first()
        if pj is not None:
            out["prejob"] = {
                "id": pj.id, "status": pj.status,
                "sent_for_check_at": pj.sent_for_check_at.isoformat() if pj.sent_for_check_at else None,
                "pdf_url": f"/api/prejob-cards/{pj.id}/pdf",
            }
    return out
