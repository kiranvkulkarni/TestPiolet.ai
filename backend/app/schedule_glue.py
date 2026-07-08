"""ORM ↔ scheduling-engine glue, shared by the tasks router and the AI tools.

The engine itself (`app/scheduling.py`) stays framework-free; this module owns
the translation: loading approved leave into day sets, deriving working-day
durations, building engine inputs from Task rows, and persisting pushes with
audit rows.
"""

import math
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import scheduling
from .models import Leave, LeaveStatus, Task, TaskDependency
from .utils import write_audit

HOURS_PER_DAY = 8.0

TASK_LOAD_OPTIONS = (selectinload(Task.assignee), selectinload(Task.device_model))


def approved_leave_days(db: Session, user_ids: set[int]) -> dict[int, frozenset[date]]:
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


def task_calendar(db: Session, task: Task) -> frozenset[date]:
    if not task.assigned_to:
        return frozenset()
    return approved_leave_days(db, {task.assigned_to}).get(task.assigned_to, frozenset())


def duration_days(task: Task, calendar: frozenset[date]) -> int:
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


def scheduling_inputs(
    db: Session, tasks: list[Task]
) -> tuple[list[scheduling.SchedTask], list[scheduling.Dependency], dict[int, frozenset[date]]]:
    leaves = approved_leave_days(db, {t.assigned_to for t in tasks if t.assigned_to})
    sched_tasks = []
    for t in tasks:
        calendar = leaves.get(t.assigned_to, frozenset()) if t.assigned_to else frozenset()
        sched_tasks.append(
            scheduling.SchedTask(
                id=t.id,
                duration_days=duration_days(t, calendar),
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


def scope_tasks(db: Session, task: Task) -> list[Task]:
    """The task plus everything connected to it through dependency edges."""
    all_deps = db.scalars(select(TaskDependency)).all()
    scope_ids = scheduling.dependency_closure(
        task.id, [scheduling.Dependency(d.from_task_id, d.to_task_id) for d in all_deps]
    )
    return db.scalars(
        select(Task).where(Task.id.in_(scope_ids)).options(*TASK_LOAD_OPTIONS)
    ).all()


def push_and_persist(db: Session, task: Task, user_id: int | None) -> list[Task]:
    """After `task`'s dates changed, shift violated dependents forward. Persists
    the shifts with audit rows; caller commits. Returns the shifted tasks."""
    scope = scope_tasks(db, task)
    sched_tasks, deps, leaves = scheduling_inputs(db, scope)
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
            db, "task", dependent.id, "update", user_id,
            "start_date", str(dependent.start_date), str(shift.start),
        )
        write_audit(
            db, "task", dependent.id, "update", user_id,
            "due_date", str(dependent.due_date), str(shift.end),
        )
        dependent.start_date = shift.start
        dependent.due_date = shift.end
        shifted.append(dependent)
    return shifted


def critical_path_for(db: Session, anchor: Task) -> list[int]:
    """Critical path of the dated tasks in the anchor's dependency scope."""
    scope = [t for t in scope_tasks(db, anchor) if t.start_date and t.due_date]
    if not scope:
        return []
    sched_tasks, deps, leaves = scheduling_inputs(db, scope)
    try:
        result = scheduling.compute_schedule(
            sched_tasks, deps, project_start=min(t.start_date for t in scope), leaves=leaves
        )
    except scheduling.CycleError:
        return []
    return result.critical_path
