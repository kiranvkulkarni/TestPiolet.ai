"""AI Project Planner (E4): plain-English brief → validated, editable draft plan.

Two halves, deliberately separated:
- `generate_raw_draft` — the only LLM call; asks for strict JSON.
- `validate_and_enrich` / `commit_plan` — deterministic: enum validation, device
  and assignee resolution (workload-balanced, leave-aware), cycle handling,
  scheduling via the E1 engine, risk flags. Fully testable without an LLM.

Nothing is written to the DB until `commit_plan`, which reuses the audited
agent tools (`create_tasks_bulk`, `set_dependency`) — never auto-commit.
"""

import json
import logging
import re
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import agent_tools, scheduling
from .agent_engine import _client
from .config import settings
from .models import DeviceModel, Project, Task, TaskStatus, TestRequest, User, UserRole
from .schedule_glue import approved_leave_days
from .utils import write_audit

logger = logging.getLogger(__name__)

VALID_TASK_TYPES = agent_tools.VALID_TASK_TYPES
VALID_PRIORITIES = agent_tools.VALID_PRIORITIES
DEFAULT_TASK_TYPE = "functional_feature_verification"

PLANNER_PROMPT = """You are a senior Samsung Android QA planner. Turn the manager's \
brief into a JSON test plan. Output ONLY a JSON object, no prose, of this exact shape:

{
  "requests": [
    {
      "title": "…",
      "priority": "critical|high|medium|low",
      "description": "…",
      "tasks": [
        {
          "ref": "t1",
          "title": "…",
          "task_type": "<one of the exact values below>",
          "estimated_hours": 8,
          "priority": "critical|high|medium|low",
          "device": "<device name mentioned in the brief, or null>",
          "depends_on_refs": ["t0"]
        }
      ]
    }
  ],
  "rationale": "one short paragraph on how you structured the plan"
}

Valid task_type values (use them exactly):
functional_sanity, functional_full_sanity, functional_feature_verification,
functional_menu_tree, issue_reproduction, fix_verification, side_effect_verification,
nonfunc_kpi_launch_time, nonfunc_fps, nonfunc_memory_profiling, nonfunc_memory_leak,
nonfunc_power_consumption, compliance_google_its, compliance_google_cts,
compliance_sensor_fusion.

Rules: one request per feature/area; refs must be unique across the whole plan;
dependencies only via depends_on_refs (sanity before feature verification before
KPI/side-effect is a sensible default); estimates in hours (a working day is 8h);
respect any tester/device/day counts in the brief. Do not invent user ids or ids of
any kind — leave assignment to the system."""


def generate_raw_draft(brief: str, context: str) -> dict:
    """One strict-JSON LLM call. Raises ValueError on unusable output."""
    client = _client()
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": f"Team/device context:\n{context}\n\nBrief:\n{brief}"},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content or ""
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("The model did not return a JSON plan")
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"The model returned invalid JSON: {exc}") from exc
    if not isinstance(raw.get("requests"), list) or not raw["requests"]:
        raise ValueError("The model returned a plan without requests")
    return raw


def build_context(db: Session) -> str:
    """Compact team + device context for the planning prompt."""
    testers = db.scalars(
        select(User).where(User.role == UserRole.tester, User.is_active.is_(True))
    ).all()
    devices = db.scalars(select(DeviceModel).where(DeviceModel.is_active.is_(True))).all()
    return (
        f"Testers ({len(testers)}): " + ", ".join(t.name for t in testers) + "\n"
        f"Devices: " + ", ".join(d.model_name for d in devices)
    )


# ---------------------------------------------------------------------------
# Deterministic validation + enrichment
# ---------------------------------------------------------------------------

def _resolve_device(devices: list[DeviceModel], name) -> DeviceModel | None:
    if not name:
        return None
    needle = str(name).lower()
    for d in devices:
        if needle in d.model_name.lower() or d.model_name.lower() in needle:
            return d
    for d in devices:
        if d.series and (needle in d.series.lower() or d.series.lower() in needle):
            return d
    return None


