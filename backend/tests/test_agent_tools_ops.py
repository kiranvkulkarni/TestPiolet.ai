"""Tests for the E3 Operations Assistant tools: explainability (rationale +
confidence + undo), the 5+ confirmation gate, and the scheduling behavior."""

from datetime import date, timedelta

from sqlalchemy import select

from app import agent_tools
from app.models import (
    AuditLog,
    Leave,
    LeaveStatus,
    LeaveType,
    Task,
    TaskDependency,
    TaskType,
)

# fixed far-future Monday (same trick as the endpoint tests)
MON = date(2030, 1, 1) + timedelta(days=(7 - date(2030, 1, 1).weekday()) % 7)
TUE = MON + timedelta(days=1)
WED = MON + timedelta(days=2)
THU = MON + timedelta(days=3)
FRI = MON + timedelta(days=4)
MON2 = MON + timedelta(days=7)


def make_task(db, seeded, title, start=None, due=None, assignee=None, est=None):
    task = Task(
        test_request_id=seeded["request"].id,
        title=title,
        task_type=TaskType.functional_sanity,
        start_date=start,
        due_date=due,
        assigned_to=assignee,
        estimated_hours=est,
    )
    db.add(task)
    db.commit()
    return task


class TestRescheduleTasks:
    def test_moves_and_explains(self, db, seeded):
        t = make_task(db, seeded, "R1", MON, TUE)
        result = agent_tools.reschedule_tasks(
            db, current_user_id=seeded["manager"].id,
            task_ids=[t.id], start_date=WED.isoformat(),
        )
        assert result["rescheduled"][0]["start_date"] == WED.isoformat()
        assert result["rescheduled"][0]["due_date"] == THU.isoformat()  # 2 working days kept
        assert "rationale" in result and "working calendar" in result["rationale"]
        assert 0 < result["confidence"] <= 1
        assert result["undo"]["kind"] == "update_tasks"
        assert result["undo"]["tasks"][0]["fields"]["start_date"] == MON.isoformat()
        # audit rows with the [AI] marker
        audits = db.scalars(
            select(AuditLog).where(AuditLog.entity_id == t.id, AuditLog.entity_type == "task")
        ).all()
        assert any("[AI]" in (a.new_value or "") for a in audits)

    def test_respects_leave_and_lowers_confidence(self, db, seeded):
        t = make_task(db, seeded, "R2", MON, TUE, assignee=seeded["ravi"].id)
        db.add(Leave(user_id=seeded["ravi"].id, start_date=WED, end_date=THU,
                     leave_type=LeaveType.planned, status=LeaveStatus.approved))
        db.commit()
        result = agent_tools.reschedule_tasks(
            db, task_ids=[t.id], start_date=WED.isoformat(),
        )
        # Wed+Thu are leave → lands Fri, spills to Monday
        assert result["rescheduled"][0]["start_date"] == FRI.isoformat()
        assert result["rescheduled"][0]["due_date"] == MON2.isoformat()
        assert "leave" in result["rationale"]
        assert result["confidence"] < 0.9

    def test_pushes_dependents(self, db, seeded):
        a = make_task(db, seeded, "RA", MON, TUE)
        b = make_task(db, seeded, "RB", WED, WED)
        db.add(TaskDependency(from_task_id=a.id, to_task_id=b.id))
        db.commit()
        result = agent_tools.reschedule_tasks(db, task_ids=[a.id], start_date=WED.isoformat())
        assert [p["id"] for p in result["pushed_dependents"]] == [b.id]
        db.refresh(b)
        assert b.start_date == FRI

    def test_confirmation_gate_at_five(self, db, seeded):
        ids = [make_task(db, seeded, f"G{i}", MON, MON).id for i in range(5)]
        result = agent_tools.reschedule_tasks(db, task_ids=ids, start_date=WED.isoformat())
        assert result["needs_confirmation"] is True
        assert len(result["plan"]) == 5
        # nothing committed
        assert db.get(Task, ids[0]).start_date == MON
        # explicit confirm commits
        result = agent_tools.reschedule_tasks(
            db, task_ids=ids, start_date=WED.isoformat(), confirm=True
        )
        assert len(result["rescheduled"]) == 5
        assert db.get(Task, ids[0]).start_date == WED

    def test_unknown_ids_error(self, db, seeded):
        assert "error" in agent_tools.reschedule_tasks(
            db, task_ids=[99999], start_date=MON.isoformat()
        )


