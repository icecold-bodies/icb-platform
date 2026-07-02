"""A09 Plan module (Phase 2) — persisted Production Flow floor state.

GET/PUT /api/plan/floor-state — a single JSON document (one physical factory →
one row, id=1). The Plan page saves on every floor mutation and polls for other
users' changes (last-write-wins; updated_at is the change stamp the client uses
for echo-avoidance). Deliberately isolated from the existing chassis/bay
chokepoints — event-level integration is a later phase.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import User, get_db
from ..deps import require_user
from ..models.mes import PlanFloorState

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
