from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import get_current_user, hash_password, require_manager
from ..database import get_db
from ..models import Task, TaskStatus, User
from ..utils import write_audit

router = APIRouter(prefix="/users", tags=["users"])

ACTIVE_STATUSES = [TaskStatus.pending, TaskStatus.in_progress, TaskStatus.blocked]


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(User).order_by(User.name)).all()


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(
    body: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        is_active=body.is_active,
        avatar_color=body.avatar_color,
    )
    db.add(user)
    db.flush()
    write_audit(db, "user", user.id, "create", current_user.id)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    body: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if current_user.role.value != "manager" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Can only edit your own profile")

    data = body.model_dump(exclude_unset=True)
    if "password" in data:
        password = data.pop("password")
        if password:
            user.password_hash = hash_password(password)
    if "role" in data and current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can change roles")
    for field, value in data.items():
        old = getattr(user, field)
        if old != value:
            write_audit(
                db, "user", user.id, "update", current_user.id, field, str(old), str(value)
            )
            setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}/workload", response_model=schemas.WorkloadOut)
def user_workload(
    user_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    rows = db.execute(
        select(Task.status, func.count(Task.id), func.coalesce(func.sum(Task.estimated_hours), 0))
        .where(Task.assigned_to == user_id, Task.status.in_(ACTIVE_STATUSES))
        .group_by(Task.status)
    ).all()
    by_status = {status.value: count for status, count, _hours in rows}
    return schemas.WorkloadOut(
        user_id=user.id,
        name=user.name,
        active_tasks=sum(count for _s, count, _h in rows),
        estimated_hours=float(sum(hours for _s, _c, hours in rows)),
        by_status=by_status,
    )
