"""The AI agent's tool functions — the ONLY way the AI touches the database.

Each tool is a plain function (db, **kwargs) -> dict returning a small,
JSON-serializable result. Defensive parsing throughout: local models
sometimes send sloppy arguments.
"""

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .models import (
    DeviceModel,
    Leave,
    LeaveStatus,
    Project,
    Task,
    TaskStatus,
    TestRequest,
    User,
    UserRole,
)
from .utils import create_notification, write_audit

ACTIVE_STATUSES = [TaskStatus.pending, TaskStatus.in_progress, TaskStatus.blocked]


def _enum_val(x) -> str:
    return x.value if hasattr(x, "value") else str(x)


def _parse_date(value) -> date | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _task_brief(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "task_type": _enum_val(t.task_type),
        "status": _enum_val(t.status),
        "priority": _enum_val(t.priority),
        "assigned_to": t.assigned_to,
        "assignee_name": t.assignee.name if t.assignee else None,
        "test_request_id": t.test_request_id,
        "start_date": t.start_date.isoformat() if t.start_date else None,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "estimated_hours": t.estimated_hours,
        "device_model_id": t.device_model_id,
    }


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

def get_team_members(db: Session, **_) -> dict:
    users = db.scalars(
        select(User).where(User.is_active.is_(True)).order_by(User.name)
    ).all()
    return {
        "team": [
            {"id": u.id, "name": u.name, "email": u.email, "role": _enum_val(u.role)}
            for u in users
        ]
    }


def get_workload_summary(db: Session, **_) -> dict:
    users = db.scalars(
        select(User).where(User.is_active.is_(True), User.role != UserRole.viewer)
    ).all()
    rows = db.execute(
        select(
            Task.assigned_to,
            func.count(Task.id),
            func.coalesce(func.sum(Task.estimated_hours), 0),
        )
        .where(Task.assigned_to.isnot(None), Task.status.in_(ACTIVE_STATUSES))
        .group_by(Task.assigned_to)
    ).all()
    loads = {uid: {"active_tasks": c, "estimated_hours": float(h)} for uid, c, h in rows}
    return {
        "workload": [
            {
                "user_id": u.id,
                "name": u.name,
                "active_tasks": loads.get(u.id, {}).get("active_tasks", 0),
                "estimated_hours": loads.get(u.id, {}).get("estimated_hours", 0.0),
            }
            for u in users
        ]
    }


def get_projects(db: Session, **_) -> dict:
    projects = db.scalars(select(Project).order_by(Project.created_at.desc())).all()
    return {
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "status": _enum_val(p.status),
                "start_date": p.start_date.isoformat() if p.start_date else None,
                "end_date": p.end_date.isoformat() if p.end_date else None,
            }
            for p in projects
        ]
    }


def get_test_requests(db: Session, project_id=None, status=None, **_) -> dict:
    query = select(TestRequest).order_by(TestRequest.created_at.desc()).limit(50)
    if project_id:
        query = query.where(TestRequest.project_id == int(project_id))
    if status:
        query = query.where(TestRequest.status == str(status))
    requests = db.scalars(query).all()
    return {
        "test_requests": [
            {
                "id": r.id,
                "title": r.title,
                "project_id": r.project_id,
                "priority": _enum_val(r.priority),
                "status": _enum_val(r.status),
            }
            for r in requests
        ]
    }


def get_tasks(
    db: Session,
    status=None,
    assigned_to=None,
    project_id=None,
    overdue=None,
    **_,
) -> dict:
    query = (
        select(Task)
        .options(selectinload(Task.assignee))
        .order_by(Task.created_at.desc())
        .limit(100)
    )
    if status:
        query = query.where(Task.status == str(status))
    if assigned_to:
        query = query.where(Task.assigned_to == int(assigned_to))
    if project_id:
        query = query.join(TestRequest).where(TestRequest.project_id == int(project_id))
    if overdue:
        query = query.where(
            Task.due_date < date.today(),
            Task.status.notin_([TaskStatus.completed, TaskStatus.cancelled]),
        )
    tasks = db.scalars(query).all()
    return {"count": len(tasks), "tasks": [_task_brief(t) for t in tasks]}


