from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import schemas
from ..auth import get_current_user, require_not_viewer
from ..database import get_db
from ..email_service import send_task_assigned_email
from ..models import (
    DeviceModel,
    Leave,
    LeaveStatus,
    Task,
    TaskStatus,
    TestRequest,
    User,
)
from ..utils import create_notification, write_audit

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _get_or_404(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _validate_refs(db: Session, data: dict) -> None:
    if data.get("test_request_id") and db.get(TestRequest, data["test_request_id"]) is None:
        raise HTTPException(status_code=404, detail="Test request not found")
    if data.get("assigned_to") and db.get(User, data["assigned_to"]) is None:
        raise HTTPException(status_code=404, detail="Assignee not found")
    if data.get("device_model_id") and db.get(DeviceModel, data["device_model_id"]) is None:
        raise HTTPException(status_code=404, detail="Device model not found")
    if data.get("depends_on") and db.get(Task, data["depends_on"]) is None:
        raise HTTPException(status_code=404, detail="Dependency task not found")


def _notify_assignment(db: Session, task: Task, actor: User) -> None:
    if task.assigned_to and task.assigned_to != actor.id:
        notif = create_notification(
            db,
            task.assigned_to,
            "task_assigned",
            f'{actor.name} assigned you "{task.title}"',
            "task",
            task.id,
        )
        assignee = db.get(User, task.assigned_to)
        if assignee:
            notif.email_sent = send_task_assigned_email(assignee.email, task.title)


def _apply_status(task: Task, new_status: TaskStatus) -> None:
    task.status = new_status
    if new_status == TaskStatus.completed and task.completed_date is None:
        task.completed_date = date.today()
    elif new_status != TaskStatus.completed:
        task.completed_date = None


TASK_LOAD_OPTIONS = (selectinload(Task.assignee), selectinload(Task.device_model))


@router.get("", response_model=list[schemas.TaskOut])
def list_tasks(
    status: str | None = None,
    assigned_to: int | None = None,
    project_id: int | None = None,
    test_request_id: int | None = None,
    priority: str | None = None,
    task_type: str | None = None,
    overdue: bool = False,
    search: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(Task).options(*TASK_LOAD_OPTIONS).order_by(Task.created_at.desc())
    if status:
        query = query.where(Task.status == status)
    if assigned_to is not None:
        query = query.where(Task.assigned_to == assigned_to)
    if test_request_id is not None:
        query = query.where(Task.test_request_id == test_request_id)
    if project_id is not None:
        query = query.join(TestRequest).where(TestRequest.project_id == project_id)
    if priority:
        query = query.where(Task.priority == priority)
    if task_type:
        query = query.where(Task.task_type == task_type)
    if overdue:
        query = query.where(
            Task.due_date < date.today(),
            Task.status.notin_([TaskStatus.completed, TaskStatus.cancelled]),
        )
    if search:
        query = query.where(Task.title.ilike(f"%{search}%"))
    return db.scalars(query).all()


@router.get("/gantt", response_model=list[schemas.GanttTaskOut])
def gantt_tasks(
    project_id: int | None = None,
    test_cycle_id: int | None = None,
    assigned_to: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = (
        select(Task)
        .join(TestRequest)
        .options(
            selectinload(Task.assignee),
            selectinload(Task.test_request).selectinload(TestRequest.project),
        )
        .where(Task.start_date.isnot(None), Task.due_date.isnot(None))
        .order_by(Task.start_date)
    )
    if project_id is not None:
        query = query.where(TestRequest.project_id == project_id)
    if test_cycle_id is not None:
        query = query.where(TestRequest.test_cycle_id == test_cycle_id)
    if assigned_to is not None:
        query = query.where(Task.assigned_to == assigned_to)

    progress_by_status = {
        TaskStatus.pending: 0.0,
        TaskStatus.in_progress: 50.0,
        TaskStatus.blocked: 25.0,
        TaskStatus.completed: 100.0,
        TaskStatus.cancelled: 0.0,
    }
    out = []
    for t in db.scalars(query).all():
        project = t.test_request.project if t.test_request else None
        out.append(
            schemas.GanttTaskOut(
                id=t.id,
                title=t.title,
                start_date=t.start_date,
                due_date=t.due_date,
                status=t.status,
                priority=t.priority,
                progress=progress_by_status.get(t.status, 0.0),
                assigned_to=t.assigned_to,
                assignee_name=t.assignee.name if t.assignee else None,
                project_id=project.id if project else None,
                project_name=project.name if project else None,
                project_color=project.color_hex if project else None,
                test_request_id=t.test_request_id,
                test_request_title=t.test_request.title if t.test_request else "",
                depends_on=t.depends_on,
            )
        )
    return out


@router.post("", response_model=schemas.TaskOut, status_code=201)
def create_task(
    body: schemas.TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    data = body.model_dump()
    _validate_refs(db, data)
    task = Task(**data, created_by=current_user.id)
    db.add(task)
    db.flush()
    write_audit(db, "task", task.id, "create", current_user.id, new_value=task.title)
    _notify_assignment(db, task, current_user)
    db.commit()
    db.refresh(task)
    return task


@router.post("/bulk", response_model=list[schemas.TaskOut], status_code=201)
def create_tasks_bulk(
    body: schemas.TaskBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    tasks = []
    for item in body.tasks:
        data = item.model_dump()
        _validate_refs(db, data)
        task = Task(**data, created_by=current_user.id)
        db.add(task)
        db.flush()
        write_audit(db, "task", task.id, "create", current_user.id, new_value=task.title)
        _notify_assignment(db, task, current_user)
        tasks.append(task)
    db.commit()
    for t in tasks:
        db.refresh(t)
    return tasks


@router.post("/bulk-update", response_model=list[schemas.TaskOut])
def bulk_update_tasks(
    body: schemas.TaskBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    data = body.update.model_dump(exclude_unset=True)
    _validate_refs(db, data)
    tasks = db.scalars(select(Task).where(Task.id.in_(body.task_ids))).all()
    if len(tasks) != len(set(body.task_ids)):
        raise HTTPException(status_code=404, detail="One or more tasks not found")
    for task in tasks:
        for field, value in data.items():
            old = getattr(task, field)
            if old != value:
                write_audit(
                    db, "task", task.id, "update", current_user.id, field, str(old), str(value)
                )
                if field == "status":
                    _apply_status(task, value)
                else:
                    setattr(task, field, value)
                if field == "assigned_to":
                    _notify_assignment(db, task, current_user)
    db.commit()
    for t in tasks:
        db.refresh(t)
    return tasks


@router.get("/{task_id}", response_model=schemas.TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _get_or_404(db, task_id)


@router.put("/{task_id}", response_model=schemas.TaskOut)
def update_task(
    task_id: int,
    body: schemas.TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    task = _get_or_404(db, task_id)
    data = body.model_dump(exclude_unset=True)
    _validate_refs(db, data)
    if data.get("depends_on") == task.id:
        raise HTTPException(status_code=400, detail="A task cannot depend on itself")
    for field, value in data.items():
        old = getattr(task, field)
        if old != value:
            write_audit(
                db, "task", task.id, "update", current_user.id, field, str(old), str(value)
            )
            if field == "status":
                _apply_status(task, value)
            else:
                setattr(task, field, value)
            if field == "assigned_to":
                _notify_assignment(db, task, current_user)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}/status", response_model=schemas.TaskOut)
def update_task_status(
    task_id: int,
    body: schemas.TaskStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    task = _get_or_404(db, task_id)
    if task.status != body.status:
        write_audit(
            db,
            "task",
            task.id,
            "update",
            current_user.id,
            "status",
            task.status.value,
            body.status.value,
        )
        _apply_status(task, body.status)
    if body.actual_hours is not None:
        task.actual_hours = body.actual_hours
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    task = _get_or_404(db, task_id)
    write_audit(db, "task", task.id, "delete", current_user.id, old_value=task.title)
    # clear inbound dependency pointers before deleting
    for dependent in db.scalars(select(Task).where(Task.depends_on == task_id)).all():
        dependent.depends_on = None
    db.delete(task)
    db.commit()


@router.get("/{task_id}/leave-conflicts", response_model=schemas.LeaveConflictOut)
def task_leave_conflicts(
    task_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    task = _get_or_404(db, task_id)
    if not (task.assigned_to and task.start_date and task.due_date):
        return schemas.LeaveConflictOut(has_conflict=False, conflicts=[])
    leaves = db.scalars(
        select(Leave).where(
            Leave.user_id == task.assigned_to,
            Leave.status == LeaveStatus.approved,
            Leave.start_date <= task.due_date,
            Leave.end_date >= task.start_date,
        )
    ).all()
    conflicts = [
        {
            "leave_id": lv.id,
            "start_date": lv.start_date.isoformat(),
            "end_date": lv.end_date.isoformat(),
            "leave_type": lv.leave_type.value,
        }
        for lv in leaves
    ]
    return schemas.LeaveConflictOut(has_conflict=bool(conflicts), conflicts=conflicts)
