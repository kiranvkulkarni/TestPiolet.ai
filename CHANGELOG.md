# Changelog

## [1.0.0] — 2026-07-08 — Documentation: user guide
- Added `docs/USER_GUIDE.md` — the complete feature & requirements guide with
  examples: setup + configuration reference, core concepts and scheduling
  semantics, every feature (Dashboard, Tasks, Gantt workspace interactions,
  AI assistant prompts, Planner walkthrough, Simulator scenarios, requests/
  projects, team, leaves, reports, devices, notifications), a curl-based API
  walkthrough, the AI safety & audit model, development workflow, and
  troubleshooting. Linked from README and CLAUDE.md.

## [1.0.0] — 2026-07-08 — E5: AI Timeline Simulator
- **`app/simulator.py`** (ADR-0006: scenarios computed in-memory, nothing
  persisted, nothing written): forks the live plan into pure scheduling-engine
  inputs, applies perturbations — `leave` (person out for a range), `slip`
  (task delayed N days), `remove_task`, `add_task` (optionally after a
  predecessor) — runs baseline vs scenario, and diffs: affected tasks with
  per-task delay and became-critical flags, predicted end-date delay,
  critical-path change. Deterministic for a given scenario.
- **Mitigations:** reassignment candidates (move an impacted assignee's delayed
  tasks to each other tester) are each **re-simulated** and ranked by actually
  recovered days; every mitigation carries an explanation, new end date,
  confidence, and a machine-executable `apply` payload that routes through the
  normal audited `PUT /tasks/{id}` — never a backdoor, never auto-applied.
