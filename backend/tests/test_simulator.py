"""Tests for the E5 Timeline Simulator: perturbations, diffing, mitigation
ranking, determinism, and — critically — that the real plan is never touched."""

from datetime import date, timedelta

from sqlalchemy import select

from app import simulator
from app.models import Task, TaskDependency, TaskType

MON = date(2030, 1, 1) + timedelta(days=(7 - date(2030, 1, 1).weekday()) % 7)
TUE = MON + timedelta(days=1)
WED = MON + timedelta(days=2)
THU = MON + timedelta(days=3)
FRI = MON + timedelta(days=4)


def make_task(db, seeded, title, start, due, assignee=None, est=None):
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


def snapshot(db):
    return {
        t.id: (t.start_date, t.due_date, t.assigned_to)
        for t in db.scalars(select(Task)).all()
    }


class TestLeavePerturbation:
    def test_priya_out_delays_her_tasks_and_plan_untouched(self, db, seeded):
        # Priya's chain: A (Mon-Tue) -> B (Wed-Thu), both hers
        a = make_task(db, seeded, "Sim A", MON, TUE, assignee=seeded["priya"].id)
        b = make_task(db, seeded, "Sim B", WED, THU, assignee=seeded["priya"].id)
        db.add(TaskDependency(from_task_id=a.id, to_task_id=b.id))
        db.commit()
        before = snapshot(db)

        result = simulator.run_simulation(
            db,
            project_id=seeded["project"].id,
            perturbations=[{
                "type": "leave", "user_id": seeded["priya"].id,
                "start_date": MON.isoformat(), "end_date": TUE.isoformat(),
            }],
        )
        assert "error" not in result
        affected_ids = {t["id"] for t in result["affected_tasks"]}
        assert {a.id, b.id} <= affected_ids
        assert result["predicted_delay_days"] > 0
        assert "end date moves" in result["summary"]
        # the real plan is unchanged
        assert snapshot(db) == before

    def test_mitigations_ranked_with_explanations(self, db, seeded):
        a = make_task(db, seeded, "Mit A", MON, TUE, assignee=seeded["priya"].id)
        b = make_task(db, seeded, "Mit B", WED, THU, assignee=seeded["priya"].id)
        db.add(TaskDependency(from_task_id=a.id, to_task_id=b.id))
        db.commit()
        result = simulator.run_simulation(
            db,
            project_id=seeded["project"].id,
            perturbations=[{
                "type": "leave", "user_id": seeded["priya"].id,
                "start_date": MON.isoformat(), "end_date": FRI.isoformat(),
            }],
        )
        assert result["mitigations"], "expected reassignment mitigations"
        top = result["mitigations"][0]
        assert top["rank"] == 1
        assert top["recovers_days"] > 0
        assert "Reassign" in top["explanation"] and "recovers" in top["explanation"]
        assert 0.5 <= top["confidence"] <= 1
        # apply payload routes through normal endpoints (update_tasks shape)
        assert top["apply"]["kind"] == "update_tasks"
        assert all("assigned_to" in t["fields"] for t in top["apply"]["tasks"])
        # ranking is by recovery, descending
        recoveries = [m["recovers_days"] for m in result["mitigations"]]
        assert recoveries == sorted(recoveries, reverse=True)


class TestSlipPerturbation:
    def test_slip_pushes_dependent(self, db, seeded):
        a = make_task(db, seeded, "Slip A", MON, TUE)
        b = make_task(db, seeded, "Slip B", WED, WED)
        db.add(TaskDependency(from_task_id=a.id, to_task_id=b.id))
        db.commit()
        result = simulator.run_simulation(
            db,
            project_id=seeded["project"].id,
            perturbations=[{"type": "slip", "task_id": a.id, "days": 2}],
        )
        by_id = {t["id"]: t for t in result["affected_tasks"]}
        assert a.id in by_id and b.id in by_id
        assert by_id[b.id]["scenario"]["start"] > by_id[b.id]["baseline"]["start"]
        # DB untouched
        db.refresh(b)
        assert b.start_date == WED


class TestScopePerturbations:
    def test_remove_task_lifts_constraint(self, db, seeded):
        a = make_task(db, seeded, "Rem A", MON, THU)
        b = make_task(db, seeded, "Rem B", FRI, FRI)
        db.add(TaskDependency(from_task_id=a.id, to_task_id=b.id))
        db.commit()
        result = simulator.run_simulation(
            db,
            project_id=seeded["project"].id,
            perturbations=[{"type": "remove_task", "task_id": a.id}],
        )
        assert result["removed_task_ids"] == [a.id]
        assert db.get(Task, a.id) is not None  # still exists for real

    def test_add_task_appears_in_scenario(self, db, seeded):
        a = make_task(db, seeded, "Add A", MON, TUE)
        result = simulator.run_simulation(
            db,
            project_id=seeded["project"].id,
            perturbations=[{
                "type": "add_task", "title": "Extra CTS run",
                "estimated_hours": 16, "after_task_id": a.id,
            }],
        )
        synth = [t for t in result["affected_tasks"] if t["id"] < 0]
        assert len(synth) == 1
        assert synth[0]["title"] == "Extra CTS run"
        # scheduled after its predecessor
        assert synth[0]["scenario"]["start"] > TUE.isoformat()
        # nothing was created for real
        assert db.scalar(select(Task).where(Task.title == "Extra CTS run")) is None


class TestContract:
    def test_deterministic(self, db, seeded):
        make_task(db, seeded, "Det A", MON, TUE, assignee=seeded["priya"].id)
        perturbations = [{
            "type": "leave", "user_id": seeded["priya"].id,
            "start_date": MON.isoformat(), "end_date": WED.isoformat(),
        }]
        r1 = simulator.run_simulation(db, project_id=seeded["project"].id, perturbations=perturbations)
        r2 = simulator.run_simulation(db, project_id=seeded["project"].id, perturbations=perturbations)
        assert r1 == r2

    def test_rejects_empty_and_unknown(self, db, seeded):
        assert "error" in simulator.run_simulation(db, perturbations=[])
        result = simulator.run_simulation(
            db, project_id=seeded["project"].id,
            perturbations=[{"type": "meteor_strike"}],
        )
        assert "error" in result

    def test_no_impact_scenario_says_so(self, db, seeded):
        make_task(db, seeded, "Chill", MON, TUE, assignee=seeded["ravi"].id)
        result = simulator.run_simulation(
            db,
            project_id=seeded["project"].id,
            perturbations=[{
                # leave far away from any task
                "type": "leave", "user_id": seeded["ravi"].id,
                "start_date": (MON + timedelta(days=300)).isoformat(),
                "end_date": (MON + timedelta(days=302)).isoformat(),
            }],
        )
        assert result["predicted_delay_days"] == 0

    def test_endpoint_read_only(self, client, db, seeded):
        a = make_task(db, seeded, "Ep A", MON, TUE, assignee=seeded["priya"].id)
        before = snapshot(db)
        resp = client.post(
            "/simulations",
            json={
                "project_id": seeded["project"].id,
                "perturbations": [{
                    "type": "leave", "user_id": seeded["priya"].id,
                    "start_date": MON.isoformat(), "end_date": TUE.isoformat(),
                }],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "summary" in body and "affected_tasks" in body
        assert snapshot(db) == before

    def test_endpoint_400_on_bad_input(self, client, seeded):
        resp = client.post("/simulations", json={"perturbations": [{"type": "nope"}]})
        assert resp.status_code == 400
