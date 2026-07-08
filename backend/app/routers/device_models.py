from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import get_current_user, require_manager
from ..database import get_db
from ..models import DeviceModel, User
from ..utils import write_audit

router = APIRouter(prefix="/device-models", tags=["device-models"])


@router.get("", response_model=list[schemas.DeviceModelOut])
def list_device_models(
    active_only: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(DeviceModel).order_by(DeviceModel.model_name)
    if active_only:
        query = query.where(DeviceModel.is_active.is_(True))
    return db.scalars(query).all()


@router.post("", response_model=schemas.DeviceModelOut, status_code=201)
def create_device_model(
    body: schemas.DeviceModelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    device = DeviceModel(**body.model_dump())
    db.add(device)
    db.flush()
    write_audit(db, "device_model", device.id, "create", current_user.id, new_value=device.model_name)
    db.commit()
    db.refresh(device)
    return device


@router.put("/{device_id}", response_model=schemas.DeviceModelOut)
def update_device_model(
    device_id: int,
    body: schemas.DeviceModelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    device = db.get(DeviceModel, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device model not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        old = getattr(device, field)
        if old != value:
            write_audit(
                db, "device_model", device.id, "update", current_user.id, field, str(old), str(value)
            )
            setattr(device, field, value)
    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=204)
def delete_device_model(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    device = db.get(DeviceModel, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device model not found")
    if device.tasks:
        # keep history intact; deactivate instead of hard delete
        device.is_active = False
        write_audit(db, "device_model", device.id, "update", current_user.id, "is_active", "True", "False")
    else:
        write_audit(db, "device_model", device.id, "delete", current_user.id, old_value=device.model_name)
        db.delete(device)
    db.commit()
