from datetime import timedelta

from sqlalchemy import select

from app import agent_tools
from app.models import AuditLog, Notification, Task, TaskStatus
from tests.conftest import TODAY


class TestCreateTask:
    def test_creates_task_with_audit_and_notification(self, db, seeded):
        result = agent_tools.create_task(
            db,
            current_user_id=seeded["manager"].id,
            test_request_id=seeded["request"].id,
            title="Night Mode sanity",
            task_type="functional_sanity",
            priority="high",
            assigned_to=seeded["ravi"].id,
            device_model_id=seeded["device"].id,
            start_date=TODAY.isoformat(),
            due_date=(TODAY + timedelta(days=1)).isoformat(),
            estimated_hours=6,
        )
        assert "created" in result
        created = result["created"]
        assert created["title"] == "Night Mode sanity"
        assert created["assigned_to"] == seeded["ravi"].id

        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "task",
                AuditLog.entity_id == created["id"],
                AuditLog.action == "create",
            )
        )
        assert audit is not None
        assert audit.user_id == seeded["manager"].id

        notif = db.scalar(select(Notification).where(Notification.user_id == seeded["ravi"].id))
        assert notif is not None
        assert notif.type == "task_assigned"

    def test_rejects_unknown_test_request(self, db, seeded):
        result = agent_tools.create_task(db, test_request_id=9999, title="Ghost task")
        assert "error" in result
        assert db.scalar(select(Task).where(Task.title == "Ghost task")) is None

    def test_rejects_invalid_task_type(self, db, seeded):
        result = agent_tools.create_task(
            db, test_request_id=seeded["request"].id, title="Bad type", task_type="smoke_test"
        )
        assert "error" in result
        assert "valid_types" in result

    def test_rejects_unknown_assignee(self, db, seeded):
        result = agent_tools.create_task(
            db, test_request_id=seeded["request"].id, title="Bad assignee", assigned_to=9999
        )
        assert "error" in result

    def test_requires_title(self, db, seeded):
        result = agent_tools.create_task(db, test_request_id=seeded["request"].id, title="  ")
        assert "error" in result


class TestCreateTasksBulk:
    def test_creates_multiple(self, db, seeded):
        result = agent_tools.create_tasks_bulk(
            db,
            current_user_id=seeded["manager"].id,
            tasks=[
                {"test_request_id": seeded["request"].id, "title": "Bulk A"},
                {"test_request_id": seeded["request"].id, "title": "Bulk B", "priority": "low"},
            ],
        )
        assert result["created_count"] == 2
        audits = db.scalars(
            select(AuditLog).where(AuditLog.entity_type == "task", AuditLog.action == "create")
        ).all()
        assert len(audits) == 2

    def test_invalid_item_creates_nothing(self, db, seeded):
        before = db.scalars(select(Task)).all()
        result = agent_tools.create_tasks_bulk(
            db,
            tasks=[
                {"test_request_id": seeded["request"].id, "title": "OK"},
                {"test_request_id": 9999, "title": "Broken"},
            ],
        )
        assert "error" in result
        after = db.scalars(select(Task)).all()
        assert len(after) == len(before)

    def test_rejects_empty_list(self, db, seeded):
        assert "error" in agent_tools.create_tasks_bulk(db, tasks=[])
        assert "error" in agent_tools.create_tasks_bulk(db, tasks=None)


class TestUpdateTask:
    def test_status_change_writes_audit_and_sets_completed_date(self, db, seeded):
        task = seeded["tasks"][0]  # in_progress
        result = agent_tools.update_task(
            db, current_user_id=seeded["manager"].id, task_id=task.id, status="completed"
        )
        assert result["updated"]["status"] == "completed"
        db.refresh(task)
        assert task.status == TaskStatus.completed
        assert task.completed_date == TODAY

        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "task",
                AuditLog.entity_id == task.id,
                AuditLog.field_changed == "status",
            )
        )
        assert audit is not None
        assert audit.old_value == "in_progress"
        assert audit.new_value == "completed"

    def test_reassignment_notifies_new_assignee(self, db, seeded):
        task = seeded["tasks"][3]  # unassigned
        result = agent_tools.update_task(
            db,
            current_user_id=seeded["manager"].id,
            task_id=task.id,
            assigned_to=seeded["priya"].id,
        )
        assert "assigned_to" in result["changed_fields"]
        notif = db.scalar(
            select(Notification).where(Notification.user_id == seeded["priya"].id)
        )
        assert notif is not None

    def test_no_op_update_reports_no_changes(self, db, seeded):
        task = seeded["tasks"][0]
        result = agent_tools.update_task(db, task_id=task.id, status="in_progress")
        assert result.get("note") == "no changes applied"

    def test_rejects_unknown_task(self, db, seeded):
        assert "error" in agent_tools.update_task(db, task_id=9999, status="completed")

    def test_rejects_invalid_status(self, db, seeded):
        task = seeded["tasks"][0]
        assert "error" in agent_tools.update_task(db, task_id=task.id, status="done")

    def test_rejects_bad_date(self, db, seeded):
        task = seeded["tasks"][0]
        assert "error" in agent_tools.update_task(db, task_id=task.id, due_date="next friday")
