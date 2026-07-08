"""AI Timeline Simulator (E5): non-destructive what-if over the current plan.

A scenario is computed entirely in-memory (ADR-0006): the current tasks,
dependencies and approved-leave calendars are turned into pure `scheduling.py`
inputs, a baseline run and a perturbed run are diffed, and mitigation
candidates are themselves ranked by re-simulation. Nothing is ever written —
applying a mitigation is the frontend/agent calling the normal audited
endpoints with the returned payload.

Perturbation shapes (JSON):
- {"type": "leave", "user_id": 3, "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
- {"type": "slip",  "task_id": 42, "days": 3}
- {"type": "remove_task", "task_id": 42}
- {"type": "add_task", "title": "…", "estimated_hours": 16,
   "assigned_to": 3 | null, "after_task_id": 42 | null}
"""

import math
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import scheduling
from .models import Task, TestRequest, User, UserRole
from .schedule_glue import approved_leave_days, duration_days

SIM_TASK_ID_START = -1  # synthetic (added) tasks get negative ids
MAX_MITIGATIONS = 4


@dataclass
class SimInputs:
    tasks: list[scheduling.SchedTask]
    deps: list[scheduling.Dependency]
    leaves: dict[int, frozenset[date]]
    project_start: date


def _parse_date(value) -> date | None:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date() if value else None
    except ValueError:
        return None


def _load_inputs(db: Session, project_id: int | None) -> tuple[SimInputs, dict[int, Task]]:
    query = (
        select(Task)
        .options(selectinload(Task.assignee))
        .where(Task.start_date.isnot(None), Task.due_date.isnot(None))
    )
    if project_id:
        query = query.join(TestRequest).where(TestRequest.project_id == int(project_id))
    rows = db.scalars(query).all()
    by_id = {t.id: t for t in rows}
    leaves = approved_leave_days(db, {t.assigned_to for t in rows if t.assigned_to})
    sched = []
    for t in rows:
        cal = leaves.get(t.assigned_to, frozenset()) if t.assigned_to else frozenset()
        sched.append(
            scheduling.SchedTask(
                id=t.id,
                duration_days=duration_days(t, cal),
                fixed_start=t.start_date,
                assignee_id=t.assigned_to,
            )
        )
    from .models import TaskDependency

    ids = set(by_id)
    deps = [
        scheduling.Dependency(d.from_task_id, d.to_task_id)
        for d in db.scalars(select(TaskDependency)).all()
        if d.from_task_id in ids and d.to_task_id in ids
    ]
    project_start = min((t.start_date for t in rows), default=date.today())
    return SimInputs(tasks=sched, deps=deps, leaves=leaves, project_start=project_start), by_id


def _apply_perturbations(
    inputs: SimInputs, perturbations: list[dict], by_id: dict[int, Task]
) -> tuple[SimInputs, list[dict], list[str], list[int], list[dict]]:
    """Returns (new inputs, applied echoes, errors, removed ids, added synthetic tasks)."""
    tasks = list(inputs.tasks)
    deps = list(inputs.deps)
    leaves = {uid: set(days) for uid, days in inputs.leaves.items()}
    applied: list[dict] = []
    errors: list[str] = []
    removed: list[int] = []
    added: list[dict] = []
    next_synth = SIM_TASK_ID_START

    for p in perturbations or []:
        if not isinstance(p, dict):
            continue
        kind = str(p.get("type") or "")

        if kind == "leave":
            user_id = p.get("user_id")
            start, end = _parse_date(p.get("start_date")), _parse_date(p.get("end_date"))
            if not (user_id and start and end and end >= start):
                errors.append("leave: user_id, start_date and end_date (YYYY-MM-DD) required")
                continue
            days = leaves.setdefault(int(user_id), set())
            day = start
            while day <= end:
                days.add(day)
                day += timedelta(days=1)
            applied.append({"type": "leave", "user_id": int(user_id),
                            "start_date": start.isoformat(), "end_date": end.isoformat()})

        elif kind == "slip":
            task_id, days = p.get("task_id"), p.get("days")
            if not (task_id and days):
                errors.append("slip: task_id and days required")
                continue
            idx = next((i for i, t in enumerate(tasks) if t.id == int(task_id)), None)
            if idx is None:
                errors.append(f"slip: task {task_id} not in scope")
                continue
            base = tasks[idx].fixed_start or inputs.project_start
            tasks[idx] = replace(tasks[idx], fixed_start=base + timedelta(days=int(days)))
            applied.append({"type": "slip", "task_id": int(task_id), "days": int(days)})

        elif kind == "remove_task":
            task_id = p.get("task_id")
            if not task_id or all(t.id != int(task_id) for t in tasks):
                errors.append(f"remove_task: task {task_id} not in scope")
                continue
            task_id = int(task_id)
            tasks = [t for t in tasks if t.id != task_id]
            deps = [d for d in deps if task_id not in (d.from_task_id, d.to_task_id)]
            removed.append(task_id)
            applied.append({"type": "remove_task", "task_id": task_id})

        elif kind == "add_task":
            title = str(p.get("title") or "New scope")
            try:
                hours = max(1.0, float(p.get("estimated_hours") or 8))
            except (TypeError, ValueError):
                hours = 8.0
            assignee = int(p["assigned_to"]) if p.get("assigned_to") else None
            after = int(p["after_task_id"]) if p.get("after_task_id") else None
            synth = scheduling.SchedTask(
                id=next_synth,
                duration_days=max(1, math.ceil(hours / 8)),
                assignee_id=assignee,
            )
            tasks.append(synth)
            if after and any(t.id == after for t in tasks):
                deps.append(scheduling.Dependency(after, next_synth))
            added.append({"sim_id": next_synth, "title": title, "estimated_hours": hours,
                          "assigned_to": assignee, "after_task_id": after})
            applied.append({"type": "add_task", **added[-1]})
            next_synth -= 1

        else:
            errors.append(f'unknown perturbation type "{kind}"')

    new_inputs = SimInputs(
        tasks=tasks,
        deps=deps,
        leaves={uid: frozenset(days) for uid, days in leaves.items()},
        project_start=inputs.project_start,
    )
    return new_inputs, applied, errors, removed, added


