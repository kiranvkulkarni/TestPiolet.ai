"""The AI agent's tool functions — the ONLY way the AI touches the database.

Each tool is a plain function (db, **kwargs) -> dict returning a small,
JSON-serializable result. Defensive parsing throughout: local models
sometimes send sloppy arguments.
"""

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import scheduling
from .models import (
    DeviceModel,
    Leave,
    LeaveStatus,
    Project,
    Task,
    TaskDependency,
    TaskStatus,
    TestRequest,
    User,
    UserRole,
)
from .schedule_glue import (
    approved_leave_days,
    duration_days,
    push_and_persist,
    scheduling_inputs,
)
from .utils import create_notification, write_audit

ACTIVE_STATUSES = [TaskStatus.pending, TaskStatus.in_progress, TaskStatus.blocked]

# bulk write tools propose a plan and wait for an explicit user confirmation
# at or above this many items (see SYSTEM_PROMPT)
CONFIRM_THRESHOLD = 5


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


def _leave_overlap(db: Session, user_id: int, start: date | None, end: date | None) -> bool:
    if not (user_id and start and end):
        return False
    return bool(
        db.scalar(
            select(Leave.id).where(
                Leave.user_id == user_id,
                Leave.status == LeaveStatus.approved,
                Leave.start_date <= end,
                Leave.end_date >= start,
            )
        )
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

    rationale = f'Created "{result.title}" under test request #{result.test_request_id}'
    confidence = 0.9
    if result.assignee:
        rationale += f", assigned to {result.assignee.name}"
        if _leave_overlap(db, result.assigned_to, result.start_date, result.due_date):
            rationale += " — warning: the dates overlap their approved leave"
            confidence = 0.6
    rationale += "."
    return {
        "created": _task_brief(result),
        "rationale": rationale,
        "confidence": confidence,
        "undo": {"kind": "delete_tasks", "ids": [result.id]},
    }


def create_tasks_bulk(
    db: Session, current_user_id: int | None = None, tasks=None, confirm=False, **_
) -> dict:
    if not isinstance(tasks, list) or not tasks:
        return {"error": "tasks must be a non-empty list of task objects"}
    if len(tasks) >= CONFIRM_THRESHOLD and not confirm:
        return {
            "needs_confirmation": True,
            "plan": [
                {
                    "title": str(item.get("title", "?")),
                    "test_request_id": item.get("test_request_id"),
                    "assigned_to": item.get("assigned_to"),
                }
                for item in tasks
                if isinstance(item, dict)
            ],
            "note": f"This would create {len(tasks)} tasks. Present the plan and ask the user "
            "to confirm; on an explicit yes, call this tool again with confirm=true.",
        }
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
    assignees = {t.assignee.name for t in built if t.assignee}
    rationale = f"Created {len(built)} tasks"
    if assignees:
        rationale += f" assigned across {', '.join(sorted(assignees))}"
    rationale += "."
    return {
        "created_count": len(built),
        "created": [_task_brief(t) for t in built],
        "rationale": rationale,
        "confidence": 0.85,
        "undo": {"kind": "delete_tasks", "ids": [t.id for t in built]},
    }


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

    old_fields = {
        field: (old.isoformat() if isinstance(old, date) else _enum_val(old) if old is not None else None)
        for field, (old, _new) in changes.items()
    }
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

    described = ", ".join(
        f"{field}: {old_fields[field] or '(empty)'} → {_enum_val(new)}"
        for field, (_old, new) in changes.items()
    )
    return {
        "updated": _task_brief(task),
        "changed_fields": list(changes.keys()),
        "rationale": f'Updated "{task.title}" — {described}.',
        "confidence": 0.9,
        "undo": {"kind": "update_tasks", "tasks": [{"id": task.id, "fields": old_fields}]},
    }


# ---------------------------------------------------------------------------
# Operations Assistant tools (E3) — every write returns rationale + confidence
# + an undo payload, and audits under the current user with an [AI] marker.
# ---------------------------------------------------------------------------

def reschedule_tasks(
    db: Session,
    current_user_id: int | None = None,
    task_ids=None,
    start_date=None,
    confirm=False,
    **_,
) -> dict:
    """Move tasks to a new start date, leave/calendar-aware; pushes dependents."""
    if not isinstance(task_ids, list) or not task_ids:
        return {"error": "task_ids must be a non-empty list"}
    start = _parse_date(start_date)
    if start is None:
        return {"error": "start_date (YYYY-MM-DD) is required"}
    wanted = {int(i) for i in task_ids}
    tasks = db.scalars(
        select(Task).options(selectinload(Task.assignee)).where(Task.id.in_(wanted))
    ).all()
    if len(tasks) != len(wanted):
        return {"error": f"tasks not found: {sorted(wanted - {t.id for t in tasks})}"}

    leaves = approved_leave_days(db, {t.assigned_to for t in tasks if t.assigned_to})

    if len(tasks) >= CONFIRM_THRESHOLD and not confirm:
        plan = []
        for t in tasks:
            cal = leaves.get(t.assigned_to, frozenset()) if t.assigned_to else frozenset()
            new_start, new_due = scheduling.task_span(start, duration_days(t, cal), cal)
            plan.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "current": f"{t.start_date} → {t.due_date}",
                    "proposed": f"{new_start} → {new_due}",
                }
            )
        return {
            "needs_confirmation": True,
            "plan": plan,
            "note": f"This would reschedule {len(tasks)} tasks. Present the plan and ask the "
            "user to confirm; on an explicit yes, call this tool again with confirm=true.",
        }

    undo_fields = []
    moved, all_pushed = [], []
    leave_adjusted = 0
    for t in tasks:
        cal = leaves.get(t.assigned_to, frozenset()) if t.assigned_to else frozenset()
        dur = duration_days(t, cal)
        new_start, new_due = scheduling.task_span(start, dur, cal)
        if new_start != start:
            leave_adjusted += 1
        undo_fields.append(
            {
                "id": t.id,
                "fields": {
                    "start_date": t.start_date.isoformat() if t.start_date else None,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                },
            }
        )
        write_audit(db, "task", t.id, "update", current_user_id, "start_date",
                    str(t.start_date), f"[AI] {new_start}")
        write_audit(db, "task", t.id, "update", current_user_id, "due_date",
                    str(t.due_date), f"[AI] {new_due}")
        t.start_date, t.due_date = new_start, new_due
        moved.append(t)
    moved_ids = {t.id for t in moved}
    for t in moved:
        for p in push_and_persist(db, t, current_user_id):
            if p.id not in moved_ids and p.id not in {x.id for x in all_pushed}:
                all_pushed.append(p)
    db.commit()

    rationale = (
        f"Rescheduled {len(moved)} task(s) to start {start} — snapped to each assignee's "
        f"working calendar (weekends + approved leave)"
    )
    if leave_adjusted:
        rationale += f"; {leave_adjusted} task(s) shifted past leave days"
    if all_pushed:
        rationale += f"; pushed {len(all_pushed)} dependent task(s) forward to keep the plan consistent"
    rationale += "."
    confidence = 0.9 - (0.1 if all_pushed else 0.0) - (0.1 if leave_adjusted else 0.0)
    return {
        "rescheduled": [_task_brief(t) for t in moved],
        "pushed_dependents": [_task_brief(t) for t in all_pushed],
        "rationale": rationale,
        "confidence": round(confidence, 2),
        "undo": {"kind": "update_tasks", "tasks": undo_fields},
    }


