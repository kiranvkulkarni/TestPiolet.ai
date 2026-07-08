import math
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import scheduling, schemas
from ..auth import get_current_user, require_not_viewer
from ..database import get_db
from ..email_service import send_task_assigned_email
from ..models import (
    DeviceModel,
    Leave,
    LeaveStatus,
    Task,
    TaskDependency,
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

HOURS_PER_DAY = 8.0


# ---------------------------------------------------------------------------
# Scheduling glue (ORM ↔ pure engine in app/scheduling.py)
# ---------------------------------------------------------------------------

def _approved_leave_days(db: Session, user_ids: set[int]) -> dict[int, frozenset[date]]:
    """Expand approved leave ranges into per-user day sets."""
    if not user_ids:
        return {}
    leaves = db.scalars(
        select(Leave).where(Leave.user_id.in_(user_ids), Leave.status == LeaveStatus.approved)
    ).all()
    days: dict[int, set[date]] = {}
    for lv in leaves:
        day = lv.start_date
        while day <= lv.end_date:
            days.setdefault(lv.user_id, set()).add(day)
            day += timedelta(days=1)
    return {uid: frozenset(d) for uid, d in days.items()}


def _duration_days(task: Task, calendar: frozenset[date]) -> int:
    """Working-day duration: from the current span if dated, else from the estimate."""
    if task.start_date and task.due_date and task.due_date >= task.start_date:
        span = scheduling.count_working_days(task.start_date, task.due_date, calendar)
        if span >= 1:
            return span
        # leave fully covers the current span — the amount of work is unchanged,
        # so measure the span against weekends only
        span = scheduling.count_working_days(task.start_date, task.due_date)
        if span >= 1:
            return span
    if task.estimated_hours:
        return max(1, math.ceil(task.estimated_hours / HOURS_PER_DAY))
    return 1


def _scheduling_inputs(
    db: Session, tasks: list[Task]
) -> tuple[list[scheduling.SchedTask], list[scheduling.Dependency], dict[int, frozenset[date]]]:
    leaves = _approved_leave_days(db, {t.assigned_to for t in tasks if t.assigned_to})
    sched_tasks = []
    for t in tasks:
        calendar = leaves.get(t.assigned_to, frozenset()) if t.assigned_to else frozenset()
        sched_tasks.append(
            scheduling.SchedTask(
                id=t.id,
                duration_days=_duration_days(t, calendar),
                fixed_start=t.start_date,
                assignee_id=t.assigned_to,
            )
        )
    ids = {t.id for t in tasks}
    dep_rows = db.scalars(
        select(TaskDependency).where(
            TaskDependency.from_task_id.in_(ids), TaskDependency.to_task_id.in_(ids)
        )
    ).all()
    deps = [scheduling.Dependency(d.from_task_id, d.to_task_id) for d in dep_rows]
    return sched_tasks, deps, leaves


def _scope_tasks(db: Session, task: Task) -> list[Task]:
    """The task plus everything connected to it through dependency edges."""
    all_deps = db.scalars(select(TaskDependency)).all()
    scope_ids = scheduling.dependency_closure(
        task.id, [scheduling.Dependency(d.from_task_id, d.to_task_id) for d in all_deps]
    )
    return db.scalars(
        select(Task).where(Task.id.in_(scope_ids)).options(*TASK_LOAD_OPTIONS)
    ).all()


def _push_and_persist(db: Session, task: Task, current_user: User) -> list[Task]:
    """After `task`'s dates changed, shift violated dependents forward. Persists
    the shifts with audit rows; caller commits. Returns the shifted tasks."""
    scope = _scope_tasks(db, task)
    sched_tasks, deps, leaves = _scheduling_inputs(db, scope)
    spans = {
        t.id: (t.start_date, t.due_date)
        for t in scope
        if t.start_date and t.due_date
    }
    if task.id not in spans:
        return []
    shifts = scheduling.push_dependents(sched_tasks, deps, spans, task.id, leaves)
    by_id = {t.id: t for t in scope}
    shifted: list[Task] = []
    for shift in shifts:
        dependent = by_id[shift.task_id]
        write_audit(
            db, "task", dependent.id, "update", current_user.id,
            "start_date", str(dependent.start_date), str(shift.start),
        )
        write_audit(
            db, "task", dependent.id, "update", current_user.id,
            "due_date", str(dependent.due_date), str(shift.end),
        )
        dependent.start_date = shift.start
        dependent.due_date = shift.end
        shifted.append(dependent)
    return shifted


def _critical_path(db: Session, anchor: Task) -> list[int]:
    """Critical path of the dated tasks in the anchor's dependency scope."""
    scope = [t for t in _scope_tasks(db, anchor) if t.start_date and t.due_date]
    if not scope:
        return []
    sched_tasks, deps, leaves = _scheduling_inputs(db, scope)
    try:
        result = scheduling.compute_schedule(
            sched_tasks, deps, project_start=min(t.start_date for t in scope), leaves=leaves
        )
    except scheduling.CycleError:
        return []
    return result.critical_path


def _mirror_legacy_depends_on(
    db: Session, task_id: int, old: int | None, new: int | None
) -> None:
    """Keep task_dependencies in sync when the deprecated Task.depends_on column
    is written through the legacy task endpoints (ADR-0005)."""
    if old == new:
        return
    if old:
        stale = db.scalar(
            select(TaskDependency).where(
                TaskDependency.from_task_id == old, TaskDependency.to_task_id == task_id
            )
        )
        if stale:
            db.delete(stale)
    if new:
        _validate_new_edge(db, from_task_id=new, to_task_id=task_id, allow_existing=True)
        exists = db.scalar(
            select(TaskDependency).where(
                TaskDependency.from_task_id == new, TaskDependency.to_task_id == task_id
            )
        )
        if not exists:
            db.add(TaskDependency(from_task_id=new, to_task_id=task_id))


def _validate_new_edge(
    db: Session, from_task_id: int, to_task_id: int, allow_existing: bool = False
) -> None:
    if from_task_id == to_task_id:
        raise HTTPException(status_code=400, detail="A task cannot depend on itself")
    if db.get(Task, from_task_id) is None:
        raise HTTPException(status_code=404, detail=f"Task {from_task_id} not found")
    existing = db.scalars(select(TaskDependency)).all()
    if not allow_existing and any(
        d.from_task_id == from_task_id and d.to_task_id == to_task_id for d in existing
    ):
        raise HTTPException(status_code=409, detail="This dependency already exists")
    edges = [scheduling.Dependency(d.from_task_id, d.to_task_id) for d in existing]
    ids = list({from_task_id, to_task_id, *(e.from_task_id for e in edges), *(e.to_task_id for e in edges)})
    if scheduling.would_create_cycle(ids, edges, scheduling.Dependency(from_task_id, to_task_id)):
        raise HTTPException(
            status_code=400,
            detail=f"Dependency {from_task_id} → {to_task_id} would create a cycle",
        )


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
    rows = db.scalars(query).all()

    # dependencies + critical path over the returned set (E1)
    ids = {t.id for t in rows}
    predecessors: dict[int, list[int]] = {}
    edges: dict[int, list[schemas.GanttDependencyEdge]] = {}
    if ids:
        for dep in db.scalars(
            select(TaskDependency).where(TaskDependency.to_task_id.in_(ids))
        ).all():
            if dep.from_task_id in ids:
                predecessors.setdefault(dep.to_task_id, []).append(dep.from_task_id)
                edges.setdefault(dep.to_task_id, []).append(
                    schemas.GanttDependencyEdge(id=dep.id, from_task_id=dep.from_task_id)
                )
    schedule: dict[int, scheduling.ScheduledTask] = {}
    if rows:
        sched_tasks, deps, leaves = _scheduling_inputs(db, rows)
        try:
            schedule = scheduling.compute_schedule(
                sched_tasks, deps,
                project_start=min(t.start_date for t in rows),
                leaves=leaves,
            ).tasks
        except scheduling.CycleError:
            schedule = {}

    out = []
    for t in rows:
        project = t.test_request.project if t.test_request else None
        sched = schedule.get(t.id)
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
                dependencies=sorted(predecessors.get(t.id, [])),
                dependency_edges=sorted(edges.get(t.id, []), key=lambda e: e.from_task_id),
                critical=sched.is_critical if sched else False,
                slack_days=sched.slack_days if sched else 0,
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
    if task.depends_on:
        _mirror_legacy_depends_on(db, task.id, None, task.depends_on)
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
        if task.depends_on:
            _mirror_legacy_depends_on(db, task.id, None, task.depends_on)
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
    if "depends_on" in data and data["depends_on"] != task.depends_on:
        _mirror_legacy_depends_on(db, task.id, task.depends_on, data["depends_on"])
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


# ---------------------------------------------------------------------------
# Scheduling write endpoints (E1) — consumed by the Gantt workspace in E2
# ---------------------------------------------------------------------------

def _task_calendar(db: Session, task: Task) -> frozenset[date]:
    if not task.assigned_to:
        return frozenset()
    return _approved_leave_days(db, {task.assigned_to}).get(task.assigned_to, frozenset())


def _set_dates(
    db: Session, task: Task, new_start: date, new_due: date, current_user: User
) -> None:
    for field, value in (("start_date", new_start), ("due_date", new_due)):
        old = getattr(task, field)
        if old != value:
            write_audit(db, "task", task.id, "update", current_user.id, field, str(old), str(value))
            setattr(task, field, value)


def _reschedule_result(
    db: Session, task: Task, affected: list[Task]
) -> schemas.RescheduleResult:
    db.commit()
    db.refresh(task)
    for t in affected:
        db.refresh(t)
    return schemas.RescheduleResult(
        task=schemas.TaskOut.model_validate(task),
        affected=[schemas.TaskOut.model_validate(t) for t in affected],
        critical_path=_critical_path(db, task),
    )


@router.patch("/{task_id}/move", response_model=schemas.RescheduleResult)
def move_task(
    task_id: int,
    body: schemas.TaskMoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    """Move a task to a new start date (snapped to the assignee's working
    calendar). Violated dependents are pushed forward, never pulled earlier."""
    task = _get_or_404(db, task_id)
    calendar = _task_calendar(db, task)
    duration = _duration_days(task, calendar)
    new_start, spanned_due = scheduling.task_span(body.start_date, duration, calendar)
    if body.keep_duration or task.due_date is None:
        new_due = spanned_due
    else:
        if task.due_date < new_start:
            raise HTTPException(
                status_code=400,
                detail="New start is after the current due date; use keep_duration or resize",
            )
        new_due = task.due_date
    _set_dates(db, task, new_start, new_due, current_user)
    affected = _push_and_persist(db, task, current_user)
    return _reschedule_result(db, task, affected)


@router.patch("/{task_id}/resize", response_model=schemas.RescheduleResult)
def resize_task(
    task_id: int,
    body: schemas.TaskResizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    """Change a task's duration by setting a new due date or a working-day count."""
    task = _get_or_404(db, task_id)
    if (body.due_date is None) == (body.duration_days is None):
        raise HTTPException(status_code=400, detail="Provide exactly one of due_date or duration_days")
    if task.start_date is None:
        raise HTTPException(status_code=400, detail="Task has no start date; move it first")
    calendar = _task_calendar(db, task)
    if body.duration_days is not None:
        new_due = scheduling.add_working_days(task.start_date, body.duration_days - 1, calendar)
    else:
        if body.due_date < task.start_date:
            raise HTTPException(status_code=400, detail="due_date must be on or after start_date")
        new_due = body.due_date
    _set_dates(db, task, task.start_date, new_due, current_user)
    affected = _push_and_persist(db, task, current_user)
    return _reschedule_result(db, task, affected)


@router.post(
    "/{task_id}/dependencies", response_model=schemas.DependencyResult, status_code=201
)
def add_dependency(
    task_id: int,
    body: schemas.DependencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    """Link a predecessor: `depends_on_task_id` must finish before this task starts.
    Cycles are rejected with 400; duplicates with 409."""
    task = _get_or_404(db, task_id)
    _validate_new_edge(db, from_task_id=body.depends_on_task_id, to_task_id=task_id)
    dep = TaskDependency(
        from_task_id=body.depends_on_task_id, to_task_id=task_id, type=body.type
    )
    db.add(dep)
    db.flush()
    write_audit(
        db, "task_dependency", dep.id, "create", current_user.id,
        new_value=f"{dep.from_task_id} -> {dep.to_task_id}",
    )
    predecessor = db.get(Task, body.depends_on_task_id)
    affected = _push_and_persist(db, predecessor, current_user)
    db.commit()
    db.refresh(dep)
    for t in affected:
        db.refresh(t)
    return schemas.DependencyResult(
        dependency=schemas.DependencyOut.model_validate(dep),
        affected=[schemas.TaskOut.model_validate(t) for t in affected],
        critical_path=_critical_path(db, task),
    )


@router.delete("/{task_id}/dependencies/{dep_id}", response_model=schemas.DependencyResult)
def remove_dependency(
    task_id: int,
    dep_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    """Unlink a dependency edge touching this task. Dates are left as they are
    (removing a constraint never forces a reschedule)."""
    task = _get_or_404(db, task_id)
    dep = db.get(TaskDependency, dep_id)
    if dep is None or task_id not in (dep.from_task_id, dep.to_task_id):
        raise HTTPException(status_code=404, detail="Dependency not found on this task")
    write_audit(
        db, "task_dependency", dep.id, "delete", current_user.id,
        old_value=f"{dep.from_task_id} -> {dep.to_task_id}",
    )
    # keep the deprecated column consistent if it mirrored this edge
    to_task = db.get(Task, dep.to_task_id)
    if to_task and to_task.depends_on == dep.from_task_id:
        to_task.depends_on = None
    db.delete(dep)
    db.commit()
    return schemas.DependencyResult(
        dependency=None, affected=[], critical_path=_critical_path(db, task)
    )
