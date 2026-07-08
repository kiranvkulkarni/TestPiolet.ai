"""Pure scheduling engine: topological ordering, forward/backward pass,
critical path, and working-day calendars (weekends + per-assignee leave).

Framework-free by design (no FastAPI/SQLAlchemy imports) so it can be unit-tested
in isolation and reused by the Gantt endpoints, the AI tools (E3) and the
Timeline Simulator (E5). All date math is deterministic.

Conventions
-----------
- Durations are in **working days** (>= 1). A task occupying a single working
  day has ``start == end``.
- A dependency ``from_task -> to_task`` is finish-to-start: the successor may
  start no earlier than the first working day after the predecessor ends.
- A task's calendar skips weekends plus the approved leave days of its assignee.
- ``fixed_start`` is a "start no earlier than" anchor (a user-chosen date).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

WEEKEND = (5, 6)  # Saturday, Sunday (date.weekday())


class CycleError(ValueError):
    """Raised when the dependency graph contains a cycle."""

    def __init__(self, task_ids: list[int]):
        self.task_ids = task_ids
        super().__init__(f"Dependency cycle involving tasks: {sorted(task_ids)}")


@dataclass(frozen=True)
class SchedTask:
    id: int
    duration_days: int = 1
    fixed_start: date | None = None
    assignee_id: int | None = None

    def __post_init__(self):
        if self.duration_days < 1:
            raise ValueError(f"Task {self.id}: duration_days must be >= 1")


@dataclass(frozen=True)
class Dependency:
    from_task_id: int
    to_task_id: int
    type: str = "finish_to_start"


@dataclass
class ScheduledTask:
    id: int
    start: date
    end: date
    slack_days: int
    is_critical: bool


@dataclass
class ScheduleResult:
    tasks: dict[int, ScheduledTask]
    critical_path: list[int]  # critical task ids in topological order
    project_end: date


# ---------------------------------------------------------------------------
# Calendars
# ---------------------------------------------------------------------------

def is_working_day(day: date, leave_days: frozenset[date] = frozenset()) -> bool:
    return day.weekday() not in WEEKEND and day not in leave_days


def next_working_day(day: date, leave_days: frozenset[date] = frozenset()) -> date:
    while not is_working_day(day, leave_days):
        day += timedelta(days=1)
    return day


def add_working_days(start: date, days: int, leave_days: frozenset[date] = frozenset()) -> date:
    """The date `days` working days after `start` (start itself not counted)."""
    day = start
    remaining = days
    while remaining > 0:
        day += timedelta(days=1)
        if is_working_day(day, leave_days):
            remaining -= 1
    return day


def subtract_working_days(end: date, days: int, leave_days: frozenset[date] = frozenset()) -> date:
    day = end
    remaining = days
    while remaining > 0:
        day -= timedelta(days=1)
        if is_working_day(day, leave_days):
            remaining -= 1
    return day


def count_working_days(start: date, end: date, leave_days: frozenset[date] = frozenset()) -> int:
    """Inclusive count of working days in [start, end]; 0 if end < start."""
    if end < start:
        return 0
    day, count = start, 0
    while day <= end:
        if is_working_day(day, leave_days):
            count += 1
        day += timedelta(days=1)
    return count


def task_span(start: date, duration_days: int, leave_days: frozenset[date] = frozenset()) -> tuple[date, date]:
    """Snap `start` to a working day and return (start, end) covering `duration_days`."""
    real_start = next_working_day(start, leave_days)
    end = add_working_days(real_start, duration_days - 1, leave_days)
    return real_start, end


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def topological_order(task_ids: list[int], dependencies: list[Dependency]) -> list[int]:
    """Kahn's algorithm; deterministic (ties broken by task id). Raises CycleError."""
    ids = set(task_ids)
    successors: dict[int, list[int]] = {tid: [] for tid in ids}
    in_degree: dict[int, int] = {tid: 0 for tid in ids}
    for dep in dependencies:
        if dep.from_task_id not in ids or dep.to_task_id not in ids:
            continue  # edge to a task outside this scope — ignore
        successors[dep.from_task_id].append(dep.to_task_id)
        in_degree[dep.to_task_id] += 1

    ready = sorted(tid for tid, deg in in_degree.items() if deg == 0)
    order: list[int] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        newly_ready = []
        for succ in successors[current]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                newly_ready.append(succ)
        ready = sorted(ready + newly_ready)

    if len(order) != len(ids):
        raise CycleError([tid for tid, deg in in_degree.items() if deg > 0])
    return order


def would_create_cycle(
    task_ids: list[int], dependencies: list[Dependency], new_edge: Dependency
) -> bool:
    if new_edge.from_task_id == new_edge.to_task_id:
        return True
    try:
        topological_order(task_ids, [*dependencies, new_edge])
        return False
    except CycleError:
        return True


