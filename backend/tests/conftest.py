"""Shared fixtures: an in-memory SQLite DB seeded with a small, known dataset."""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    DeviceModel,
    Leave,
    LeaveStatus,
    LeaveType,
    Priority,
    Project,
    Task,
    TaskStatus,
    TaskType,
    TestRequest,
    User,
    UserRole,
)

TODAY = date.today()


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def seeded(db: Session) -> dict:
    """1 manager + 2 testers, 1 device, 1 project/request, 4 tasks, 1 approved leave."""
    manager = User(
        name="Manager", email="mgr@test.local", password_hash="x", role=UserRole.manager
    )
    priya = User(name="Priya", email="priya@test.local", password_hash="x", role=UserRole.tester)
    ravi = User(name="Ravi", email="ravi@test.local", password_hash="x", role=UserRole.tester)
    device = DeviceModel(brand="Samsung", series="Galaxy S", model_name="SM-S938B")
    db.add_all([manager, priya, ravi, device])
    db.flush()

    project = Project(name="Camera v16")
    db.add(project)
    db.flush()
    request = TestRequest(project_id=project.id, title="HDR verification")
    db.add(request)
    db.flush()

    tasks = [
        # Priya: one in_progress (active), one completed (not active)
        Task(
            test_request_id=request.id,
            title="HDR sanity",
            task_type=TaskType.functional_sanity,
            status=TaskStatus.in_progress,
            priority=Priority.high,
            assigned_to=priya.id,
            estimated_hours=8.0,
            start_date=TODAY,
            due_date=TODAY + timedelta(days=2),
        ),
        Task(
            test_request_id=request.id,
            title="HDR full sanity",
            task_type=TaskType.functional_full_sanity,
            status=TaskStatus.completed,
            assigned_to=priya.id,
            estimated_hours=16.0,
        ),
        # Ravi: one pending overdue
        Task(
            test_request_id=request.id,
            title="Fix verification #123",
            task_type=TaskType.fix_verification,
            status=TaskStatus.pending,
            assigned_to=ravi.id,
            estimated_hours=4.0,
            start_date=TODAY - timedelta(days=5),
            due_date=TODAY - timedelta(days=2),
        ),
        # unassigned
        Task(
            test_request_id=request.id,
            title="CTS run",
            task_type=TaskType.compliance_google_cts,
            status=TaskStatus.pending,
        ),
    ]
    db.add_all(tasks)

    leave = Leave(
        user_id=priya.id,
        start_date=TODAY + timedelta(days=5),
        end_date=TODAY + timedelta(days=7),
        leave_type=LeaveType.planned,
        status=LeaveStatus.approved,
        approved_by=manager.id,
    )
    db.add(leave)
    db.commit()

    return {
        "manager": manager,
        "priya": priya,
        "ravi": ravi,
        "device": device,
        "project": project,
        "request": request,
        "tasks": tasks,
        "leave": leave,
    }
