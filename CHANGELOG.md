# Changelog

## [Unreleased] — E0: harden the baseline
- **Alembic migrations** (ADR-0003 accepted): `backend/alembic/` with a baseline
  revision generated from `models.py` (verified drift-free via `alembic check`).
  Fresh DBs: `alembic upgrade head`; pre-existing DBs: `alembic stamp head`.
  Workflow documented in `backend/README.md`. From E1 on, every schema change
  ships with a migration.
- **Tests** (`backend/tests/`, pytest): 26 tests covering the agent tools —
  `get_tasks` filters (status/assignee/overdue/combined), `get_workload_summary`
  (active-only counting), `check_leave_conflicts` (overlap + defensive-arg errors),
  `create_task` / `create_tasks_bulk` / `update_task` including validation
  rejections, bulk rollback on partial failure, `AuditLog` rows, `completed_date`
  stamping, and assignment notifications.
- Audit logging was already standardized via `app/utils.py` (`write_audit`) across
  routers and AI write tools in the baseline; now locked in by tests.
- No user-facing change; no schema change.

## [Unreleased] — Baseline application built
- **Backend (FastAPI)**: full app under `backend/app/` — models + enums per
  `docs/DATA_MODEL.md`, Pydantic v2 schemas, JWT auth (bcrypt, 8-hour tokens),
  13 routers covering the whole surface in `docs/API_MAP.md` (auth, users,
  device-models, projects, test-cycles, test-requests, tasks incl. `/tasks/gantt` +
  bulk + status patch + leave-conflicts, comments, attachments, leaves, dashboard
  incl. CSV export, notifications, agent). `AuditLog` written on mutations;
  notifications created on assignment/comment/leave events; optional SMTP email.
- **AI agent**: `agent_engine.py` (OpenAI-compatible tool loop, temperature 0.1,
  10-iteration guard) + `agent_tools.py` with the ten tools
  (7 read / 3 write), exposed at `POST /agent/chat`, `GET /agent/status`.
  Off by default until `AGENT_ENABLED=true` and a local LLM is reachable.
- **Seed** (`python -m app.seed`): manager + 8 testers + 7 Samsung devices +
  2 projects, 1 cycle, 6 test requests, 18 tasks, 2 leaves.
- **Frontend (React 19 + Vite + TS + Tailwind v4)**: Login, Dashboard, Tasks
  (list + kanban with drag-to-status, filters, optimistic status updates, task
  detail with comments/attachments), GanttView (`gantt-task-react`), TestRequests,
  Projects, Team, Leaves (request/approve), Reports (Recharts + CSV export),
  DeviceModels — plus notification bell and the floating AI ChatWidget. TanStack
  Query for server state, Zustand `authStore`, shared axios client with JWT +
  401 redirect, Radix dialogs/dropdowns.
- **Note**: seed logins use `.local` addresses, so email fields are plain strings
  (not `EmailStr`) in the API schemas.

## [Unreleased] — Context package added
- Added Claude Code context package: CLAUDE.md, product/architecture/data-model/API/
  standards/UX docs, ADRs (incl. migrations + Gantt approach), and an evolution roadmap
  with a per-milestone prompt library (E0–E5).
- No application code changed.
