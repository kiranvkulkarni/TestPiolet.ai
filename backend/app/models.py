import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# ---------------------------------------------------------------------------
# Enumerations — exact string values; the AI agent and API depend on these.
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    manager = "manager"
    tester = "tester"
    viewer = "viewer"


class TaskType(str, enum.Enum):
    functional_sanity = "functional_sanity"
    functional_full_sanity = "functional_full_sanity"
    functional_feature_verification = "functional_feature_verification"
    functional_menu_tree = "functional_menu_tree"
    issue_reproduction = "issue_reproduction"
    fix_verification = "fix_verification"
    side_effect_verification = "side_effect_verification"
    nonfunc_kpi_launch_time = "nonfunc_kpi_launch_time"
    nonfunc_fps = "nonfunc_fps"
    nonfunc_memory_profiling = "nonfunc_memory_profiling"
    nonfunc_memory_leak = "nonfunc_memory_leak"
    nonfunc_power_consumption = "nonfunc_power_consumption"
    compliance_google_its = "compliance_google_its"
    compliance_google_cts = "compliance_google_cts"
    compliance_sensor_fusion = "compliance_sensor_fusion"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    blocked = "blocked"
    completed = "completed"
    cancelled = "cancelled"


class Priority(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class AutomationType(str, enum.Enum):
    manual = "manual"
    automated = "automated"
    both = "both"


class ProjectStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    on_hold = "on_hold"
    cancelled = "cancelled"


class TestCycleStatus(str, enum.Enum):
    planning = "planning"
    active = "active"
    completed = "completed"


class RequestStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class LeaveType(str, enum.Enum):
    planned = "planned"
    sick = "sick"
    emergency = "emergency"
    comp_off = "comp_off"


class LeaveStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


def _enum(e: type[enum.Enum]) -> Enum:
    # store enum *values* (the exact strings above), not python member names
    return Enum(e, values_callable=lambda x: [m.value for m in x], native_enum=False, length=50)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(_enum(UserRole), default=UserRole.tester)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_color: Mapped[str] = mapped_column(String(7), default="#6366f1")

    tasks: Mapped[list["Task"]] = relationship(
        back_populates="assignee", foreign_keys="Task.assigned_to"
    )
    leaves: Mapped[list["Leave"]] = relationship(
        back_populates="user", foreign_keys="Leave.user_id"
    )


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(_enum(ProjectStatus), default=ProjectStatus.active)
    color_hex: Mapped[str] = mapped_column(String(7), default="#3b82f6")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    test_cycles: Mapped[list["TestCycle"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    test_requests: Mapped[list["TestRequest"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class TestCycle(Base, TimestampMixin):
    __tablename__ = "test_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[TestCycleStatus] = mapped_column(
        _enum(TestCycleStatus), default=TestCycleStatus.planning
    )

    project: Mapped["Project"] = relationship(back_populates="test_cycles")
    test_requests: Mapped[list["TestRequest"]] = relationship(back_populates="test_cycle")


class TestRequest(Base, TimestampMixin):
    __tablename__ = "test_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    test_cycle_id: Mapped[int | None] = mapped_column(ForeignKey("test_cycles.id"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[Priority] = mapped_column(_enum(Priority), default=Priority.medium)
    status: Mapped[RequestStatus] = mapped_column(_enum(RequestStatus), default=RequestStatus.open)

    project: Mapped["Project"] = relationship(back_populates="test_requests")
    test_cycle: Mapped["TestCycle | None"] = relationship(back_populates="test_requests")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="test_request", cascade="all, delete-orphan"
    )


class DeviceModel(Base, TimestampMixin):
    __tablename__ = "device_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand: Mapped[str] = mapped_column(String(100), default="Samsung")
    series: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str] = mapped_column(String(150))
    os_version: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    tasks: Mapped[list["Task"]] = relationship(back_populates="device_model")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_request_id: Mapped[int] = mapped_column(ForeignKey("test_requests.id"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[TaskType] = mapped_column(
        _enum(TaskType), default=TaskType.functional_sanity
    )
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus), default=TaskStatus.pending)
    priority: Mapped[Priority] = mapped_column(_enum(Priority), default=Priority.medium)
    automation_type: Mapped[AutomationType] = mapped_column(
        _enum(AutomationType), default=AutomationType.manual
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_date: Mapped[date | None] = mapped_column(Date)
    estimated_hours: Mapped[float | None] = mapped_column(Float)
    actual_hours: Mapped[float | None] = mapped_column(Float)
    build_version: Mapped[str | None] = mapped_column(String(100))
    device_model_id: Mapped[int | None] = mapped_column(ForeignKey("device_models.id"))
    depends_on: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))

    test_request: Mapped["TestRequest"] = relationship(back_populates="tasks")
    assignee: Mapped["User | None"] = relationship(
        back_populates="tasks", foreign_keys=[assigned_to]
    )
    creator: Mapped["User | None"] = relationship(foreign_keys=[created_by])
    device_model: Mapped["DeviceModel | None"] = relationship(back_populates="tasks")
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class Leave(Base, TimestampMixin):
    __tablename__ = "leaves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    leave_type: Mapped[LeaveType] = mapped_column(_enum(LeaveType), default=LeaveType.planned)
    status: Mapped[LeaveStatus] = mapped_column(_enum(LeaveStatus), default=LeaveStatus.pending)
    reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    user: Mapped["User"] = relationship(back_populates="leaves", foreign_keys=[user_id])
    approver: Mapped["User | None"] = relationship(foreign_keys=[approved_by])


class Comment(Base, TimestampMixin):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)

    task: Mapped["Task"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship()


class Attachment(Base, TimestampMixin):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    filename: Mapped[str] = mapped_column(String(300))
    original_filename: Mapped[str] = mapped_column(String(300))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str | None] = mapped_column(String(150))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    task: Mapped["Task"] = relationship(back_populates="attachments")
    uploader: Mapped["User | None"] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(50))  # create / update / delete
    field_changed: Mapped[str | None] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User | None"] = relationship()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(50))  # task_assigned / status_change / leave / ...
    message: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship()