class TestDependencyTools:
    def test_set_dependency_pushes_and_explains(self, db, seeded):
        a = make_task(db, seeded, "DA", WED, THU)
        b = make_task(db, seeded, "DB", MON, MON)
        result = agent_tools.set_dependency(
            db, current_user_id=seeded["manager"].id, from_task_id=a.id, to_task_id=b.id
        )
        assert result["dependency"]["from_task_id"] == a.id
        assert [p["id"] for p in result["pushed_dependents"]] == [b.id]
        assert result["confidence"] == 0.85  # push happened
        db.refresh(b)
        assert b.start_date == FRI
        assert result["undo"]["kind"] == "remove_dependency"

    def test_set_dependency_rejects_cycle(self, db, seeded):
        a = make_task(db, seeded, "CA", MON, MON)
        b = make_task(db, seeded, "CB", TUE, TUE)
        assert "error" not in agent_tools.set_dependency(db, from_task_id=a.id, to_task_id=b.id)
        result = agent_tools.set_dependency(db, from_task_id=b.id, to_task_id=a.id)
        assert "cycle" in result["error"]

    def test_set_dependency_rejects_duplicate_and_self(self, db, seeded):
        a = make_task(db, seeded, "SA", MON, MON)
        b = make_task(db, seeded, "SB", TUE, TUE)
        agent_tools.set_dependency(db, from_task_id=a.id, to_task_id=b.id)
        assert "error" in agent_tools.set_dependency(db, from_task_id=a.id, to_task_id=b.id)
        assert "error" in agent_tools.set_dependency(db, from_task_id=a.id, to_task_id=a.id)

    def test_remove_dependency(self, db, seeded):
        a = make_task(db, seeded, "XA", MON, MON)
        b = make_task(db, seeded, "XB", TUE, TUE)
        agent_tools.set_dependency(db, from_task_id=a.id, to_task_id=b.id)
        result = agent_tools.remove_dependency(db, from_task_id=a.id, to_task_id=b.id)
        assert result["removed"]["from_task_id"] == a.id
        assert result["undo"]["kind"] == "add_dependency"
        assert "error" in agent_tools.remove_dependency(db, from_task_id=a.id, to_task_id=b.id)


class TestAssignBulk:
    def test_balances_by_load_and_explains(self, db, seeded):
        # active load from the seed: Priya 8h (her completed 16h doesn't count), Ravi 4h
        t1 = make_task(db, seeded, "B1", MON, TUE, est=8)
        t2 = make_task(db, seeded, "B2", MON, TUE, est=8)
        result = agent_tools.assign_bulk(
            db, current_user_id=seeded["manager"].id, task_ids=[t1.id, t2.id]
        )
        # first 8h task goes to Ravi (4h < 8h), second to Priya (8h < Ravi's new 12h)
        names = {a["assignee_name"] for a in result["assigned"]}
        assert names == {"Ravi", "Priya"}
        assert "loads (h)" in result["rationale"]
        assert result["undo"]["kind"] == "update_tasks"

    def test_exclusion_moves_work_off_someone(self, db, seeded):
        t = make_task(db, seeded, "B3", MON, TUE, est=8)
        result = agent_tools.assign_bulk(
            db, task_ids=[t.id], exclude_user_ids=[seeded["ravi"].id]
        )
        assert result["assigned"][0]["assignee_name"] == "Priya"

    def test_avoids_leave_conflicts(self, db, seeded):
        db.add(Leave(user_id=seeded["ravi"].id, start_date=MON, end_date=FRI,
                     leave_type=LeaveType.planned, status=LeaveStatus.approved))
        db.commit()
        t = make_task(db, seeded, "B4", MON, TUE, est=8)
        result = agent_tools.assign_bulk(db, task_ids=[t.id])
        # Ravi is least loaded but on leave for the whole window → Priya gets it
        assert result["assigned"][0]["assignee_name"] == "Priya"
        assert "avoided" in result["rationale"]
        assert result["confidence"] == 0.85

    def test_confirmation_gate(self, db, seeded):
        ids = [make_task(db, seeded, f"BC{i}", MON, MON, est=4).id for i in range(6)]
        result = agent_tools.assign_bulk(db, task_ids=ids)
        assert result["needs_confirmation"] is True
        assert all(db.get(Task, i).assigned_to is None for i in ids)
        result = agent_tools.assign_bulk(db, task_ids=ids, confirm=True)
        assert len(result["assigned"]) == 6