def validate_and_enrich(
    db: Session,
    raw: dict,
    project_id: int | None = None,
    start_date: date | None = None,
) -> dict:
    """Turn a raw (LLM or user-edited) draft into a validated, scheduled draft.

    Never writes. Fixes what it can (invalid enums, unknown devices) and records
    a warning for each fix; drops cycle-forming dependencies with a warning.
    """
    warnings: list[str] = []
    project = db.get(Project, project_id) if project_id else None
    if project_id and project is None:
        warnings.append(f"Project {project_id} not found — pick one before committing.")
    start = start_date or scheduling.next_working_day(date.today() + timedelta(days=1))

    devices = db.scalars(select(DeviceModel).where(DeviceModel.is_active.is_(True))).all()
    testers = db.scalars(
        select(User).where(User.role == UserRole.tester, User.is_active.is_(True))
    ).all()
    load_rows = db.execute(
        select(Task.assigned_to, func.coalesce(func.sum(Task.estimated_hours), 0))
        .where(Task.assigned_to.isnot(None), Task.status.in_(agent_tools.ACTIVE_STATUSES))
        .group_by(Task.assigned_to)
    ).all()
    load = {uid: float(h) for uid, h in load_rows}
    leaves = approved_leave_days(db, {t.id for t in testers})

    # ---- flatten tasks, fix enums, resolve devices --------------------------
    draft_requests: list[dict] = []
    flat: list[dict] = []  # references into draft_requests[*]["tasks"]
    seen_refs: set[str] = set()
    counter = 0
    for req in raw.get("requests", []):
        if not isinstance(req, dict):
            continue
        req_priority = str(req.get("priority") or "medium")
        if req_priority not in VALID_PRIORITIES:
            warnings.append(f'Request "{req.get("title")}": invalid priority "{req_priority}" → medium.')
            req_priority = "medium"
        out_req = {
            "title": str(req.get("title") or "Untitled request").strip(),
            "priority": req_priority,
            "description": req.get("description"),
            "tasks": [],
        }
        for item in req.get("tasks", []) or []:
            if not isinstance(item, dict):
                continue
            counter += 1
            ref = str(item.get("ref") or f"t{counter}")
            if ref in seen_refs:
                ref = f"{ref}_{counter}"
            seen_refs.add(ref)

            task_type = str(item.get("task_type") or "")
            if task_type not in VALID_TASK_TYPES:
                warnings.append(
                    f'Task "{item.get("title")}": unknown task_type "{task_type}" → {DEFAULT_TASK_TYPE}.'
                )
                task_type = DEFAULT_TASK_TYPE
            priority = str(item.get("priority") or req_priority)
            if priority not in VALID_PRIORITIES:
                priority = req_priority
            try:
                estimated = max(1.0, float(item.get("estimated_hours") or 8))
            except (TypeError, ValueError):
                estimated = 8.0

            device = None
            requested_device = item.get("device") or item.get("device_model_name")
            if item.get("device_model_id"):
                device = next((d for d in devices if d.id == int(item["device_model_id"])), None)
            if device is None and requested_device:
                device = _resolve_device(devices, requested_device)
                if device is None:
                    warnings.append(f'Task "{item.get("title")}": device "{requested_device}" not found.')

            task = {
                "ref": ref,
                "title": str(item.get("title") or "Untitled task").strip(),
                "task_type": task_type,
                "priority": priority,
                "estimated_hours": estimated,
                "device_model_id": device.id if device else None,
                "device_model_name": device.model_name if device else None,
                "assigned_to": int(item["assigned_to"]) if item.get("assigned_to") else None,
                "assignee_name": None,
                "depends_on_refs": [
                    str(r) for r in (item.get("depends_on_refs") or []) if r
                ],
                "start_date": None,
                "due_date": None,
            }
            out_req["tasks"].append(task)
            flat.append(task)
        if out_req["tasks"]:
            draft_requests.append(out_req)

    if not flat:
        return {
            "project_id": project_id,
            "project_name": project.name if project else None,
            "start_date": start.isoformat(),
            "requests": [],
            "warnings": [*warnings, "The draft contains no tasks."],
            "rationale": str(raw.get("rationale") or ""),
            "project_end": None,
        }

    # ---- dependencies: resolve refs, drop unknown + cycle-forming edges -----
    ref_index = {t["ref"]: i + 1 for i, t in enumerate(flat)}  # synthetic 1-based ids
    edges: list[scheduling.Dependency] = []
    for t in flat:
        kept = []
        for dep_ref in t["depends_on_refs"]:
            if dep_ref not in ref_index or dep_ref == t["ref"]:
                warnings.append(f'Task "{t["title"]}": dropped unknown dependency "{dep_ref}".')
                continue
            candidate = scheduling.Dependency(ref_index[dep_ref], ref_index[t["ref"]])
            if scheduling.would_create_cycle(list(ref_index.values()), edges, candidate):
                warnings.append(
                    f'Task "{t["title"]}": dependency on "{dep_ref}" would create a cycle — dropped.'
                )
                continue
            edges.append(candidate)
            kept.append(dep_ref)
        t["depends_on_refs"] = kept

    # ---- workload-balanced assignment (respects explicit assignments) -------
    if testers:
        working = dict(load)
        by_id = {u.id: u for u in testers}
        for t in flat:
            if t["assigned_to"] and t["assigned_to"] in by_id:
                working[t["assigned_to"]] = working.get(t["assigned_to"], 0.0) + t["estimated_hours"]
                t["assignee_name"] = by_id[t["assigned_to"]].name
        order = sorted(
            (t for t in flat if not t["assigned_to"]),
            key=lambda t: t["estimated_hours"],
            reverse=True,
        )
        for t in order:
            chosen = min(testers, key=lambda u: working.get(u.id, 0.0))
            t["assigned_to"] = chosen.id
            t["assignee_name"] = chosen.name
            working[chosen.id] = working.get(chosen.id, 0.0) + t["estimated_hours"]
    else:
        warnings.append("No active testers to assign work to.")

    # ---- schedule the draft via the E1 engine --------------------------------
    sched_tasks = [
        scheduling.SchedTask(
            id=ref_index[t["ref"]],
            duration_days=max(1, round(t["estimated_hours"] / 8 + 0.49)),
            assignee_id=t["assigned_to"],
        )
        for t in flat
    ]
    result = scheduling.compute_schedule(sched_tasks, edges, project_start=start, leaves=leaves)
    for t in flat:
        sched = result.tasks[ref_index[t["ref"]]]
        t["start_date"] = sched.start.isoformat()
        t["due_date"] = sched.end.isoformat()
        if t["assigned_to"] and leaves.get(t["assigned_to"]):
            span_days = {sched.start + timedelta(days=i) for i in range((sched.end - sched.start).days + 1)}
            if span_days & leaves[t["assigned_to"]]:
                warnings.append(
                    f'Task "{t["title"]}": {t["assignee_name"]} has approved leave inside '
                    "the scheduled window (dates were stretched around it)."
                )

    return {
        "project_id": project_id,
        "project_name": project.name if project else None,
        "start_date": start.isoformat(),
        "requests": draft_requests,
        "warnings": warnings,
        "rationale": str(raw.get("rationale") or ""),
        "project_end": result.project_end.isoformat(),
    }