def get_device_models(db: Session, **_) -> dict:
    devices = db.scalars(
        select(DeviceModel).where(DeviceModel.is_active.is_(True)).order_by(DeviceModel.model_name)
    ).all()
    return {
        "device_models": [
            {
                "id": d.id,
                "brand": d.brand,
                "series": d.series,
                "model_name": d.model_name,
                "os_version": d.os_version,
            }
            for d in devices
        ]
    }


def check_leave_conflicts(db: Session, user_id=None, start_date=None, end_date=None, **_) -> dict:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if not (user_id and start and end):
        return {"error": "user_id, start_date and end_date (YYYY-MM-DD) are required"}
    leaves = db.scalars(
        select(Leave).where(
            Leave.user_id == int(user_id),
            Leave.status == LeaveStatus.approved,
            Leave.start_date <= end,
            Leave.end_date >= start,
        )
    ).all()
    return {
        "has_conflict": bool(leaves),
        "conflicts": [
            {
                "leave_id": lv.id,
                "start_date": lv.start_date.isoformat(),
                "end_date": lv.end_date.isoformat(),
                "leave_type": _enum_val(lv.leave_type),
            }
            for lv in leaves
        ],
    }


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------

VALID_TASK_TYPES = {
    "functional_sanity", "functional_full_sanity", "functional_feature_verification",
    "functional_menu_tree", "issue_reproduction", "fix_verification",
    "side_effect_verification", "nonfunc_kpi_launch_time", "nonfunc_fps",
    "nonfunc_memory_profiling", "nonfunc_memory_leak", "nonfunc_power_consumption",
    "compliance_google_its", "compliance_google_cts", "compliance_sensor_fusion",
}
VALID_STATUSES = {"pending", "in_progress", "blocked", "completed", "cancelled"}
VALID_PRIORITIES = {"critical", "high", "medium", "low"}


def _build_task(db: Session, args: dict, current_user_id: int | None) -> Task | dict:
    """Validate agent-supplied args and return an unsaved Task, or an error dict."""
    test_request_id = args.get("test_request_id")
    title = (args.get("title") or "").strip()
    if not test_request_id or not title:
        return {"error": "test_request_id and title are required"}
    if db.get(TestRequest, int(test_request_id)) is None:
        return {"error": f"test_request_id {test_request_id} not found — call get_test_requests first"}

    task_type = str(args.get("task_type") or "functional_sanity")
    if task_type not in VALID_TASK_TYPES:
        return {"error": f"invalid task_type '{task_type}'", "valid_types": sorted(VALID_TASK_TYPES)}
    priority = str(args.get("priority") or "medium")
    if priority not in VALID_PRIORITIES:
        return {"error": f"invalid priority '{priority}'"}

    assigned_to = args.get("assigned_to")
    if assigned_to is not None:
        assigned_to = int(assigned_to)
        if db.get(User, assigned_to) is None:
            return {"error": f"user {assigned_to} not found — call get_team_members first"}
    device_model_id = args.get("device_model_id")
    if device_model_id is not None:
        device_model_id = int(device_model_id)
        if db.get(DeviceModel, device_model_id) is None:
            return {"error": f"device_model_id {device_model_id} not found — call get_device_models first"}

    estimated = args.get("estimated_hours")
    return Task(
        test_request_id=int(test_request_id),
        title=title,
        description=args.get("description"),
        task_type=task_type,
        priority=priority,
        assigned_to=assigned_to,
        device_model_id=device_model_id,
        start_date=_parse_date(args.get("start_date")),
        due_date=_parse_date(args.get("due_date")),
        estimated_hours=float(estimated) if estimated is not None else None,
        build_version=args.get("build_version"),
        created_by=current_user_id,
    )


