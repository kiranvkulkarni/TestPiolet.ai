from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import schemas
from ..auth import get_current_user, require_manager, require_not_viewer
from ..database import get_db
from ..models import Leave, LeaveStatus, Task, TaskStatus, User
from ..utils import create_notification, write_audit

router = APIRouter(prefix="/leaves", tags=["leaves"])


def _get_or_404(db: Session, leave_id: int) -> Leave:
    leave = db.get(Leave, leave_id)
    if leave is None:
        raise HTTPException(status_code=404, detail="Leave not found")
    return leave


@router.get("", response_model=list[schemas.LeaveOut])
def list_leaves(
    user_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(Leave).options(selectinload(Leave.user)).order_by(Leave.start_date.desc())
    if user_id is not None:
        query = query.where(Leave.user_id == user_id)
    if status:
        query = query.where(Leave.status == status)
    return db.scalars(query).all()


@router.get("/calendar", response_model=list[schemas.LeaveOut])
def leaves_calendar(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = (
        select(Leave)
        .options(selectinload(Leave.user))
        .where(Leave.status != LeaveStatus.rejected)
        .order_by(Leave.start_date)
    )
    if start:
        query = query.where(Leave.end_date >= start)
    if end:
        query = query.where(Leave.start_date <= end)
    return db.scalars(query).all()


@router.get("/conflicts")
def leave_conflicts(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Approved/pending leaves overlapping active tasks of the same user."""
    leaves = db.scalars(
        select(Leave)
        .options(selectinload(Leave.user))
        .where(Leave.status != LeaveStatus.rejected, Leave.end_date >= date.today())
    ).all()
    conflicts = []
    for lv in leaves:
        tasks = db.scalars(
            select(Task).where(
                Task.assigned_to == lv.user_id,
                Task.status.in_([TaskStatus.pending, TaskStatus.in_progress, TaskStatus.blocked]),
                Task.start_date.isnot(None),
                Task.due_date.isnot(None),
                Task.start_date <= lv.end_date,
                Task.due_date >= lv.start_date,
            )
        ).all()
        if tasks:
            conflicts.append(
                {
                    "leave_id": lv.id,
                    "user_id": lv.user_id,
                    "user_name": lv.user.name if lv.user else None,
                    "leave_start": lv.start_date.isoformat(),
                    "leave_end": lv.end_date.isoformat(),
                    "tasks": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "start_date": t.start_date.isoformat(),
                            "due_date": t.due_date.isoformat(),
                        }
                        for t in tasks
                    ],
                }
            )
    return conflicts


@router.post("", response_model=schemas.LeaveOut, status_code=201)
def create_leave(
    body: schemas.LeaveCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    if body.end_date < body.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    if current_user.role.value != "manager" and body.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Can only request leave for yourself")
    if db.get(User, body.user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    leave = Leave(**body.model_dump())
    db.add(leave)
    db.flush()
    write_audit(db, "leave", leave.id, "create", current_user.id)
    # notify managers
    managers = db.scalars(select(User).where(User.role == "manager", User.is_active.is_(True))).all()
    for m in managers:
        if m.id != current_user.id:
            create_notification(
                db, m.id, "leave_requested",
                f"{current_user.name} requested {body.leave_type.value} leave "
                f"{body.start_date} → {body.end_date}",
                "leave", leave.id,
            )
    db.commit()
    db.refresh(leave)
    return leave


@router.get("/{leave_id}", response_model=schemas.LeaveOut)
def get_leave(leave_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _get_or_404(db, leave_id)


@router.put("/{leave_id}", response_model=schemas.LeaveOut)
def update_leave(
    leave_id: int,
    body: schemas.LeaveUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    leave = _get_or_404(db, leave_id)
    if current_user.role.value != "manager" and leave.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Can only edit your own leave")
    for field, value in body.model_dump(exclude_unset=True).items():
        old = getattr(leave, field)
        if old != value:
            write_audit(
                db, "leave", leave.id, "update", current_user.id, field, str(old), str(value)
            )
            setattr(leave, field, value)
    db.commit()
    db.refresh(leave)
    return leave


@router.patch("/{leave_id}/approve", response_model=schemas.LeaveOut)
def approve_leave(
    leave_id: int,
    body: schemas.LeaveApprove,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    leave = _get_or_404(db, leave_id)
    write_audit(
        db, "leave", leave.id, "update", current_user.id,
        "status", leave.status.value, body.status.value,
    )
    leave.status = body.status
    leave.approved_by = current_user.id
    create_notification(
        db, leave.user_id, "leave_decision",
        f"Your leave {leave.start_date} → {leave.end_date} was {body.status.value}",
        "leave", leave.id,
    )
    db.commit()
    db.refresh(leave)
    return leave


@router.delete("/{leave_id}", status_code=204)
def delete_leave(
    leave_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    leave = _get_or_404(db, leave_id)
    if current_user.role.value != "manager" and leave.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Can only delete your own leave")
    write_audit(db, "leave", leave.id, "delete", current_user.id)
    db.delete(leave)
    db.commit()
