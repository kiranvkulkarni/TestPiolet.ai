# Data Model

The actual schema, from `backend/app/models.py`. **Integer primary keys**, SQLAlchemy 2.0,
`created_at`/`updated_at` timestamps via `func.now()`. This is the source of truth; keep
it in sync when you change models. Schema changes ship with an **Alembic migration**
(ADR-0003, since E0) — see `backend/README.md` for the workflow.

## Hierarchy

```
Project
  ├── TestCycle          (optional grouping; a request may skip the cycle)
  └── TestRequest        (belongs to a Project, optionally to a TestCycle)
        └── Task         (belongs to a TestRequest)
              ├── Comment
              ├── Attachment
              └── TaskDependency (typed edges, many-to-many; source of truth
                                  since E1 — the old depends_on self-FK is
                                  deprecated and mirrored; see ADR-0005)
DeviceModel → Task       (a task can target one device)
User        → Task        (assignee, creator), Leave, Comment, Notification
```

## ER diagram

```mermaid
erDiagram
    USER ||--o{ TASK : "assigned / created"
    USER ||--o{ LEAVE : requests
    USER ||--o{ COMMENT : writes
    USER ||--o{ NOTIFICATION : receives
    PROJECT ||--o{ TEST_CYCLE : has
    PROJECT ||--o{ TEST_REQUEST : has
    TEST_CYCLE ||--o{ TEST_REQUEST : groups
    TEST_REQUEST ||--o{ TASK : contains
    TASK ||--o| TASK : depends_on
    TASK ||--o{ COMMENT : has
    TASK ||--o{ ATTACHMENT : has
    DEVICE_MODEL ||--o{ TASK : used_by

    USER { int id PK; string name; string email UK; string password_hash; enum role; bool is_active; string avatar_color }
    PROJECT { int id PK; string name; text description; enum status; string color_hex; date start_date; date end_date }
    TEST_CYCLE { int id PK; int project_id FK; string name; date start_date; date end_date; enum status }
    TEST_REQUEST { int id PK; int project_id FK; int test_cycle_id FK; string title; string requested_by; enum priority; enum status }
    TASK { int id PK; int test_request_id FK; string title; enum task_type; int assigned_to FK; enum status; enum priority; enum automation_type; date start_date; date due_date; date completed_date; float estimated_hours; float actual_hours; string build_version; int device_model_id FK; int depends_on FK }
    DEVICE_MODEL { int id PK; string brand; string series; string model_name; string os_version; bool is_active }
    LEAVE { int id PK; int user_id FK; date start_date; date end_date; enum leave_type; enum status; int approved_by FK }
    COMMENT { int id PK; int task_id FK; int user_id FK; text content }
    ATTACHMENT { int id PK; int task_id FK; string filename; string original_filename; int file_size; string mime_type; int uploaded_by FK }
    AUDIT_LOG { int id PK; string entity_type; int entity_id; string action; string field_changed; text old_value; text new_value; int user_id FK }
    NOTIFICATION { int id PK; int user_id FK; string type; text message; string entity_type; int entity_id; bool is_read; bool email_sent }
```

## Enumerations (exact string values — the AI and API depend on these)

- **UserRole:** `manager` · `tester` · `viewer`
- **TaskType (15):** `functional_sanity` · `functional_full_sanity` ·
  `functional_feature_verification` · `functional_menu_tree` · `issue_reproduction` ·
  `fix_verification` · `side_effect_verification` · `nonfunc_kpi_launch_time` ·
  `nonfunc_fps` · `nonfunc_memory_profiling` · `nonfunc_memory_leak` ·
  `nonfunc_power_consumption` · `compliance_google_its` · `compliance_google_cts` ·
  `compliance_sensor_fusion`
- **TaskStatus:** `pending` · `in_progress` · `blocked` · `completed` · `cancelled`
- **Priority:** `critical` · `high` · `medium` · `low`
- **AutomationType:** `manual` · `automated` · `both`
- **ProjectStatus:** `active` · `completed` · `on_hold` · `cancelled`
- **TestCycleStatus:** `planning` · `active` · `completed`
- **RequestStatus:** `open` · `in_progress` · `completed` · `cancelled`
- **LeaveType:** `planned` · `sick` · `emergency` · `comp_off`
- **LeaveStatus:** `pending` · `approved` · `rejected`
- **DependencyType:** `finish_to_start` (only type today; the table is ready for more)

## Notes & known limits (evolution targets)

- **Dependencies (since E1):** `task_dependencies` (`from_task_id` → `to_task_id`,
  typed, unique per edge, cycles rejected) is the source of truth. `Task.depends_on`
  is deprecated: reads should ignore it; legacy writes are mirrored into the table
  (ADR-0005). Drop it once nothing writes it (post-E3).
- **Scheduling (since E1):** `app/scheduling.py` (framework-free) computes derived
  start/end, slack and the critical path from durations + dependencies + working
  calendars (weekends + approved leave). Stored dates remain user-owned: the
  move/resize/link endpoints only push *violated* dependents forward, never pull
  dates earlier.
- **AuditLog exists but isn't uniformly written** — standardize writing it on mutations,
  including AI actions, as part of the Explainable-AI work.
- **Scenarios (what-if):** deliberately **not stored** (ADR-0006) — the Simulator (E5)
  computes scenarios in-memory from the live plan and returns a diff; add a
  `scenarios` table only when saving/sharing scenarios becomes a real need.