def dependency_closure(start_id: int, dependencies: list[Dependency]) -> set[int]:
    """All task ids connected to `start_id` through dependency edges (any direction)."""
    neighbors: dict[int, set[int]] = {}
    for dep in dependencies:
        neighbors.setdefault(dep.from_task_id, set()).add(dep.to_task_id)
        neighbors.setdefault(dep.to_task_id, set()).add(dep.from_task_id)
    seen = {start_id}
    frontier = [start_id]
    while frontier:
        current = frontier.pop()
        for nxt in neighbors.get(current, ()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen


# ---------------------------------------------------------------------------
# CPM: forward + backward pass
# ---------------------------------------------------------------------------

def compute_schedule(
    tasks: list[SchedTask],
    dependencies: list[Dependency],
    project_start: date,
    leaves: dict[int, frozenset[date]] | None = None,
) -> ScheduleResult:
    """Forward/backward pass over the dependency DAG.

    - Earliest start = max(project_start, fixed_start, predecessors' end + 1),
      snapped to the assignee's next working day.
    - Slack is measured in the task's own working-day calendar; critical tasks
      have zero slack. Raises CycleError on cyclic dependencies.
    """
    leaves = leaves or {}
    by_id = {t.id: t for t in tasks}
    order = topological_order(list(by_id), dependencies)

    def cal(task: SchedTask) -> frozenset[date]:
        return leaves.get(task.assignee_id, frozenset()) if task.assignee_id else frozenset()

    predecessors: dict[int, list[int]] = {tid: [] for tid in by_id}
    successors: dict[int, list[int]] = {tid: [] for tid in by_id}
    for dep in dependencies:
        if dep.from_task_id in by_id and dep.to_task_id in by_id:
            predecessors[dep.to_task_id].append(dep.from_task_id)
            successors[dep.from_task_id].append(dep.to_task_id)

    # forward pass — earliest start/end
    early: dict[int, tuple[date, date]] = {}
    for tid in order:
        task = by_id[tid]
        earliest = project_start
        if task.fixed_start and task.fixed_start > earliest:
            earliest = task.fixed_start
        for pred in predecessors[tid]:
            candidate = early[pred][1] + timedelta(days=1)
            if candidate > earliest:
                earliest = candidate
        early[tid] = task_span(earliest, task.duration_days, cal(task))

    project_end = max(end for _start, end in early.values())

    # backward pass — latest start/end
    late: dict[int, tuple[date, date]] = {}
    for tid in reversed(order):
        task = by_id[tid]
        calendar = cal(task)
        if successors[tid]:
            latest_end = min(late[succ][0] - timedelta(days=1) for succ in successors[tid])
        else:
            latest_end = project_end
        # snap the latest end back onto a working day for this task
        while not is_working_day(latest_end, calendar):
            latest_end -= timedelta(days=1)
        latest_start = subtract_working_days(latest_end, task.duration_days - 1, calendar)
        late[tid] = (latest_start, latest_end)

    scheduled: dict[int, ScheduledTask] = {}
    for tid in order:
        task = by_id[tid]
        early_start, early_end = early[tid]
        late_start, _late_end = late[tid]
        slack = count_working_days(early_start, late_start, cal(task)) - 1
        slack = max(slack, 0)
        scheduled[tid] = ScheduledTask(
            id=tid,
            start=early_start,
            end=early_end,
            slack_days=slack,
            is_critical=slack == 0,
        )

    critical_path = [tid for tid in order if scheduled[tid].is_critical]
    return ScheduleResult(tasks=scheduled, critical_path=critical_path, project_end=project_end)


# ---------------------------------------------------------------------------
# Incremental reschedule (used by move/resize/link endpoints)
# ---------------------------------------------------------------------------

@dataclass
class Shift:
    task_id: int
    start: date
    end: date


def push_dependents(
    tasks: list[SchedTask],
    dependencies: list[Dependency],
    current_spans: dict[int, tuple[date, date]],
    changed_id: int,
    leaves: dict[int, frozenset[date]] | None = None,
) -> list[Shift]:
    """Forward-push only: after `changed_id` got new dates (already reflected in
    `current_spans`), shift downstream tasks just enough to satisfy
    finish-to-start constraints. Never pulls tasks earlier and never touches
    tasks that are not violated — user-set dates are preserved otherwise.
    """
    leaves = leaves or {}
    by_id = {t.id: t for t in tasks}
    order = topological_order(list(by_id), dependencies)
    predecessors: dict[int, list[int]] = {tid: [] for tid in by_id}
    successors: dict[int, list[int]] = {tid: [] for tid in by_id}
    for dep in dependencies:
        if dep.from_task_id in by_id and dep.to_task_id in by_id:
            predecessors[dep.to_task_id].append(dep.from_task_id)
            successors[dep.from_task_id].append(dep.to_task_id)

    # only tasks downstream of the change may be pushed
    downstream: set[int] = set()
    frontier = [changed_id]
    while frontier:
        for succ in successors.get(frontier.pop(), ()):
            if succ not in downstream:
                downstream.add(succ)
                frontier.append(succ)

    spans = dict(current_spans)
    shifts: list[Shift] = []
    for tid in order:
        if tid not in downstream or not predecessors[tid]:
            continue
        preds_with_dates = [spans[p] for p in predecessors[tid] if p in spans]
        if not preds_with_dates or tid not in spans:
            continue
        required_start = max(end for _s, end in preds_with_dates) + timedelta(days=1)
        current_start, current_end = spans[tid]
        if current_start >= required_start:
            continue  # not violated — leave the user's dates alone
        task = by_id[tid]
        calendar = leaves.get(task.assignee_id, frozenset()) if task.assignee_id else frozenset()
        duration = count_working_days(current_start, current_end, calendar) or task.duration_days
        new_start, new_end = task_span(required_start, duration, calendar)
        spans[tid] = (new_start, new_end)
        shifts.append(Shift(task_id=tid, start=new_start, end=new_end))
    return shifts
