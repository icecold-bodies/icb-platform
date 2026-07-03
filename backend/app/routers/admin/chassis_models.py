"""Admin CRUD for icb_mes.chassis_models (require_admin; mirrors the fridge_units idiom).

The chassis-type DDM behind the shared make/model dropdown (Pre-Job Card, Planning ack,
Chassis +New/Edit) — seeded by migration 0021, admin-editable here (the CRUD the 0021
docstring promised for v4.35). Also the home of the chassis-type PICTURE default
(image_file, migration 0033): assigning a picture here auto-links it to every chassis of
this type (a manual pick on a chassis stays as that chassis's override). Deactivate
(PATCH is_active=false) hides a type from the dropdowns without losing its data.
"""
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import User, get_db
from ...deps import require_admin
from ...models.mes import ChassisModel
from ...services.chassis import list_type_images

router = APIRouter(prefix="/api/admin/chassis-models", tags=["admin"])


class ChassisModelAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    make: str
    model: str
    category: Optional[str] = None
    max_payload_kg: Optional[int] = None
    image_file: Optional[str] = None
    sort_order: int
    is_active: bool


class ChassisModelCreate(BaseModel):
    make: str
    model: str
    code: Optional[str] = None          # blank → auto-derived from make+model
    category: Optional[str] = None      # truck | bakkie | trailer
    max_payload_kg: Optional[int] = None
    image_file: Optional[str] = None    # a filename from GET /api/chassis-records/type-images
    sort_order: int = 100
    is_active: bool = True


class ChassisModelUpdate(BaseModel):
    make: Optional[str] = None
    model: Optional[str] = None
    code: Optional[str] = None
    category: Optional[str] = None
    max_payload_kg: Optional[int] = None
    image_file: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


def _auto_code(make: str, model: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", f"{make} {model}").strip("-").upper()[:64]


def _check_image(image_file: Optional[str]) -> None:
    """A picture must be a real library file (same guard as the chassis-record manual pick)."""
    if image_file and image_file not in {i.file for i in list_type_images()}:
        raise HTTPException(status_code=422, detail="Unknown chassis-type picture.")


@router.get("", response_model=List[ChassisModelAdminOut])
def list_models(is_active: Optional[bool] = Query(None),
                db: Session = Depends(get_db), user: User = Depends(require_admin)):
    stmt = select(ChassisModel)
    if is_active is not None:
        stmt = stmt.where(ChassisModel.is_active.is_(is_active))
    return db.execute(stmt.order_by(ChassisModel.sort_order, ChassisModel.make, ChassisModel.model)
                      ).scalars().all()


@router.post("", response_model=ChassisModelAdminOut, status_code=201)
def create_model(payload: ChassisModelCreate, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    make, model = payload.make.strip(), payload.model.strip()
    if not make or not model:
        raise HTTPException(status_code=422, detail="Make and model are both required.")
    code = (payload.code or "").strip() or _auto_code(make, model)
    dup = db.execute(select(ChassisModel).where(
        (ChassisModel.code == code) |
        ((ChassisModel.make == make) & (ChassisModel.model == model)))).scalars().first()
    if dup is not None:
        raise HTTPException(status_code=409, detail="That chassis type (or code) already exists.")
    _check_image(payload.image_file)
    obj = ChassisModel(code=code, make=make, model=model, category=payload.category,
                       max_payload_kg=payload.max_payload_kg, image_file=payload.image_file,
                       sort_order=payload.sort_order, is_active=payload.is_active,
                       created_by=user.username)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{model_id}", response_model=ChassisModelAdminOut)
def update_model(model_id: int, payload: ChassisModelUpdate, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    obj = db.get(ChassisModel, model_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="chassis type not found")
    data = payload.model_dump(exclude_unset=True)
    if "image_file" in data:
        _check_image(data["image_file"])
    if data.get("code") is not None and not str(data["code"]).strip():
        data.pop("code")                 # blanking the code is a no-op, never an empty key
    dup_code = data.get("code")
    if dup_code and db.execute(select(ChassisModel).where(
            ChassisModel.code == dup_code, ChassisModel.id != model_id)).scalars().first():
        raise HTTPException(status_code=409, detail="That code is already in use.")
    for k, v in data.items():
        setattr(obj, k, v)
    obj.updated_by = user.username
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{model_id}", status_code=204)
def delete_model(model_id: int, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    obj = db.get(ChassisModel, model_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="chassis type not found")
    db.delete(obj)
    db.commit()