- **Exposure:** `run_simulation` agent tool (the assistant can answer "what if
  Priya is out next week?") + read-only `POST /simulations` REST mirror.
- **Simulator page** (`/simulator`): scenario builder (chips per perturbation),
  impact summary, baseline-vs-scenario overlay bars per affected task, and
  ranked mitigation cards with one-click Apply.
- **Tests:** +10 (116 total): leave/slip/remove/add perturbations, plan
  untouched before and after, determinism, mitigation ranking + explanation +
  apply-payload shape, endpoint read-only behavior and 400s.

## [1.0.0] — 2026-07-08 — E4: AI Project Planner
- **`app/agent_planner.py`** — brief → validated draft plan, in two separated
  halves: `generate_raw_draft` (the single strict-JSON LLM call) and a fully
  deterministic pipeline: `validate_and_enrich` (fixes invalid enums with
  warnings, resolves device names to IDs, workload-balanced assignment that
  respects explicit picks, drops cycle-forming dependency edges with warnings,
  schedules everything through the E1 engine incl. approved leave) and
  `commit_plan` (re-validates hard constraints and refuses on cycles/missing
  project; creates requests + tasks + dependencies via the audited agent tools).
  **Never auto-commits** — nothing is written until the manager commits.
- **Endpoints** (manager-only): `POST /agent/plan` (needs the LLM; 503 when the
  agent is disabled), `POST /agent/plan/refresh` (deterministic re-validate of an
  edited draft), `POST /agent/plan/commit`.
- **Planner page** (`/planner`, sidebar "AI Planner"): brief + target project →
  AI rationale, warning banner (unknown devices, dropped cycles, leave overlaps),
  editable plan table (title/type/estimate/assignee/device/priority), draft
  mini-timeline, "Re-schedule edits", and "Commit N tasks" which lands the plan
  in the Gantt.
- **Tests:** +15 (106 total): enum fixing, device resolution, balanced + explicit
  assignment, cycle dropping (validate) and cycle refusal (commit), leave-aware
  scheduling, nothing-written-before-commit, commit audit trail (`[AI planner]`),
  endpoint behavior incl. 503 when disabled.

## [1.0.0] — 2026-07-08 — E3: Explainable AI + Operations Assistant (USP #2)
- **Six new agent tools** (16 total), each with a REST mirror calling the same
  function: `reschedule_tasks` (bulk, leave/calendar-aware, pushes dependents →
  `POST /tasks/reschedule`), `assign_bulk` (workload-balanced, avoids approved
  leave, `exclude_user_ids` to move work off someone → `POST /tasks/assign-balanced`),
  `set_dependency` / `remove_dependency` (cycle-safe; mirror the E1 endpoints),
  `get_critical_path` (→ `GET /tasks/critical-path`), `find_underloaded_testers`
  (→ `GET /users/underloaded`).
- **Explainable AI:** every write tool returns `{rationale, confidence, undo}`;
  `run_agent` aggregates `explanation` and `/agent/chat` now returns
  `{reply, actions, explanation, pending_confirmation}`. All AI mutations write
  `AuditLog` rows marked `[AI]` under the current user.
- **Confirmation flow:** bulk write tools (5+ items) return a `needs_confirmation`
  plan instead of committing; only an explicit user yes re-calls with
  `confirm=true` (system prompt forbids the model setting it alone).
- **ChatWidget:** per-action explanation cards (rationale + confidence badge),
  one-click **Undo** (executes the machine-readable undo payload through the
  normal REST endpoints), "View in Gantt" link, and Yes/Cancel quick replies for
  pending plans.
- **Refactor:** scheduling glue (calendars, durations, push-persist, critical
  path) extracted from the tasks router into `app/schedule_glue.py`, shared by
  the router and the AI tools — one code path for schedule math.
- **Tests:** +22 (91 total): reschedule incl. leave snapping + dependent pushes +
  `[AI]` audit rows, dependency cycle/duplicate rejection, workload balancing +
  leave avoidance + exclusions, both confirmation gates (nothing committed
  without confirm), critical path ordering, underloaded testers, REST mirrors.

## [1.0.0] — 2026-07-08 — E2: editable Gantt workspace (USP #1)
- **Custom timeline component** (ADR-0004 decided: build custom, `gantt-task-react`
  removed): `components/gantt/GanttWorkspace.tsx` + pure `timeline.ts` +
  `useUndoStack.ts`.
- **Interactions**, all persisted through the E1 endpoints with optimistic updates
  (reconcile on refetch, rollback + toast on error):
  drag to move (drop on another person's section to reassign) · edge-drag resize
  (left edge = move keep-due, right edge = resize) · dependency drawing from the
  bar handle or the context menu (cycle 400s surfaced as toasts) · double-click
  inline title rename (Enter/Esc) · right-click menu (Rename, Duplicate, Split,
  Convert to milestone, Create dependency, Unlink …) · Ctrl+click multi-select with
  bulk drag and ←/→ nudge · **undo/redo** command stack (Ctrl+Z / Ctrl+Y) on every
  edit · day/week/month zoom · color-by status/priority/assignee ·
  **critical-path highlight** (dims non-critical) · **workload heatmap** overlay
  per assignee (overlapping active tasks per day) · milestone rendering (diamond).
- **Performance:** rows grouped by assignee and manually virtualized (only the
  visible window renders); weekend shading via CSS gradient; verified against a
  seeded 450-task project (`python -m app.seed --large`), `/tasks/gantt` with 468
  rows + CPM serves in ~0.3 s.
- **API:** `GET /tasks/gantt` rows now include `dependency_edges`
  (`{id, from_task_id}`) so the UI can unlink without an extra round-trip.

## [1.0.0] — 2026-07-08 — E1: dependencies + scheduling engine (backend only)
- **`task_dependencies` table** (ADR-0005): typed many-to-many edges
  (`finish_to_start`), unique per edge, cycles rejected. The migration copies
  legacy `Task.depends_on` values into the table; the column is deprecated —
  legacy writes are mirrored into the table, reads use only the table.
- **`app/scheduling.py`** — pure, framework-free engine: working-day calendars
  (weekends + approved leave per assignee), deterministic topological order,
  forward/backward pass (CPM) with slack + critical path, `would_create_cycle`,
  and a conservative `push_dependents` that only shifts *violated* dependents
  forward (user-set dates are never pulled earlier).
- **New endpoints** on `/tasks` (each returns the task, pushed dependents, and
  the recomputed critical path): `PATCH /{id}/move`, `PATCH /{id}/resize`,
  `POST /{id}/dependencies` (400 cycle / 409 duplicate),
  `DELETE /{id}/dependencies/{dep_id}`.
- **`GET /tasks/gantt`** now includes `dependencies` (predecessor ids),
  `critical`, and `slack_days` per row.
- **Tests:** +43 (27 engine unit tests: chains, parallel paths, weekends, leave
  gaps, determinism, cycles; 16 API tests: cycle 4xx, push-on-move/resize,
  leave-aware snapping, legacy mirroring, gantt enrichment). Suite: 69 green.
- No frontend change (E2 consumes this).

## [1.0.0] — 2026-07-08 — E0: harden the baseline
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

## [1.0.0] — 2026-07-08 — Baseline application built
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

## [1.0.0] — 2026-07-08 — Context package added
- Added Claude Code context package: CLAUDE.md, product/architecture/data-model/API/
  standards/UX docs, ADRs (incl. migrations + Gantt approach), and an evolution roadmap
  with a per-milestone prompt library (E0–E5).
- No application code changed.
