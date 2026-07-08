"""Tests for the E4 AI Planner's deterministic pipeline: validation, enrichment,
scheduling, and the explicit commit path. No LLM involved."""

from datetime import date, timedelta

from sqlalchemy import select

from app import agent_planner
from app.models import (
    AuditLog,
    Leave,
    LeaveStatus,
    LeaveType,
    Task,
    TaskDependency,
)
from app.models import TestRequest as TestRequestModel  # avoid pytest collecting it

MON = date(2030, 1, 1) + timedelta(days=(7 - date(2030, 1, 1).weekday()) % 7)
TUE = MON + timedelta(days=1)
WED = MON + timedelta(days=2)


def sample_raw(**overrides) -> dict:
    raw = {
        "requests": [
            {
                "title": "HDR pipeline verification",
                "priority": "high",
                "tasks": [
                    {
                        "ref": "t1",
                        "title": "HDR sanity",
                        "task_type": "functional_sanity",
                        "estimated_hours": 8,
                        "device": "S25 Ultra",
                    },
                    {
                        "ref": "t2",
                        "title": "HDR feature verification",
                        "task_type": "functional_feature_verification",
                        "estimated_hours": 16,
                        "depends_on_refs": ["t1"],
                    },
                ],
            },
            {
                "title": "Night Mode",
                "priority": "medium",
                "tasks": [
                    {
                        "ref": "t3",
                        "title": "Night Mode KPI",
                        "task_type": "nonfunc_kpi_launch_time",
                        "estimated_hours": 8,
                    }
                ],
            },
        ],
        "rationale": "Sanity gates feature verification; KPI runs in parallel.",
    }
    raw.update(overrides)
    return raw


class TestValidateAndEnrich:
    def test_happy_path_schedules_and_assigns(self, db, seeded):
        draft = agent_planner.validate_and_enrich(
            db, sample_raw(), project_id=seeded["project"].id, start_date=MON
        )
        flat = [t for r in draft["requests"] for t in r["tasks"]]
        assert len(flat) == 3
        # everyone got an assignee and scheduled dates
        assert all(t["assigned_to"] for t in flat)
        assert all(t["start_date"] and t["due_date"] for t in flat)
        # t2 starts after t1 ends (finish-to-start)
        t1 = next(t for t in flat if t["ref"] == "t1")
        t2 = next(t for t in flat if t["ref"] == "t2")
        assert t2["start_date"] > t1["due_date"]
        # device resolved by name
        assert t1["device_model_id"] == seeded["device"].id
        assert draft["project_end"] >= t2["due_date"]
        assert draft["rationale"]

    def test_invalid_enum_fixed_with_warning(self, db, seeded):
        raw = sample_raw()
        raw["requests"][0]["tasks"][0]["task_type"] = "smoke_test"
        draft = agent_planner.validate_and_enrich(db, raw, project_id=seeded["project"].id)
        t1 = draft["requests"][0]["tasks"][0]
        assert t1["task_type"] == agent_planner.DEFAULT_TASK_TYPE
        assert any("smoke_test" in w for w in draft["warnings"])

    def test_unknown_device_warned(self, db, seeded):
        raw = sample_raw()
        raw["requests"][0]["tasks"][0]["device"] = "iPhone 17"
        draft = agent_planner.validate_and_enrich(db, raw, project_id=seeded["project"].id)
        assert draft["requests"][0]["tasks"][0]["device_model_id"] is None
        assert any("iPhone 17" in w for w in draft["warnings"])

    def test_cycle_edges_dropped_with_warning(self, db, seeded):
        raw = sample_raw()
        raw["requests"][0]["tasks"][0]["depends_on_refs"] = ["t2"]  # t1↔t2 cycle
        draft = agent_planner.validate_and_enrich(db, raw, project_id=seeded["project"].id)
        assert any("cycle" in w for w in draft["warnings"])
        flat = [t for r in draft["requests"] for t in r["tasks"]]
        edges = {(d, t["ref"]) for t in flat for d in t["depends_on_refs"]}
        # exactly one direction survives (first-seen edge wins), never both
        assert len(edges & {("t1", "t2"), ("t2", "t1")}) == 1

    def test_balanced_assignment_prefers_less_loaded(self, db, seeded):
        # Ravi (4h active) should get work before Priya (8h active)
        raw = {
            "requests": [
                {
                    "title": "One task",
                    "tasks": [{"ref": "a", "title": "Solo", "task_type": "functional_sanity",
                               "estimated_hours": 8}],
                }
            ]
        }
        draft = agent_planner.validate_and_enrich(db, raw, project_id=seeded["project"].id)
        assert draft["requests"][0]["tasks"][0]["assignee_name"] == "Ravi"

    def test_explicit_assignment_respected(self, db, seeded):
        raw = sample_raw()
        raw["requests"][0]["tasks"][0]["assigned_to"] = seeded["priya"].id
        draft = agent_planner.validate_and_enrich(db, raw, project_id=seeded["project"].id)
        assert draft["requests"][0]["tasks"][0]["assignee_name"] == "Priya"

    def test_leave_stretches_schedule_and_warns(self, db, seeded):
        db.add(Leave(user_id=seeded["ravi"].id, start_date=MON, end_date=TUE,
                     leave_type=LeaveType.planned, status=LeaveStatus.approved))
        db.add(Leave(user_id=seeded["priya"].id, start_date=MON, end_date=TUE,
                     leave_type=LeaveType.planned, status=LeaveStatus.approved))
        db.commit()
        raw = {
            "requests": [
                {"title": "R", "tasks": [{"ref": "a", "title": "During leave",
                                          "task_type": "functional_sanity", "estimated_hours": 8}]}
            ]
        }
        draft = agent_planner.validate_and_enrich(db, raw, start_date=MON)
        task = draft["requests"][0]["tasks"][0]
        assert task["start_date"] == WED.isoformat()  # snapped past everyone's leave

    def test_empty_draft_flagged(self, db, seeded):
        draft = agent_planner.validate_and_enrich(db, {"requests": []})
        assert any("no tasks" in w for w in draft["warnings"])


