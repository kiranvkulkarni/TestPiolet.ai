from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    AutomationType,
    DependencyType,
    LeaveStatus,
    LeaveType,
    Priority,
    ProjectStatus,
    RequestStatus,
    TaskStatus,
    TaskType,
    TestCycleStatus,
    UserRole,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Auth / users
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserBase(BaseModel):
    name: str
    email: str
    role: UserRole = UserRole.tester
    is_active: bool = True
    avatar_color: str = "#6366f1"


class UserCreate(UserBase):
    password: str = Field(min_length=6)


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    avatar_color: str | None = None
    password: str | None = Field(default=None, min_length=6)


class UserOut(ORMModel):
    id: int
    name: str
    email: str
    role: UserRole
    is_active: bool
    avatar_color: str
    created_at: datetime


class UserBrief(ORMModel):
    id: int
    name: str
    email: str
    avatar_color: str


class WorkloadOut(BaseModel):
    user_id: int
    name: str
    active_tasks: int
    estimated_hours: float
    by_status: dict[str, int]


# ---------------------------------------------------------------------------
# Projects / cycles / requests
# ---------------------------------------------------------------------------

class ProjectBase(BaseModel):
    name: str
    description: str | None = None
    status: ProjectStatus = ProjectStatus.active
    color_hex: str = "#3b82f6"
    start_date: date | None = None
    end_date: date | None = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    color_hex: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class ProjectOut(ORMModel, ProjectBase):
    id: int
    created_at: datetime


class TestCycleBase(BaseModel):
    project_id: int
    name: str
    start_date: date | None = None
    end_date: date | None = None
    status: TestCycleStatus = TestCycleStatus.planning


class TestCycleCreate(TestCycleBase):
    pass


class TestCycleUpdate(BaseModel):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: TestCycleStatus | None = None


class TestCycleOut(ORMModel, TestCycleBase):
    id: int
    created_at: datetime


class TestRequestBase(BaseModel):
    project_id: int
    test_cycle_id: int | None = None
    title: str
    description: str | None = None
    requested_by: str | None = None
    priority: Priority = Priority.medium
    status: RequestStatus = RequestStatus.open


class TestRequestCreate(TestRequestBase):
    pass


class TestRequestUpdate(BaseModel):
    test_cycle_id: int | None = None
    title: str | None = None
    description: str | None = None
    requested_by: str | None = None
    priority: Priority | None = None
    status: RequestStatus | None = None


class TestRequestOut(ORMModel, TestRequestBase):
    id: int
    created_at: datetime
    task_count: int = 0


# ---------------------------------------------------------------------------
# Device models
# ---------------------------------------------------------------------------

class DeviceModelBase(BaseModel):
    brand: str = "Samsung"
    series: str | None = None
    model_name: str
    os_version: str | None = None
    is_active: bool = True


class DeviceModelCreate(DeviceModelBase):
    pass


class DeviceModelUpdate(BaseModel):
    brand: str | None = None
    series: str | None = None
    model_name: str | None = None
    os_version: str | None = None
    is_active: bool | None = None


class DeviceModelOut(ORMModel, DeviceModelBase):
    id: int


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class TaskBase(BaseModel):
    test_request_id: int
    title: str
    description: str | None = None
    task_type: TaskType = TaskType.functional_sanity
    assigned_to: int | None = None
    status: TaskStatus = TaskStatus.pending
    priority: Priority = Priority.medium
    automation_type: AutomationType = AutomationType.manual
    start_date: date | None = None
    due_date: date | None = None
    completed_date: date | None = None
    estimated_hours: float | None = None
    actual_hours: float | None = None
    build_version: str | None = None
    device_model_id: int | None = None
    depends_on: int | None = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    test_request_id: int | None = None
    title: str | None = None
    description: str | None = None
    task_type: TaskType | None = None
    assigned_to: int | None = None
    status: TaskStatus | None = None
    priority: Priority | None = None
    automation_type: AutomationType | None = None
    start_date: date | None = None
    due_date: date | None = None
    completed_date: date | None = None
    estimated_hours: float | None = None
    actual_hours: float | None = None
    build_version: str | None = None
    device_model_id: int | None = None
    depends_on: int | None = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus
    actual_hours: float | None = None