def _run(inputs: SimInputs) -> scheduling.ScheduleResult:
    return scheduling.compute_schedule(
        inputs.tasks, inputs.deps, project_start=inputs.project_start, leaves=inputs.leaves
    )


def _diff(
    baseline: scheduling.ScheduleResult,
    scenario: scheduling.ScheduleResult,
    by_id: dict[int, Task],
    added: list[dict],
) -> tuple[list[dict], int]:
    affected: list[dict] = []
    for tid, base in baseline.tasks.items():
        after = scenario.tasks.get(tid)
        if after is None:
            continue  # removed
        if base.start != after.start or base.end != after.end:
            task = by_id.get(tid)
            affected.append(
                {
                    "id": tid,
                    "title": task.title if task else f"task {tid}",
                    "assignee_name": task.assignee.name if task and task.assignee else None,
                    "baseline": {"start": base.start.isoformat(), "end": base.end.isoformat()},
                    "scenario": {"start": after.start.isoformat(), "end": after.end.isoformat()},
                    "delay_days": (after.end - base.end).days,
                    "became_critical": after.is_critical and not base.is_critical,
                }
            )
    added_names = {a["sim_id"]: a["title"] for a in added}
    for tid, after in scenario.tasks.items():
        if tid < 0:  # synthetic
            affected.append(
                {
                    "id": tid,
                    "title": added_names.get(tid, "added task"),
                    "assignee_name": None,
                    "baseline": None,
                    "scenario": {"start": after.start.isoformat(), "end": after.end.isoformat()},
                    "delay_days": 0,
                    "became_critical": after.is_critical,
                }
            )
    affected.sort(key=lambda a: (-a["delay_days"], a["id"]))
    delay = (scenario.project_end - baseline.project_end).days
    return affected, delay


# ---------------------------------------------------------------------------
# Mitigations: candidate generation + re-simulation ranking
# ---------------------------------------------------------------------------

def _mitigation_candidates(
    db: Session,
    inputs: SimInputs,
    scenario: scheduling.ScheduleResult,
    affected: list[dict],
    by_id: dict[int, Task],
) -> list[dict]:
    """Reassignment candidates: move the delayed tasks of each impacted assignee
    onto each other tester. Each candidate is re-simulated for real recovery."""
    delayed_real = [a for a in affected if a["id"] > 0 and a["delay_days"] > 0]
    if not delayed_real:
        return []
    impacted_users: dict[int, list[int]] = {}
    for a in delayed_real:
        task = by_id.get(a["id"])
        if task and task.assigned_to:
            impacted_users.setdefault(task.assigned_to, []).append(task.id)

    testers = db.scalars(
        select(User).where(User.role == UserRole.tester, User.is_active.is_(True))
    ).all()
    by_user = {u.id: u for u in testers}

    candidates = []
    for uid, task_ids in sorted(impacted_users.items()):
        for candidate in sorted(testers, key=lambda u: u.id):
            if candidate.id == uid:
                continue
            candidates.append(
                {
                    "from_user": by_user.get(uid).name if by_user.get(uid) else f"user {uid}",
                    "to_user": candidate.name,
                    "to_user_id": candidate.id,
                    "task_ids": sorted(task_ids),
                }
            )
    return candidates


