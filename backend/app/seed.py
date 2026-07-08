"""Demo data: 1 manager + 8 testers + devices + projects/requests + sample tasks.

Run with:  python -m app.seed
Idempotent-ish: refuses to run if users already exist.
"""

import random
from datetime import date, timedelta

from sqlalchemy import select

from .auth import hash_password
from .database import Base, SessionLocal, engine
from .models import (
    DeviceModel,
    Leave,
    LeaveStatus,
    LeaveType,
    Priority,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
    TaskType,
    TestCycle,
    TestCycleStatus,
    TestRequest,
    User,
    UserRole,
)

AVATAR_COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#06b6d4", "#3b82f6", "#8b5cf6", "#ec4899"]

TESTERS = [
    "Priya Sharma", "Ravi Kumar", "Anjali Desai", "Suresh Reddy",
    "Deepa Nair", "Arun Patil", "Kavya Iyer", "Manoj Singh",
]

DEVICES = [
    ("Galaxy S", "SM-S938B (Galaxy S25 Ultra)", "Android 15 / One UI 7"),
    ("Galaxy S", "SM-S931B (Galaxy S25)", "Android 15 / One UI 7"),
    ("Galaxy Z", "SM-F966B (Galaxy Z Fold6)", "Android 15 / One UI 7"),
    ("Galaxy Z", "SM-F741B (Galaxy Z Flip6)", "Android 15 / One UI 7"),
    ("Galaxy A", "SM-A566B (Galaxy A56)", "Android 15 / One UI 7"),
    ("Galaxy A", "SM-A366B (Galaxy A36)", "Android 15 / One UI 7"),
    ("Galaxy Tab", "SM-X926B (Galaxy Tab S10 Ultra)", "Android 15 / One UI 7"),
]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.scalar(select(User).limit(1)):
            print("Database already has users — skipping seed.")
            return

        # --- users ---------------------------------------------------------
        manager = User(
            name="QA Manager",
            email="admin@qa.local",
            password_hash=hash_password("admin123"),
            role=UserRole.manager,
            avatar_color="#6366f1",
        )
        db.add(manager)
        testers: list[User] = []
        for i, name in enumerate(TESTERS):
            first = name.split()[0].lower()
            tester = User(
                name=name,
                email=f"{first}@qa.local",
                password_hash=hash_password("tester123"),
                role=UserRole.tester,
                avatar_color=AVATAR_COLORS[i % len(AVATAR_COLORS)],
            )
            db.add(tester)
            testers.append(tester)

        # --- devices ---------------------------------------------------------
        devices: list[DeviceModel] = []
        for series, model_name, os_version in DEVICES:
            device = DeviceModel(
                brand="Samsung", series=series, model_name=model_name, os_version=os_version
            )
            db.add(device)
            devices.append(device)
        db.flush()

        today = date.today()

        # --- projects / cycles / requests -----------------------------------
        camera = Project(
            name="Camera v16 (One UI 8)",
            description="Camera app major update: HDR pipeline, Night Mode v3, Portrait Video.",
            status=ProjectStatus.active,
            color_hex="#3b82f6",
            start_date=today - timedelta(days=21),
            end_date=today + timedelta(days=45),
        )
        gallery = Project(
            name="Gallery MR2",
            description="Gallery maintenance release: shared albums, AI search fixes.",
            status=ProjectStatus.active,
            color_hex="#22c55e",
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=30),
        )
        db.add_all([camera, gallery])
        db.flush()

        cycle1 = TestCycle(
            project_id=camera.id,
            name="Sprint 3 regression",
            start_date=today - timedelta(days=7),
            end_date=today + timedelta(days=7),
            status=TestCycleStatus.active,
        )
        db.add(cycle1)
        db.flush()

        req_specs = [
            (camera.id, cycle1.id, "HDR pipeline verification — build R16.031", Priority.critical),
            (camera.id, cycle1.id, "Night Mode v3 feature verification", Priority.high),
            (camera.id, None, "Portrait Video side-effect check after fix #48213", Priority.high),
            (camera.id, None, "Camera KPI baseline — launch time & FPS", Priority.medium),
            (gallery.id, None, "Shared albums sanity — build G2.104", Priority.medium),
            (gallery.id, None, "Google CTS pre-check for MR2", Priority.high),
        ]
        requests: list[TestRequest] = []
        for project_id, cycle_id, title, priority in req_specs:
            req = TestRequest(
                project_id=project_id,
                test_cycle_id=cycle_id,
                title=title,
                requested_by="HQ Release Team",
                priority=priority,
            )
            db.add(req)
            requests.append(req)
        db.flush()

        # --- tasks -----------------------------------------------------------
        rng = random.Random(42)
        task_specs = [
            (0, "HDR sanity on S25 Ultra", TaskType.functional_sanity, TaskStatus.completed, Priority.critical, 8),
            (0, "HDR full sanity on Z Fold6", TaskType.functional_full_sanity, TaskStatus.in_progress, Priority.critical, 16),
            (0, "HDR scene-by-scene feature verification", TaskType.functional_feature_verification, TaskStatus.in_progress, Priority.high, 24),
            (0, "HDR menu tree sweep", TaskType.functional_menu_tree, TaskStatus.pending, Priority.medium, 12),
            (1, "Night Mode v3 verification — S25", TaskType.functional_feature_verification, TaskStatus.in_progress, Priority.high, 20),
            (1, "Night Mode low-light KPI capture", TaskType.nonfunc_kpi_launch_time, TaskStatus.pending, Priority.medium, 8),
            (1, "Night Mode memory profiling", TaskType.nonfunc_memory_profiling, TaskStatus.pending, Priority.medium, 12),
            (2, "Reproduce issue #48213 on Flip6", TaskType.issue_reproduction, TaskStatus.completed, Priority.high, 4),
            (2, "Verify fix #48213", TaskType.fix_verification, TaskStatus.in_progress, Priority.high, 6),
            (2, "Side-effect check around Portrait Video", TaskType.side_effect_verification, TaskStatus.pending, Priority.high, 10),
            (3, "Camera launch-time KPI — 5 devices", TaskType.nonfunc_kpi_launch_time, TaskStatus.pending, Priority.medium, 10),
            (3, "Preview FPS measurement", TaskType.nonfunc_fps, TaskStatus.pending, Priority.medium, 8),
            (3, "Power consumption during 4K recording", TaskType.nonfunc_power_consumption, TaskStatus.blocked, Priority.medium, 12),
            (4, "Shared albums sanity — A56", TaskType.functional_sanity, TaskStatus.in_progress, Priority.medium, 6),
            (4, "Shared albums memory-leak soak", TaskType.nonfunc_memory_leak, TaskStatus.pending, Priority.low, 16),
            (5, "Google CTS run — Tab S10 Ultra", TaskType.compliance_google_cts, TaskStatus.pending, Priority.high, 24),
            (5, "Google ITS camera compliance", TaskType.compliance_google_its, TaskStatus.pending, Priority.high, 16),
            (5, "Sensor fusion compliance check", TaskType.compliance_sensor_fusion, TaskStatus.pending, Priority.medium, 12),
        ]
        prev_task: Task | None = None
        for i, (req_idx, title, ttype, status, priority, est) in enumerate(task_specs):
            tester = testers[i % len(testers)]
            start = today + timedelta(days=rng.randint(-7, 5))
            duration = max(1, round(est / 6))
            task = Task(
                test_request_id=requests[req_idx].id,
                title=title,
                task_type=ttype,
                status=status,
                priority=priority,
                assigned_to=tester.id,
                created_by=manager.id,
                start_date=start,
                due_date=start + timedelta(days=duration),
                completed_date=start + timedelta(days=duration) if status == TaskStatus.completed else None,
                estimated_hours=float(est),
                actual_hours=float(est) * rng.uniform(0.8, 1.3) if status == TaskStatus.completed else None,
                build_version="R16.031" if req_idx < 4 else "G2.104",
                device_model_id=devices[i % len(devices)].id,
                depends_on=prev_task.id if (prev_task and req_idx in (0, 2) and i % 2 == 1) else None,
            )
            db.add(task)
            db.flush()
            prev_task = task

        # --- leaves ----------------------------------------------------------
        db.add_all(
            [
                Leave(
                    user_id=testers[0].id,
                    start_date=today + timedelta(days=3),
                    end_date=today + timedelta(days=5),
                    leave_type=LeaveType.planned,
                    status=LeaveStatus.approved,
                    reason="Family function",
                    approved_by=manager.id,
                ),
                Leave(
                    user_id=testers[3].id,
                    start_date=today + timedelta(days=10),
                    end_date=today + timedelta(days=14),
                    leave_type=LeaveType.planned,
                    status=LeaveStatus.pending,
                    reason="Vacation",
                ),
            ]
        )

        db.commit()
        print("Seeded: 1 manager, 8 testers, 7 devices, 2 projects, 6 requests, 18 tasks, 2 leaves.")
        print("Login: admin@qa.local / admin123  ·  testers: <first-name>@qa.local / tester123")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