class TaskBulkCreate(BaseModel):
    tasks: list[TaskCreate]


class TaskBulkUpdate(BaseModel):
    task_ids: list[int]
    update: TaskUpdate


class TaskOut(ORMModel, TaskBase):
    id: int
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime
    assignee: UserBrief | None = None
    device_model: DeviceModelOut | None = None


class GanttTaskOut(BaseModel):
    id: int
    title: str
    start_date: date
    due_date: date
    status: TaskStatus
    priority: Priority
    progress: float
    assigned_to: int | None
    assignee_name: str | None
    project_id: int | None
    project_name: str | None
    project_color: str | None
    test_request_id: int
    test_request_title: str
    depends_on: int | None  # legacy single FK (deprecated; see dependencies)
    dependencies: list[int] = []  # predecessor task ids (from task_dependencies)
    critical: bool = False
    slack_days: int = 0


# ---------------------------------------------------------------------------
# Dependencies & scheduling (E1)
# ---------------------------------------------------------------------------

class DependencyCreate(BaseModel):
    depends_on_task_id: int  # the predecessor: it must finish before this task starts
    type: DependencyType = DependencyType.finish_to_start


class DependencyOut(ORMModel):
    id: int
    from_task_id: int
    to_task_id: int
    type: DependencyType


class TaskMoveRequest(BaseModel):
    start_date: date
    keep_duration: bool = True


class TaskResizeRequest(BaseModel):
    due_date: date | None = None
    duration_days: int | None = Field(default=None, ge=1)


class RescheduleResult(BaseModel):
    task: "TaskOut"
    affected: list["TaskOut"]  # dependents that were shifted (excludes `task`)
    critical_path: list[int]


class DependencyResult(BaseModel):
    dependency: DependencyOut | None = None
    affected: list["TaskOut"] = []
    critical_path: list[int] = []


class LeaveConflictOut(BaseModel):
    has_conflict: bool
    conflicts: list[dict]


# ---------------------------------------------------------------------------
# Leaves
# ---------------------------------------------------------------------------

class LeaveBase(BaseModel):
    user_id: int
    start_date: date
    end_date: date
    leave_type: LeaveType = LeaveType.planned
    reason: str | None = None


class LeaveCreate(LeaveBase):
    pass


class LeaveUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    leave_type: LeaveType | None = None
    reason: str | None = None


class LeaveApprove(BaseModel):
    status: LeaveStatus


class LeaveOut(ORMModel, LeaveBase):
    id: int
    status: LeaveStatus
    approved_by: int | None = None
    user: UserBrief | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Comments / attachments
# ---------------------------------------------------------------------------

class CommentCreate(BaseModel):
    content: str


class CommentUpdate(BaseModel):
    content: str


class CommentOut(ORMModel):
    id: int
    task_id: int
    user_id: int
    content: str
    created_at: datetime
    user: UserBrief | None = None


class AttachmentOut(ORMModel):
    id: int
    task_id: int
    filename: str
    original_filename: str
    file_size: int
    mime_type: str | None = None
    uploaded_by: int | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class NotificationOut(ORMModel):
    id: int
    type: str
    message: str
    entity_type: str | None = None
    entity_id: int | None = None
    is_read: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardSummary(BaseModel):
    total_tasks: int
    pending: int
    in_progress: int
    blocked: int
    completed: int
    overdue: int
    active_projects: int
    open_requests: int
    team_size: int


# ---------------------------------------------------------------------------
# AI agent
# ---------------------------------------------------------------------------

class AgentMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(BaseModel):
    messages: list[AgentMessage]


class AgentChatResponse(BaseModel):
    reply: str
    actions: list[dict]


class AgentStatus(BaseModel):
    enabled: bool
    llm_reachable: bool
    model: str | None = None


TokenResponse.model_rebuild()
RescheduleResult.model_rebuild()
DependencyResult.model_rebuild()