class TestCommitPlan:
    def _reviewed_draft(self, db, seeded) -> dict:
        return agent_planner.validate_and_enrich(
            db, sample_raw(), project_id=seeded["project"].id, start_date=MON
        )

    def test_commit_creates_everything_with_audit(self, db, seeded):
        draft = self._reviewed_draft(db, seeded)
        result = agent_planner.commit_plan(db, draft, seeded["manager"].id)
        assert "error" not in result
        assert len(result["request_ids"]) == 2
        assert len(result["task_ids"]) == 3
        assert result["dependency_count"] == 1
        # tasks really exist with scheduled dates + assignees
        t = db.get(Task, result["task_ids"][0])
        assert t.start_date is not None and t.assigned_to is not None
        # dependency row exists
        dep = db.scalar(select(TaskDependency).where(
            TaskDependency.to_task_id.in_(result["task_ids"])))
        assert dep is not None
        # audit: request marked as AI-planner-created, tasks marked [AI]
        req_audit = db.scalar(select(AuditLog).where(
            AuditLog.entity_type == "test_request",
            AuditLog.entity_id == result["request_ids"][0]))
        assert "[AI planner]" in req_audit.new_value
        assert result["rationale"].startswith("Committed 3 tasks")

    def test_nothing_written_before_commit(self, db, seeded):
        before_requests = db.scalars(select(TestRequestModel)).all()
        before_tasks = db.scalars(select(Task)).all()
        self._reviewed_draft(db, seeded)  # generate + validate only
        assert len(db.scalars(select(TestRequestModel)).all()) == len(before_requests)
        assert len(db.scalars(select(Task)).all()) == len(before_tasks)

    def test_commit_rejects_missing_project(self, db, seeded):
        draft = self._reviewed_draft(db, seeded)
        draft["project_id"] = None
        assert "error" in agent_planner.commit_plan(db, draft, seeded["manager"].id)

    def test_commit_rejects_cycles(self, db, seeded):
        draft = self._reviewed_draft(db, seeded)
        # sabotage the reviewed draft with a cycle
        flat = [t for r in draft["requests"] for t in r["tasks"]]
        t1 = next(t for t in flat if t["ref"] == "t1")
        t1["depends_on_refs"] = ["t2"]
        result = agent_planner.commit_plan(db, draft, seeded["manager"].id)
        assert "cycle" in result["error"]
        assert db.scalar(select(TestRequestModel).where(
            TestRequestModel.title == "HDR pipeline verification")) is None

    def test_commit_endpoint(self, client, db, seeded):
        draft = self._reviewed_draft(db, seeded)
        resp = client.post("/agent/plan/commit", json={"draft": draft})
        assert resp.status_code == 200
        assert len(resp.json()["task_ids"]) == 3

    def test_refresh_endpoint_is_deterministic_and_writes_nothing(self, client, db, seeded):
        draft = self._reviewed_draft(db, seeded)
        before_tasks = len(db.scalars(select(Task)).all())
        resp = client.post("/agent/plan/refresh", json={"draft": draft})
        assert resp.status_code == 200
        assert len(db.scalars(select(Task)).all()) == before_tasks
        flat = [t for r in resp.json()["requests"] for t in r["tasks"]]
        assert len(flat) == 3

    def test_plan_endpoint_503_when_agent_disabled(self, client):
        resp = client.post("/agent/plan", json={"brief": "Camera v16 next week: HDR + Night Mode"})
        assert resp.status_code == 503