def set_dependency(
    db: Session, current_user_id: int | None = None, from_task_id=None, to_task_id=None, **_
) -> dict:
    """Link finish-to-start: from_task must finish before to_task starts."""
    if not (from_task_id and to_task_id):
        return {"error": "from_task_id and to_task_id are required"}
    from_id, to_id = int(from_task_id), int(to_task_id)
    if from_id == to_id:
        return {"error": "a task cannot depend on itself"}
    from_task, to_task = db.get(Task, from_id), db.get(Task, to_id)
    if from_task is None or to_task is None:
        return {"error": "one or both tasks not found"}
    existing = db.scalars(select(TaskDependency)).all()
    if any(d.from_task_id == from_id and d.to_task_id == to_id for d in existing):
        return {"error": "this dependency already exists"}
    edges = [scheduling.Dependency(d.from_task_id, d.to_task_id) for d in existing]
    ids = list({from_id, to_id, *(e.from_task_id for e in edges), *(e.to_task_id for e in edges)})
    if scheduling.would_create_cycle(ids, edges, scheduling.Dependency(from_id, to_id)):
        return {"error": f"dependency {from_id} → {to_id} would create a cycle"}

    dep = TaskDependency(from_task_id=from_id, to_task_id=to_id)
    db.add(dep)
    db.flush()
    write_audit(db, "task_dependency", dep.id, "create", current_user_id,
                new_value=f"[AI] {from_id} -> {to_id}")
    pushed = push_and_persist(db, from_task, current_user_id)
    db.commit()

    rationale = f'Linked "{from_task.title}" → "{to_task.title}" (finish-to-start); no cycle introduced'
    if pushed:
        rationale += f"; {len(pushed)} task(s) were pushed to respect it"
    else:
        rationale += "; existing dates already satisfy it"
    rationale += "."
    return {
        "dependency": {"id": dep.id, "from_task_id": from_id, "to_task_id": to_id},
        "pushed_dependents": [_task_brief(t) for t in pushed],
        "rationale": rationale,
        "confidence": 0.95 if not pushed else 0.85,
        "undo": {"kind": "remove_dependency", "task_id": to_id, "dep_id": dep.id},
    }


