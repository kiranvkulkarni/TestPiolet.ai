from datetime import timedelta

from app import agent_tools
from tests.conftest import TODAY


class TestGetTasks:
    def test_no_filters_returns_all(self, db, seeded):
        result = agent_tools.get_tasks(db)
        assert result["count"] == 4

    def test_filter_by_status(self, db, seeded):
        result = agent_tools.get_tasks(db, status="pending")
        assert result["count"] == 2
        assert all(t["status"] == "pending" for t in result["tasks"])

    def test_filter_by_assignee(self, db, seeded):
        priya = seeded["priya"]
        result = agent_tools.get_tasks(db, assigned_to=priya.id)
        assert result["count"] == 2
        assert all(t["assigned_to"] == priya.id for t in result["tasks"])

    def test_filter_overdue(self, db, seeded):
        result = agent_tools.get_tasks(db, overdue=True)
        assert result["count"] == 1
        assert result["tasks"][0]["title"] == "Fix verification #123"

    def test_combined_filters(self, db, seeded):
        result = agent_tools.get_tasks(db, status="pending", assigned_to=seeded["ravi"].id)
        assert result["count"] == 1


class TestGetWorkloadSummary:
    def test_counts_only_active_tasks(self, db, seeded):
        result = agent_tools.get_workload_summary(db)
        by_name = {w["name"]: w for w in result["workload"]}
        # Priya's completed task must not count toward load
        assert by_name["Priya"]["active_tasks"] == 1
        assert by_name["Priya"]["estimated_hours"] == 8.0
        assert by_name["Ravi"]["active_tasks"] == 1
        assert by_name["Ravi"]["estimated_hours"] == 4.0

    def test_includes_manager_with_zero_load(self, db, seeded):
        result = agent_tools.get_workload_summary(db)
        by_name = {w["name"]: w for w in result["workload"]}
        assert by_name["Manager"]["active_tasks"] == 0


class TestCheckLeaveConflicts:
    def test_overlap_detected(self, db, seeded):
        priya = seeded["priya"]
        result = agent_tools.check_leave_conflicts(
            db,
            user_id=priya.id,
            start_date=(TODAY + timedelta(days=6)).isoformat(),
            end_date=(TODAY + timedelta(days=9)).isoformat(),
        )
        assert result["has_conflict"] is True
        assert len(result["conflicts"]) == 1

    def test_no_overlap(self, db, seeded):
        priya = seeded["priya"]
        result = agent_tools.check_leave_conflicts(
            db,
            user_id=priya.id,
            start_date=(TODAY + timedelta(days=10)).isoformat(),
            end_date=(TODAY + timedelta(days=12)).isoformat(),
        )
        assert result["has_conflict"] is False

    def test_other_user_has_no_conflict(self, db, seeded):
        result = agent_tools.check_leave_conflicts(
            db,
            user_id=seeded["ravi"].id,
            start_date=(TODAY + timedelta(days=5)).isoformat(),
            end_date=(TODAY + timedelta(days=7)).isoformat(),
        )
        assert result["has_conflict"] is False

    def test_missing_args_returns_error(self, db, seeded):
        result = agent_tools.check_leave_conflicts(db, user_id=seeded["priya"].id)
        assert "error" in result

    def test_bad_date_format_returns_error(self, db, seeded):
        result = agent_tools.check_leave_conflicts(
            db, user_id=seeded["priya"].id, start_date="tomorrow", end_date="soon"
        )
        assert "error" in result