def _score_mitigations(
    inputs: SimInputs,
    scenario_result: scheduling.ScheduleResult,
    candidates: list[dict],
    by_id: dict[int, Task],
) -> list[dict]:
    scored = []
    for cand in candidates:
        moved = set(cand["task_ids"])
        tasks = [
            replace(t, assignee_id=cand["to_user_id"]) if t.id in moved else t
            for t in inputs.tasks
        ]
        try:
            result = scheduling.compute_schedule(
                tasks, inputs.deps, project_start=inputs.project_start, leaves=inputs.leaves
            )
        except scheduling.CycleError:
            continue
        recovered = (scenario_result.project_end - result.project_end).days
        if recovered <= 0:
            continue
        titles = [by_id[tid].title for tid in cand["task_ids"] if tid in by_id]
        confidence = round(max(0.6, 0.9 - 0.05 * (len(moved) - 1)), 2)
        scored.append(
            {
                "explanation": (
                    f"Reassign {len(moved)} affected task(s) "
                    f"({', '.join(titles[:3])}{'…' if len(titles) > 3 else ''}) "
                    f"from {cand['from_user']} to {cand['to_user']} → recovers "
                    f"{recovered} day(s); scenario end moves "
                    f"{scenario_result.project_end} → {result.project_end}."
                ),
                "recovers_days": recovered,
                "new_project_end": result.project_end.isoformat(),
                "confidence": confidence,
                "apply": {
                    "kind": "update_tasks",
                    "tasks": [
                        {"id": tid, "fields": {"assigned_to": cand["to_user_id"]}}
                        for tid in cand["task_ids"]
                    ],
                },
            }
        )
    scored.sort(key=lambda m: (-m["recovers_days"], len(m["apply"]["tasks"]), m["explanation"]))
    for rank, m in enumerate(scored, start=1):
        m["rank"] = rank
    return scored[:MAX_MITIGATIONS]


# ---------------------------------------------------------------------------
# Entry point (used by the REST endpoint and the agent tool)
# ---------------------------------------------------------------------------

def run_simulation(db: Session, project_id=None, perturbations=None, **_) -> dict:
    """Non-destructive what-if. Read-only: the real plan is never modified."""
    if not isinstance(perturbations, list) or not perturbations:
        return {"error": "perturbations must be a non-empty list"}
    inputs, by_id = _load_inputs(db, int(project_id) if project_id else None)
    if not inputs.tasks:
        return {"error": "no scheduled tasks in scope (tasks need start and due dates)"}

    scenario_inputs, applied, errors, removed, added = _apply_perturbations(
        inputs, perturbations, by_id
    )
    if not applied:
        return {"error": "; ".join(errors) or "no valid perturbations"}

    try:
        baseline = _run(inputs)
        scenario = _run(scenario_inputs)
    except scheduling.CycleError as exc:
        return {"error": str(exc)}

    affected, delay = _diff(baseline, scenario, by_id, added)
    mitigations = (
        _score_mitigations(
            scenario_inputs, scenario,
            _mitigation_candidates(db, scenario_inputs, scenario, affected, by_id),
            by_id,
        )
        if delay > 0
        else []
    )

    if delay > 0:
        summary = (
            f"{len([a for a in affected if a['delay_days'] > 0])} task(s) slip; the plan's end "
            f"date moves {baseline.project_end} → {scenario.project_end} "
            f"(+{delay} day(s))."
        )
        if mitigations:
            summary += f" Best mitigation recovers {mitigations[0]['recovers_days']} day(s)."
    elif affected:
        summary = f"{len(affected)} task(s) change dates but the end date holds ({baseline.project_end})."
    else:
        summary = "No impact — the plan absorbs this scenario."

    return {
        "baseline": {
            "project_end": baseline.project_end.isoformat(),
            "critical_path": baseline.critical_path,
        },
        "scenario": {
            "project_end": scenario.project_end.isoformat(),
            "critical_path": [t for t in scenario.critical_path],
        },
        "predicted_delay_days": delay,
        "affected_tasks": affected,
        "removed_task_ids": removed,
        "added_tasks": added,
        "mitigations": mitigations,
        "perturbations_applied": applied,
        "warnings": errors,
        "summary": summary,
        "note": "Simulation only — nothing was changed. Apply a mitigation through the "
        "normal task endpoints.",
    }