def remove_dependency(
    db: Session, current_user_id: int | None = None, from_task_id=None, to_task_id=None, **_
) -> dict:
    if not (from_task_id and to_task_id):
        return {"error": "from_task_id and to_task_id are required"}
    from_id, to_id = int(from_task_id), int(to_task_id)
    dep = db.scalar(
        select(TaskDependency).where(
            TaskDependency.from_task_id == from_id, TaskDependency.to_task_id == to_id
        )
    )
    if dep is None:
        return {"error": f"no dependency {from_id} → {to_id} exists"}
    write_audit(db, "task_dependency", dep.id, "delete", current_user_id,
                old_value=f"[AI] {from_id} -> {to_id}")
    to_task = db.get(Task, to_id)
    if to_task and to_task.depends_on == from_id:
        to_task.depends_on = None
    db.delete(dep)
    db.commit()
    return {
        "removed": {"from_task_id": from_id, "to_task_id": to_id},
        "rationale": f"Removed the dependency {from_id} → {to_id}; no dates were changed "
        "(removing a constraint never forces a reschedule).",
        "confidence": 0.95,
        "undo": {"kind": "add_dependency", "from_task_id": from_id, "to_task_id": to_id},
    }


def assign_bulk(
    db: Session,
    current_user_id: int | None = None,
    task_ids=None,
    exclude_user_ids=None,
    confirm=False,
    **_,
) -> dict:
    """Assign/reassign tasks across the team, balancing by estimated hours."""
    if not isinstance(task_ids, list) or not task_ids:
        return {"error": "task_ids must be a non-empty list"}
    exclude = {int(u) for u in exclude_user_ids} if isinstance(exclude_user_ids, list) else set()
    wanted = {int(i) for i in task_ids}
    tasks = db.scalars(select(Task).where(Task.id.in_(wanted))).all()
    if len(tasks) != len(wanted):
        return {"error": f"tasks not found: {sorted(wanted - {t.id for t in tasks})}"}
    testers = db.scalars(
        select(User).where(
            User.role == UserRole.tester, User.is_active.is_(True), User.id.notin_(exclude)
        )
    ).all()
    if not testers:
        return {"error": "no eligible testers (all excluded or inactive)"}

    # current active load (estimated hours) per tester
    rows = db.execute(
        select(Task.assigned_to, func.coalesce(func.sum(Task.estimated_hours), 0))
        .where(Task.assigned_to.isnot(None), Task.status.in_(ACTIVE_STATUSES))
        .group_by(Task.assigned_to)
    ).all()
    load = {uid: float(h) for uid, h in rows}
    before = {u.name: round(load.get(u.id, 0.0), 1) for u in testers}
    leaves = approved_leave_days(db, {u.id for u in testers})

    def task_hours(t: Task) -> float:
        return float(t.estimated_hours) if t.estimated_hours else 8.0

    # greedy: biggest task first onto the least-loaded tester without a leave conflict
    plan: list[tuple[Task, User, bool]] = []
    working = dict(load)
    conflicts = 0
    for t in sorted(tasks, key=task_hours, reverse=True):
        ranked = sorted(testers, key=lambda u: working.get(u.id, 0.0))
        chosen, had_conflict = None, False
        for u in ranked:
            days = leaves.get(u.id, frozenset())
            if t.start_date and t.due_date and any(t.start_date <= d <= t.due_date for d in days):
                continue
            chosen = u
            break
        if chosen is None:  # everyone is on leave in that window — pick least loaded anyway
            chosen, had_conflict = ranked[0], True
            conflicts += 1
        working[chosen.id] = working.get(chosen.id, 0.0) + task_hours(t)
        plan.append((t, chosen, had_conflict))

    if len(tasks) >= CONFIRM_THRESHOLD and not confirm:
        return {
            "needs_confirmation": True,
            "plan": [
                {"id": t.id, "title": t.title, "assign_to": u.name, "leave_conflict": bad}
                for t, u, bad in plan
            ],
            "note": f"This would (re)assign {len(tasks)} tasks. Present the plan and ask the "
            "user to confirm; on an explicit yes, call this tool again with confirm=true.",
        }

    undo_fields = []
    for t, u, _bad in plan:
        undo_fields.append({"id": t.id, "fields": {"assigned_to": t.assigned_to}})
        write_audit(db, "task", t.id, "update", current_user_id, "assigned_to",
                    str(t.assigned_to), f"[AI] {u.id}")
        t.assigned_to = u.id
        create_notification(db, u.id, "task_assigned",
                            f'AI assistant assigned you "{t.title}"', "task", t.id)
    db.commit()

    after = {u.name: round(working.get(u.id, 0.0), 1) for u in testers}
    rationale = (
        f"Assigned {len(plan)} task(s) by estimated hours, largest first onto the least-loaded "
        f"tester; loads (h) before {before} → after {after}"
    )
    rationale += (
        f"; {conflicts} unavoidable leave conflict(s) — flagged for review." if conflicts
        else "; approved leave was avoided for every assignment."
    )
    return {
        "assigned": [
            {"id": t.id, "title": t.title, "assigned_to": u.id, "assignee_name": u.name}
            for t, u, _bad in plan
        ],
        "rationale": rationale,
        "confidence": round(0.85 - (0.15 if conflicts else 0.0), 2),
        "undo": {"kind": "update_tasks", "tasks": undo_fields},
    }


