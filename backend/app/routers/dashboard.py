import csv
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import schemas
from ..auth import get_current_user
from ..database import get_db
from ..models import (
    Leave,
    LeaveStatus,
    Project,
    ProjectStatus,
    RequestStatus,
    Task,
    TaskStatus,
    TestRequest,
    User,
    UserRole,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

ACTIVE_STATUSES = [TaskStatus.pending, TaskStatus.in_progress, TaskStatus.blocked]


@router.get("/summary", response_model=schemas.DashboardSummary)
def summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    status_counts = dict(
        db.execute(select(Task.status, func.count(Task.id)).group_by(Task.status)).all()
    )
    overdue = db.scalar(
        select(func.count(Task.id)).where(
            Task.due_date < date.today(),
            Task.status.notin_([TaskStatus.completed, TaskStatus.cancelled]),
        )
    ) or 0
    return schemas.DashboardSummary(
        total_tasks=sum(status_counts.values()),
        pending=status_counts.get(TaskStatus.pending, 0),
        in_progress=status_counts.get(TaskStatus.in_progress, 0),
        blocked=status_counts.get(TaskStatus.blocked, 0),
        completed=status_counts.get(TaskStatus.completed, 0),
        overdue=overdue,
        active_projects=db.scalar(
            select(func.count(Project.id)).where(Project.status == ProjectStatus.active)
        ) or 0,
        open_requests=db.scalar(
            select(func.count(TestRequest.id)).where(
                TestRequest.status.in_([RequestStatus.open, RequestStatus.in_progress])
            )
        ) or 0,
        team_size=db.scalar(
            select(func.count(User.id)).where(User.is_active.is_(True), User.role != UserRole.viewer)
        ) or 0,
    )


@router.get("/team-workload")
def team_workload(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    users = db.scalars(
        select(User).where(User.is_active.is_(True), User.role != UserRole.viewer).order_by(User.name)
    ).all()
    rows = db.execute(
        select(
            Task.assigned_to,
            Task.status,
            func.count(Task.id),
            func.coalesce(func.sum(Task.estimated_hours), 0),
        )
        .where(Task.assigned_to.isnot(None), Task.status.in_(ACTIVE_STATUSES))
        .group_by(Task.assigned_to, Task.status)
    ).all()
    by_user: dict[int, dict] = {}
    for user_id, status, count, hours in rows:
        entry = by_user.setdefault(user_id, {"active_tasks": 0, "estimated_hours": 0.0, "by_status": {}})
        entry["active_tasks"] += count
        entry["estimated_hours"] += float(hours)
        entry["by_status"][status.value] = count
    return [
        {
            "user_id": u.id,
            "name": u.name,
            "avatar_color": u.avatar_color,
            **by_user.get(u.id, {"active_tasks": 0, "estimated_hours": 0.0, "by_status": {}}),
        }
        for u in users
    ]


@router.get("/task-types")
def task_types(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(select(Task.task_type, func.count(Task.id)).group_by(Task.task_type)).all()
    return [{"task_type": t.value, "count": c} for t, c in rows]


@router.get("/project-progress")
def project_progress(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    projects = db.scalars(
        select(Project).where(Project.status == ProjectStatus.active).order_by(Project.name)
    ).all()
    out = []
    for p in projects:
        rows = db.execute(
            select(Task.status, func.count(Task.id))
            .join(TestRequest, Task.test_request_id == TestRequest.id)
            .where(TestRequest.project_id == p.id)
            .group_by(Task.status)
        ).all()
        counts = {s.value: c for s, c in rows}
        total = sum(counts.values())
        completed = counts.get("completed", 0)
        out.append(
            {
                "project_id": p.id,
                "name": p.name,
                "color_hex": p.color_hex,
                "total_tasks": total,
                "completed_tasks": completed,
                "percent_complete": round(100 * completed / total, 1) if total else 0.0,
                "by_status": counts,
            }
        )
    return out


@router.get("/overdue")
def overdue_tasks(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    tasks = db.scalars(
        select(Task)
        .options(selectinload(Task.assignee))
        .where(
            Task.due_date < date.today(),
            Task.status.notin_([TaskStatus.completed, TaskStatus.cancelled]),
        )
        .order_by(Task.due_date)
    ).all()
    return [
        {
            "id": t.id,
            "title": t.title,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "days_overdue": (date.today() - t.due_date).days if t.due_date else 0,
            "status": t.status.value,
            "priority": t.priority.value,
            "assignee_name": t.assignee.name if t.assignee else None,
        }
        for t in tasks
    ]


@router.get("/upcoming-leaves")
def upcoming_leaves(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    horizon = date.today() + timedelta(days=30)
    leaves = db.scalars(
        select(Leave)
        .options(selectinload(Leave.user))
        .where(
            Leave.status == LeaveStatus.approved,
            Leave.end_date >= date.today(),
            Leave.start_date <= horizon,
        )
        .order_by(Leave.start_date)
    ).all()
    return [
        {
            "id": lv.id,
            "user_id": lv.user_id,
            "user_name": lv.user.name if lv.user else None,
            "start_date": lv.start_date.isoformat(),
            "end_date": lv.end_date.isoformat(),
            "leave_type": lv.leave_type.value,
        }
        for lv in leaves
    ]


@router.get("/export/tasks")
def export_tasks(
    status: str | None = None,
    project_id: int | None = None,
    assigned_to: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = (
        select(Task)
        .options(
            selectinload(Task.assignee),
            selectinload(Task.device_model),
            selectinload(Task.test_request).selectinload(TestRequest.project),
        )
        .order_by(Task.id)
    )
    if status:
        query = query.where(Task.status == status)
    if assigned_to is not None:
        query = query.where(Task.assigned_to == assigned_to)
    if project_id is not None:
        query = query.join(TestRequest).where(TestRequest.project_id == project_id)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "ID", "Title", "Project", "Test Request", "Type", "Status", "Priority",
            "Automation", "Assignee", "Device", "Start", "Due", "Completed",
            "Est. Hours", "Actual Hours", "Build",
        ]
    )
    for t in db.scalars(query).all():
        project = t.test_request.project if t.test_request else None
        writer.writerow(
            [
                t.id,
                t.title,
                project.name if project else "",
                t.test_request.title if t.test_request else "",
                t.task_type.value,
                t.status.value,
                t.priority.value,
                t.automation_type.value,
                t.assignee.name if t.assignee else "",
                t.device_model.model_name if t.device_model else "",
                t.start_date.isoformat() if t.start_date else "",
                t.due_date.isoformat() if t.due_date else "",
                t.completed_date.isoformat() if t.completed_date else "",
                t.estimated_hours or "",
                t.actual_hours or "",
                t.build_version or "",
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tasks.csv"},
    )
