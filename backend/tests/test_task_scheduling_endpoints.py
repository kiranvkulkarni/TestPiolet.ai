"""API tests for the E1 scheduling endpoints: move / resize / link / unlink
and the enriched /tasks/gantt payload."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Leave, LeaveStatus, LeaveType, Task, TaskDependency, TaskType

# a fixed far-future Monday so weekend math is deterministic
MON = date(2030, 1, 1) + timedelta(days=(7 - date(2030, 1, 1).weekday()) % 7)
TUE = MON + timedelta(days=1)
WED = MON + timedelta(days=2)
THU = MON + timedelta(days=3)
FRI = MON + timedelta(days=4)
MON2 = MON + timedelta(days=7)
TUE2 = MON + timedelta(days=8)
WED2 = MON + timedelta(days=9)


@pytest.fixture()
def chain(db, seeded):
    """Two fresh dated tasks A (Mon-Tue) -> B (Wed) linked in task_dependencies."""
    a = Task(
        test_request_id=seeded["request"].id,
        title="Chain A",
        task_type=TaskType.functional_sanity,
        start_date=MON,
        due_date=TUE,
    )
    b = Task(
        test_request_id=seeded["request"].id,
        title="Chain B",
        task_type=TaskType.fix_verification,
        start_date=WED,
        due_date=WED,
    )
    db.add_all([a, b])
    db.flush()
    db.add(TaskDependency(from_task_id=a.id, to_task_id=b.id))
    db.commit()
    return {"a": a, "b": b}


class TestDependencyEndpoints:
    def test_link_creates_edge(self, client, db, seeded):
        t1, t2 = seeded["tasks"][0], seeded["tasks"][3]
        resp = client.post(
            f"/tasks/{t2.id}/dependencies", json={"depends_on_task_id": t1.id}
        )
        assert resp.status_code == 201
        dep = resp.json()["dependency"]
        assert dep["from_task_id"] == t1.id
        assert dep["to_task_id"] == t2.id

    def test_self_dependency_rejected(self, client, seeded):
        t = seeded["tasks"][0]
        resp = client.post(f"/tasks/{t.id}/dependencies", json={"depends_on_task_id": t.id})
        assert resp.status_code == 400

    def test_duplicate_rejected_with_409(self, client, chain):
        resp = client.post(
            f"/tasks/{chain['b'].id}/dependencies",
            json={"depends_on_task_id": chain["a"].id},
        )
        assert resp.status_code == 409

    def test_cycle_rejected_with_400(self, client, chain):
        # B -> A would close the loop A -> B -> A
        resp = client.post(
            f"/tasks/{chain['a'].id}/dependencies",
            json={"depends_on_task_id": chain["b"].id},
        )
        assert resp.status_code == 400
        assert "cycle" in resp.json()["detail"].lower()

    def test_unlink_removes_edge_and_clears_legacy_column(self, client, db, chain):
        b = chain["b"]
        b.depends_on = chain["a"].id  # legacy column mirroring this edge
        db.commit()
        dep = db.scalar(select(TaskDependency).where(TaskDependency.to_task_id == b.id))
        resp = client.delete(f"/tasks/{b.id}/dependencies/{dep.id}")
        assert resp.status_code == 200
        assert db.get(TaskDependency, dep.id) is None
        db.refresh(b)
        assert b.depends_on is None

    def test_unlink_unknown_dep_404(self, client, chain):
        resp = client.delete(f"/tasks/{chain['a'].id}/dependencies/99999")
        assert resp.status_code == 404

    def test_legacy_depends_on_update_mirrors_into_table(self, client, db, seeded):
        t1, t2 = seeded["tasks"][0], seeded["tasks"][3]
        resp = client.put(f"/tasks/{t2.id}", json={"depends_on": t1.id})
        assert resp.status_code == 200
        edge = db.scalar(
            select(TaskDependency).where(
                TaskDependency.from_task_id == t1.id, TaskDependency.to_task_id == t2.id
            )
        )
        assert edge is not None


class TestMoveEndpoint:
    def test_move_shifts_task_and_pushes_dependent(self, client, db, chain):
        a, b = chain["a"], chain["b"]
        resp = client.patch(f"/tasks/{a.id}/move", json={"start_date": WED.isoformat()})
        assert resp.status_code == 200
        body = resp.json()
        # A keeps its 2-day duration: Wed-Thu
        assert body["task"]["start_date"] == WED.isoformat()
        assert body["task"]["due_date"] == THU.isoformat()
        # B (was Wed) violates A's new end -> pushed to Friday
        affected = {t["id"]: t for t in body["affected"]}
        assert b.id in affected
        assert affected[b.id]["start_date"] == FRI.isoformat()
        assert body["critical_path"]  # recomputed
        db.refresh(b)
        assert b.start_date == FRI

    def test_move_snaps_weekend_start_to_monday(self, client, chain):
        a = chain["a"]
        saturday = FRI + timedelta(days=1)
        resp = client.patch(f"/tasks/{a.id}/move", json={"start_date": saturday.isoformat()})
        assert resp.status_code == 200
        assert resp.json()["task"]["start_date"] == MON2.isoformat()

    def test_move_respects_approved_leave(self, client, db, seeded, chain):
        a = chain["a"]
        a.assigned_to = seeded["ravi"].id
        db.add(
            Leave(
                user_id=seeded["ravi"].id,
                start_date=MON,
                end_date=TUE,
                leave_type=LeaveType.planned,
                status=LeaveStatus.approved,
            )
        )
        db.commit()
        resp = client.patch(f"/tasks/{a.id}/move", json={"start_date": MON.isoformat()})
        assert resp.status_code == 200
        # Mon+Tue are leave days: 2-day task lands Wed-Thu
        assert resp.json()["task"]["start_date"] == WED.isoformat()
        assert resp.json()["task"]["due_date"] == THU.isoformat()

    def test_pending_leave_does_not_shift_dates(self, client, db, seeded, chain):
        a = chain["a"]
        a.assigned_to = seeded["ravi"].id
        db.add(
            Leave(
                user_id=seeded["ravi"].id,
                start_date=MON,
                end_date=TUE,
                leave_type=LeaveType.planned,
                status=LeaveStatus.pending,
            )
        )
        db.commit()
        resp = client.patch(f"/tasks/{a.id}/move", json={"start_date": MON.isoformat()})
        assert resp.json()["task"]["start_date"] == MON.isoformat()


class TestResizeEndpoint:
    def test_resize_by_duration(self, client, chain):
        a = chain["a"]  # starts Monday
        resp = client.patch(f"/tasks/{a.id}/resize", json={"duration_days": 5})
        assert resp.status_code == 200
        assert resp.json()["task"]["due_date"] == FRI.isoformat()

    def test_resize_pushes_dependent(self, client, db, chain):
        a, b = chain["a"], chain["b"]
        resp = client.patch(f"/tasks/{a.id}/resize", json={"duration_days": 3})  # Mon-Wed
        affected = {t["id"]: t for t in resp.json()["affected"]}
        assert affected[b.id]["start_date"] == THU.isoformat()

    def test_resize_requires_exactly_one_arg(self, client, chain):
        a = chain["a"]
        assert client.patch(f"/tasks/{a.id}/resize", json={}).status_code == 400
        assert (
            client.patch(
                f"/tasks/{a.id}/resize",
                json={"duration_days": 2, "due_date": FRI.isoformat()},
            ).status_code
            == 400
        )

    def test_resize_rejects_due_before_start(self, client, chain):
        a = chain["a"]
        before = (MON - timedelta(days=3)).isoformat()
        assert client.patch(f"/tasks/{a.id}/resize", json={"due_date": before}).status_code == 400


class TestGanttEnrichment:
    def test_gantt_includes_dependencies_and_critical_flag(self, client, chain):
        resp = client.get("/tasks/gantt")
        assert resp.status_code == 200
        rows = {t["id"]: t for t in resp.json()}
        a, b = chain["a"], chain["b"]
        assert rows[b.id]["dependencies"] == [a.id]
        assert rows[a.id]["critical"] is True
        assert rows[b.id]["critical"] is True
        assert "slack_days" in rows[a.id]