class TestReadTools:
    def test_get_critical_path_orders_chain(self, db, seeded):
        a = make_task(db, seeded, "P1", MON, TUE)
        b = make_task(db, seeded, "P2", WED, WED)
        db.add(TaskDependency(from_task_id=a.id, to_task_id=b.id))
        db.commit()
        result = agent_tools.get_critical_path(db, project_id=seeded["project"].id)
        ids = [p["id"] for p in result["critical_path"]]
        assert ids.index(a.id) < ids.index(b.id)
        assert result["project_end"]
        assert "zero slack" in result["summary"]

    def test_find_underloaded_testers(self, db, seeded):
        # Priya 24h vs Ravi 4h (seed) → below-average = Ravi
        result = agent_tools.find_underloaded_testers(db)
        names = [u["name"] for u in result["underloaded"]]
        assert "Ravi" in names and "Priya" not in names
        assert result["underloaded"][0]["headroom_hours"] > 0

    def test_find_underloaded_with_threshold(self, db, seeded):
        result = agent_tools.find_underloaded_testers(db, threshold_hours=100)
        assert len(result["underloaded"]) == 2  # everyone under 100h


class TestCreateBulkConfirmGate:
    def test_create_tasks_bulk_gate(self, db, seeded):
        items = [
            {"test_request_id": seeded["request"].id, "title": f"Bulk {i}"} for i in range(5)
        ]
        result = agent_tools.create_tasks_bulk(db, tasks=items)
        assert result["needs_confirmation"] is True
        result = agent_tools.create_tasks_bulk(db, tasks=items, confirm=True)
        assert result["created_count"] == 5
        assert result["undo"]["kind"] == "delete_tasks"


class TestRestMirrors:
    def test_reschedule_endpoint(self, client, db, seeded):
        t = make_task(db, seeded, "M1", MON, TUE)
        resp = client.post(
            "/tasks/reschedule",
            json={"task_ids": [t.id], "start_date": WED.isoformat()},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rescheduled"][0]["start_date"] == WED.isoformat()
        assert "rationale" in body

    def test_assign_balanced_endpoint(self, client, db, seeded):
        t = make_task(db, seeded, "M2", MON, TUE, est=8)
        resp = client.post("/tasks/assign-balanced", json={"task_ids": [t.id]})
        assert resp.status_code == 200
        assert resp.json()["assigned"][0]["assignee_name"] == "Ravi"

    def test_critical_path_endpoint(self, client, db, seeded):
        resp = client.get(f"/tasks/critical-path?project_id={seeded['project'].id}")
        assert resp.status_code == 200
        assert "critical_path" in resp.json()

    def test_underloaded_endpoint(self, client, seeded):
        resp = client.get("/users/underloaded")
        assert resp.status_code == 200
        assert "underloaded" in resp.json()

    def test_reschedule_endpoint_error_maps_to_400(self, client, seeded):
        resp = client.post(
            "/tasks/reschedule", json={"task_ids": [99999], "start_date": MON.isoformat()}
        )
        assert resp.status_code == 400