def get_critical_path(db: Session, project_id=None, **_) -> dict:
    """The chain of zero-slack tasks that determines the end date."""
    query = (
        select(Task)
        .options(selectinload(Task.assignee))
        .where(Task.start_date.isnot(None), Task.due_date.isnot(None))
    )
    if project_id:
        query = query.join(TestRequest).where(TestRequest.project_id == int(project_id))
    tasks = db.scalars(query).all()
    if not tasks:
        return {"critical_path": [], "note": "no scheduled tasks in scope"}
    sched_tasks, deps, leaves = scheduling_inputs(db, tasks)
    try:
        result = scheduling.compute_schedule(
            sched_tasks, deps, project_start=min(t.start_date for t in tasks), leaves=leaves
        )
    except scheduling.CycleError as exc:
        return {"error": str(exc)}
    by_id = {t.id: t for t in tasks}
    path = [
        {
            "id": tid,
            "title": by_id[tid].title,
            "assignee_name": by_id[tid].assignee.name if by_id[tid].assignee else None,
            "start_date": result.tasks[tid].start.isoformat(),
            "end_date": result.tasks[tid].end.isoformat(),
        }
        for tid in result.critical_path
    ]
    return {
        "critical_path": path,
        "project_end": result.project_end.isoformat(),
        "summary": f"{len(path)} task(s) have zero slack; any delay on them moves the end "
        f"date ({result.project_end}). {len(tasks) - len(path)} task(s) have slack.",
    }


def find_underloaded_testers(db: Session, threshold_hours=None, **_) -> dict:
    """Testers with active load under the threshold (default: team average)."""
    testers = db.scalars(
        select(User).where(User.role == UserRole.tester, User.is_active.is_(True))
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
    load = {uid: (c, float(h)) for uid, c, h in rows}
    hours = [load.get(u.id, (0, 0.0))[1] for u in testers]
    threshold = float(threshold_hours) if threshold_hours else round(sum(hours) / max(len(hours), 1), 1)
    under = sorted(
        (
            {
                "user_id": u.id,
                "name": u.name,
                "active_tasks": load.get(u.id, (0, 0.0))[0],
                "estimated_hours": load.get(u.id, (0, 0.0))[1],
                "headroom_hours": round(threshold - load.get(u.id, (0, 0.0))[1], 1),
            }
            for u in testers
            if load.get(u.id, (0, 0.0))[1] < threshold
        ),
        key=lambda x: x["estimated_hours"],
    )
    return {
        "threshold_hours": threshold,
        "underloaded": under,
        "summary": f"{len(under)} of {len(testers)} testers are under {threshold}h of active "
        "estimated work.",
    }