# ---------------------------------------------------------------------------
# Commit (explicit confirmation only)
# ---------------------------------------------------------------------------

def commit_plan(db: Session, draft: dict, current_user_id: int | None) -> dict:
    """Create the requests, tasks and dependencies from an edited draft.

    Re-validates hard constraints (project, refs, cycles) and refuses rather than
    silently fixing — the manager already reviewed this exact draft. Reuses the
    audited agent tools so every row lands in AuditLog.
    """
    project = db.get(Project, draft.get("project_id") or 0)
    if project is None:
        return {"error": "a valid project_id is required to commit"}
    requests = draft.get("requests") or []
    flat = [t for req in requests for t in (req.get("tasks") or [])]
    if not flat:
        return {"error": "the draft contains no tasks"}

    refs = [str(t.get("ref")) for t in flat]
    if len(set(refs)) != len(refs):
        return {"error": "duplicate task refs in the draft"}
    ref_index = {r: i + 1 for i, r in enumerate(refs)}
    edges = []
    for t in flat:
        for dep_ref in t.get("depends_on_refs") or []:
            if str(dep_ref) not in ref_index:
                return {"error": f'unknown dependency ref "{dep_ref}"'}
            edges.append(scheduling.Dependency(ref_index[str(dep_ref)], ref_index[str(t["ref"])]))
    try:
        scheduling.topological_order(list(ref_index.values()), edges)
    except scheduling.CycleError:
        return {"error": "the draft contains a dependency cycle — fix it before committing"}

    created_request_ids: list[int] = []
    ref_to_task_id: dict[str, int] = {}
    created_tasks: list[dict] = []
    for req in requests:
        row = TestRequest(
            project_id=project.id,
            title=str(req.get("title") or "Untitled request"),
            description=req.get("description"),
            priority=str(req.get("priority") or "medium"),
            requested_by="AI Planner",
        )
        db.add(row)
        db.flush()
        write_audit(db, "test_request", row.id, "create", current_user_id,
                    new_value=f"[AI planner] {row.title}")
        created_request_ids.append(row.id)

        payload = [
            {
                "test_request_id": row.id,
                "title": t.get("title"),
                "task_type": t.get("task_type"),
                "priority": t.get("priority"),
                "estimated_hours": t.get("estimated_hours"),
                "assigned_to": t.get("assigned_to"),
                "device_model_id": t.get("device_model_id"),
                "start_date": t.get("start_date"),
                "due_date": t.get("due_date"),
            }
            for t in req.get("tasks") or []
        ]
        result = agent_tools.create_tasks_bulk(
            db, current_user_id=current_user_id, tasks=payload, confirm=True
        )
        if "error" in result:
            db.rollback()
            return {"error": f'request "{row.title}": {result["error"]}'}
        for t, created in zip(req.get("tasks") or [], result["created"]):
            ref_to_task_id[str(t["ref"])] = created["id"]
            created_tasks.append(created)

    dep_count = 0
    for t in flat:
        for dep_ref in t.get("depends_on_refs") or []:
            result = agent_tools.set_dependency(
                db,
                current_user_id=current_user_id,
                from_task_id=ref_to_task_id[str(dep_ref)],
                to_task_id=ref_to_task_id[str(t["ref"])],
            )
            if "error" in result:
                logger.warning("Planner dependency skipped: %s", result["error"])
            else:
                dep_count += 1

    return {
        "project_id": project.id,
        "request_ids": created_request_ids,
        "task_ids": [t["id"] for t in created_tasks],
        "created_tasks": created_tasks,
        "dependency_count": dep_count,
        "rationale": f"Committed {len(created_tasks)} tasks across "
        f"{len(created_request_ids)} test request(s) with {dep_count} dependencies "
        f'into "{project.name}" — exactly as reviewed.',
    }
