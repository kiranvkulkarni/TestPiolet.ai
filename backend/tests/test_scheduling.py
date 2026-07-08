"""Unit tests for the pure scheduling engine. No DB, no framework."""

from datetime import date

import pytest

from app.scheduling import (
    CycleError,
    Dependency,
    SchedTask,
    add_working_days,
    compute_schedule,
    count_working_days,
    dependency_closure,
    next_working_day,
    push_dependents,
    subtract_working_days,
    task_span,
    topological_order,
    would_create_cycle,
)

# 2026-07-06 is a Monday
MON = date(2026, 7, 6)
TUE = date(2026, 7, 7)
WED = date(2026, 7, 8)
THU = date(2026, 7, 9)
FRI = date(2026, 7, 10)
SAT = date(2026, 7, 11)
SUN = date(2026, 7, 12)
MON2 = date(2026, 7, 13)
TUE2 = date(2026, 7, 14)
WED2 = date(2026, 7, 15)
THU2 = date(2026, 7, 16)
FRI2 = date(2026, 7, 17)


class TestCalendar:
    def test_next_working_day_skips_weekend(self):
        assert next_working_day(SAT) == MON2
        assert next_working_day(MON) == MON

    def test_next_working_day_skips_leave(self):
        assert next_working_day(MON, frozenset([MON, TUE])) == WED

    def test_add_working_days_across_weekend(self):
        assert add_working_days(FRI, 1) == MON2
        assert add_working_days(MON, 4) == FRI

    def test_subtract_working_days(self):
        assert subtract_working_days(MON2, 1) == FRI
        assert subtract_working_days(FRI, 4) == MON

    def test_count_working_days(self):
        assert count_working_days(MON, FRI) == 5
        assert count_working_days(MON, SUN) == 5
        assert count_working_days(FRI, MON) == 0
        assert count_working_days(MON, FRI, frozenset([WED])) == 4

    def test_task_span_snaps_and_spans(self):
        assert task_span(SAT, 2) == (MON2, TUE2)
        assert task_span(THU, 3) == (THU, MON2)  # Thu, Fri, Mon


class TestTopologicalOrder:
    def test_orders_chain(self):
        deps = [Dependency(1, 2), Dependency(2, 3)]
        assert topological_order([3, 1, 2], deps) == [1, 2, 3]

    def test_deterministic_tie_break_by_id(self):
        assert topological_order([3, 2, 1], []) == [1, 2, 3]

    def test_raises_on_cycle(self):
        deps = [Dependency(1, 2), Dependency(2, 3), Dependency(3, 1)]
        with pytest.raises(CycleError) as exc:
            topological_order([1, 2, 3], deps)
        assert set(exc.value.task_ids) == {1, 2, 3}

    def test_ignores_edges_outside_scope(self):
        deps = [Dependency(1, 2), Dependency(99, 1)]
        assert topological_order([1, 2], deps) == [1, 2]


class TestWouldCreateCycle:
    def test_self_edge(self):
        assert would_create_cycle([1], [], Dependency(1, 1)) is True

    def test_back_edge(self):
        deps = [Dependency(1, 2), Dependency(2, 3)]
        assert would_create_cycle([1, 2, 3], deps, Dependency(3, 1)) is True

    def test_valid_edge(self):
        deps = [Dependency(1, 2)]
        assert would_create_cycle([1, 2, 3], deps, Dependency(2, 3)) is False


class TestDependencyClosure:
    def test_connected_component(self):
        deps = [Dependency(1, 2), Dependency(2, 3), Dependency(10, 11)]
        assert dependency_closure(2, deps) == {1, 2, 3}
        assert dependency_closure(10, deps) == {10, 11}
        assert dependency_closure(42, deps) == {42}


