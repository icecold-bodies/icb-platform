"""Read-only floor surface at the ERP-contract paths (v1.43 ERP enablement; ADR 0038).

The integration Pack (docs/handoffs/ERP_MES_INTEGRATION_PACK_v1.0.md §4) contracts
`GET /api/floor/state` and `GET /api/floor-events`. Neither existed: floor state is
served to the SPA at `/api/plan/floor-state` (routers/plan.py — untouched), and the
`icb_mes.floor_events` journal (written by every services/floor.py transition since
v1.41.0) had no read endpoint at all. This router adds both contract paths, readable
by an integration token OR any signed-in user. Read-only: no floor logic, no writes.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_user
from ..integration_auth import integration_readable
from ..models.mes import FloorEvent
from .plan import get_floor_state

router = APIRouter(prefix="/api", tags=["floor-read"])


@router.get("/floor/state")
@integration_readable
def floor_state(db: Session = Depends(get_db),
                user=Depends(require_user)):
    """The same document `/api/plan/floor-state` serves (delegates to the plan
    handler — one source of truth for the payload; the SPA path stays as-is)."""
    return get_floor_state(db=db, user=user)


@router.get("/floor-events")
@integration_readable
def list_floor_events(
    since_id: int = Query(0, ge=0, description="Only events with id > since_id; "
                          "page forward by passing the previous response's last_id"),
    job_number: Optional[str] = Query(None, description="Filter to one job"),
    event_type: Optional[str] = Query(None, description="Filter to one event type"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    """The floor journal, ascending id — the incremental-pull shape (start at
    since_id=0, store last_id, repeat). Each event: actor, timestamps, from/to
    stage and the payload echo, exactly as journaled by the transition engine."""
    q = db.query(FloorEvent).filter(FloorEvent.id > since_id)
    if job_number:
        q = q.filter(FloorEvent.job_number == str(job_number))
    if event_type:
        q = q.filter(FloorEvent.event_type == event_type)
    rows = q.order_by(FloorEvent.id.asc()).limit(limit).all()
    events = [{
        "id": e.id,
        "event_type": e.event_type,
        "job_number": e.job_number,
        "production_job_id": e.production_job_id,
        "from_stage": e.from_stage,
        "to_stage": e.to_stage,
        "details": e.details,
        "doc_version": e.doc_version,
        "user_id": e.user_id,
        "user_name": e.user_name,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in rows]
    return {"events": events,
            "count": len(events),
            "last_id": events[-1]["id"] if events else since_id}