def create_task(db: Session, current_user_id: int | None = None, **args) -> dict:
    result = _build_task(db, args, current_user_id)
    if isinstance(result, dict):
        return result
    db.add(result)
    db.flush()
    write_audit(db, "task", result.id, "create", current_user_id, new_value=f"[AI] {result.title}")
    if result.assigned_to:
        create_notification(
            db, result.assigned_to, "task_assigned",
            f'AI assistant assigned you "{result.title}"', "task", result.id,
        )
    db.commit()
    db.refresh(result)
    return {"created": _task_brief(result)}


def create_tasks_bulk(db: Session, current_user_id: int | None = None, tasks=None, **_) -> dict:
    if not isinstance(tasks, list) or not tasks:
        return {"error": "tasks must be a non-empty list of task objects"}
    built: list[Task] = []
    for i, item in enumerate(tasks):
        if not isinstance(item, dict):
            return {"error": f"tasks[{i}] is not an object"}
        result = _build_task(db, item, current_user_id)
        if isinstance(result, dict):
            result["error"] = f"tasks[{i}]: {result['error']}"
            db.rollback()
            return result
        built.append(result)
    for task in built:
        db.add(task)
        db.flush()
        write_audit(db, "task", task.id, "create", current_user_id, new_value=f"[AI] {task.title}")
        if task.assigned_to:
            create_notification(
                db, task.assigned_to, "task_assigned",
                f'AI assistant assigned you "{task.title}"', "task", task.id,
            )
    db.commit()
    return {"created_count": len(built), "created": [_task_brief(t) for t in built]}


UPDATABLE_FIELDS = {
    "title", "description", "task_type", "status", "priority", "assigned_to",
    "start_date", "due_date", "estimated_hours", "actual_hours", "build_version",
    "device_model_id",
}


def update_task(db: Session, current_user_id: int | None = None, task_id=None, **args) -> dict:
    if not task_id:
        return {"error": "task_id is required"}
    task = db.get(Task, int(task_id))
    if task is None:
        return {"error": f"task {task_id} not found"}

    changes = {}
    for field, value in args.items():
        if field not in UPDATABLE_FIELDS or value is None:
            continue
        if field == "task_type" and str(value) not in VALID_TASK_TYPES:
            return {"error": f"invalid task_type '{value}'"}
        if field == "status" and str(value) not in VALID_STATUSES:
            return {"error": f"invalid status '{value}'"}
        if field == "priority" and str(value) not in VALID_PRIORITIES:
            return {"error": f"invalid priority '{value}'"}
        if field in ("start_date", "due_date"):
            value = _parse_date(value)
            if value is None:
                return {"error": f"{field} must be YYYY-MM-DD"}
        if field in ("assigned_to", "device_model_id"):
            value = int(value)
            model = User if field == "assigned_to" else DeviceModel
            if db.get(model, value) is None:
                return {"error": f"{field} {value} not found"}
        if field in ("estimated_hours", "actual_hours"):
            value = float(value)
        old = getattr(task, field)
        old_cmp = _enum_val(old) if old is not None else None
        new_cmp = _enum_val(value) if value is not None else None
        if old_cmp != new_cmp:
            changes[field] = (old, value)

    if not changes:
        return {"updated": _task_brief(task), "note": "no changes applied"}

    for field, (old, value) in changes.items():
        write_audit(
            db, "task", task.id, "update", current_user_id,
            field, _enum_val(old) if old is not None else None, _enum_val(value),
        )
        setattr(task, field, value)
    if "status" in changes:
        if task.status == TaskStatus.completed and task.completed_date is None:
            task.completed_date = date.today()
    if "assigned_to" in changes and task.assigned_to:
        create_notification(
            db, task.assigned_to, "task_assigned",
            f'AI assistant assigned you "{task.title}"', "task", task.id,
        )
    db.commit()
    db.refresh(task)
    return {"updated": _task_brief(task), "changed_fields": list(changes.keys())}