class TestComputeSchedule:
    def test_chain_schedules_sequentially(self):
        tasks = [SchedTask(1, 2), SchedTask(2, 1), SchedTask(3, 2)]
        deps = [Dependency(1, 2), Dependency(2, 3)]
        result = compute_schedule(tasks, deps, project_start=MON)
        assert (result.tasks[1].start, result.tasks[1].end) == (MON, TUE)
        assert (result.tasks[2].start, result.tasks[2].end) == (WED, WED)
        assert (result.tasks[3].start, result.tasks[3].end) == (THU, FRI)
        assert result.critical_path == [1, 2, 3]
        assert result.project_end == FRI

    def test_parallel_paths_critical_is_longer(self):
        # 1 -> 2 (long) and 1 -> 3 (short), both -> 4
        tasks = [SchedTask(1, 1), SchedTask(2, 3), SchedTask(3, 1), SchedTask(4, 1)]
        deps = [Dependency(1, 2), Dependency(1, 3), Dependency(2, 4), Dependency(3, 4)]
        result = compute_schedule(tasks, deps, project_start=MON)
        assert result.critical_path == [1, 2, 4]
        assert result.tasks[3].is_critical is False
        assert result.tasks[3].slack_days == 2
        assert result.tasks[4].start == FRI

    def test_weekend_pushes_successor_to_monday(self):
        tasks = [SchedTask(1, 4), SchedTask(2, 1)]  # 1: Mon-Thu... wait Mon+4=Thu
        deps = [Dependency(1, 2)]
        result = compute_schedule(tasks, deps, project_start=TUE)
        # task 1: Tue,Wed,Thu,Fri → ends Fri; task 2 starts next working day = Monday
        assert result.tasks[1].end == FRI
        assert result.tasks[2].start == MON2

    def test_approved_leave_shifts_assignees_dates(self):
        # assignee 7 is on leave Wed+Thu; 2-day task starting Wed lands Fri+Mon
        tasks = [SchedTask(1, 2, fixed_start=WED, assignee_id=7)]
        leaves = {7: frozenset([WED, THU])}
        result = compute_schedule(tasks, [], project_start=MON, leaves=leaves)
        assert result.tasks[1].start == FRI
        assert result.tasks[1].end == MON2

    def test_leave_stretches_duration_over_gap(self):
        # 3-day task, assignee on leave Tue-Thu: Mon, then Fri, then Mon2
        tasks = [SchedTask(1, 3, assignee_id=7)]
        leaves = {7: frozenset([TUE, WED, THU])}
        result = compute_schedule(tasks, [], project_start=MON, leaves=leaves)
        assert result.tasks[1].start == MON
        assert result.tasks[1].end == MON2

    def test_fixed_start_is_start_no_earlier_than(self):
        tasks = [SchedTask(1, 1, fixed_start=WED), SchedTask(2, 1, fixed_start=MON)]
        deps = [Dependency(1, 2)]
        result = compute_schedule(tasks, deps, project_start=MON)
        # 2's fixed Monday is overridden by its predecessor finishing Wednesday
        assert result.tasks[1].start == WED
        assert result.tasks[2].start == THU

    def test_cycle_raises(self):
        tasks = [SchedTask(1, 1), SchedTask(2, 1)]
        deps = [Dependency(1, 2), Dependency(2, 1)]
        with pytest.raises(CycleError):
            compute_schedule(tasks, deps, project_start=MON)

    def test_deterministic(self):
        tasks = [SchedTask(i, (i % 3) + 1) for i in range(1, 8)]
        deps = [Dependency(1, 4), Dependency(2, 4), Dependency(3, 5), Dependency(4, 6), Dependency(5, 6), Dependency(6, 7)]
        a = compute_schedule(tasks, deps, project_start=MON)
        b = compute_schedule(tasks, deps, project_start=MON)
        assert a.tasks == b.tasks
        assert a.critical_path == b.critical_path


class TestPushDependents:
    def test_violated_dependent_is_pushed_keeping_duration(self):
        tasks = [SchedTask(1, 2), SchedTask(2, 2)]
        deps = [Dependency(1, 2)]
        # task 1 moved to Wed-Thu; task 2 currently Mon-Tue (now violated)
        spans = {1: (WED, THU), 2: (MON, TUE)}
        shifts = push_dependents(tasks, deps, spans, changed_id=1)
        assert len(shifts) == 1
        assert shifts[0].task_id == 2
        assert (shifts[0].start, shifts[0].end) == (FRI, MON2)

    def test_non_violated_dependent_untouched(self):
        tasks = [SchedTask(1, 1), SchedTask(2, 1)]
        deps = [Dependency(1, 2)]
        spans = {1: (MON, MON), 2: (FRI, FRI)}
        assert push_dependents(tasks, deps, spans, changed_id=1) == []

    def test_push_propagates_transitively(self):
        tasks = [SchedTask(1, 1), SchedTask(2, 1), SchedTask(3, 1)]
        deps = [Dependency(1, 2), Dependency(2, 3)]
        spans = {1: (WED, WED), 2: (MON, MON), 3: (TUE, TUE)}
        shifts = push_dependents(tasks, deps, spans, changed_id=1)
        by_id = {s.task_id: s for s in shifts}
        assert by_id[2].start == THU
        assert by_id[3].start == FRI

    def test_upstream_and_unrelated_tasks_never_move(self):
        tasks = [SchedTask(1, 1), SchedTask(2, 1), SchedTask(3, 1)]
        deps = [Dependency(1, 2)]
        # task 3 is unrelated and "violated-looking" vs nothing; task 1 is upstream
        spans = {1: (MON, MON), 2: (MON, MON), 3: (MON, MON)}
        shifts = push_dependents(tasks, deps, spans, changed_id=2)
        assert shifts == []

    def test_push_respects_leave_calendar(self):
        tasks = [SchedTask(1, 1), SchedTask(2, 1, assignee_id=7)]
        deps = [Dependency(1, 2)]
        spans = {1: (THU, THU), 2: (MON, MON)}
        leaves = {7: frozenset([FRI])}
        shifts = push_dependents(tasks, deps, spans, changed_id=1, leaves=leaves)
        assert shifts[0].start == MON2  # Friday is leave, weekend skipped
