"""Admin Master-Data WO (v1.40.6) — admin CRUD for icb_mes.production_stage_thresholds.

Per-stage duration targets (vacuum=8h, press=4h seeds) + the per-row workday_start
the stage clock starts at on a slot's scheduled day. Flat enough for the generic
AdminCrudTable — standard list/create/patch/delete contract (fridge_units idiom).
Planners never read this endpoint: the board embeds each slot's progress
(services/planning.build_board), so reads stay require_user there and this router
stays require_admin end to end. Deactivate (PATCH is_active=false) switches a
stage's bars off without losing the captured hours.
"""
import datetime as _dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import User, get_db
from ...deps import require_admin
from ...models.mes import ProductionStageThreshold

router = APIRouter(prefix="/api/admin/production-thresholds", tags=["admin"])


class StageThresholdOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    stage_code: str
    label: str
    threshold_hours: float
    workday_start: _dt.time
    is_active: bool


class StageThresholdCreate(BaseModel):
    stage_code: str
    label: str
    threshold_hours: float
    workday_start: _dt.time = _dt.time(7, 0)
    is_active: bool = True


class StageThresholdUpdate(BaseModel):
    stage_code: Optional[str] = None
    label: Optional[str] = None
    threshold_hours: Optional[float] = None
    workday_start: Optional[_dt.time] = None
    is_active: Optional[bool] = None


@router.get("", response_model=List[StageThresholdOut])
def list_thresholds(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return db.execute(select(ProductionStageThreshold)
                      .order_by(ProductionStageThreshold.stage_code)).scalars().all()


@router.post("", response_model=StageThresholdOut, status_code=201)
def create_threshold(payload: StageThresholdCreate, db: Session = Depends(get_db),
                     user: User = Depends(require_admin)):
    if payload.threshold_hours <= 0:
        raise HTTPException(status_code=422, detail="threshold_hours must be > 0")
    dup = db.execute(select(ProductionStageThreshold).where(
        ProductionStageThreshold.stage_code == payload.stage_code)).scalars().first()
    if dup is not None:
        raise HTTPException(status_code=409, detail="that stage_code already exists")
    obj = ProductionStageThreshold(**payload.model_dump(), created_by=user.username)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{threshold_id}", response_model=StageThresholdOut)
def update_threshold(threshold_id: int, payload: StageThresholdUpdate,
                     db: Session = Depends(get_db), user: User = Depends(require_admin)):
    obj = db.get(ProductionStageThreshold, threshold_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="stage threshold not found")
    data = payload.model_dump(exclude_unset=True)
    if "threshold_hours" in data and (data["threshold_hours"] is None or data["threshold_hours"] <= 0):
        raise HTTPException(status_code=422, detail="threshold_hours must be > 0")
    for k, v in data.items():
        setattr(obj, k, v)
    obj.updated_by = user.username
    obj.version = (obj.version or 1) + 1
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{threshold_id}", status_code=204)
def delete_threshold(threshold_id: int, db: Session = Depends(get_db),
                     user: User = Depends(require_admin)):
    obj = db.get(ProductionStageThreshold, threshold_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="stage threshold not found")
    db.delete(obj)
    db.commit()
