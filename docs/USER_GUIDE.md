# QA Task Assigner — Complete Guide

Everything the product does, what it needs to run, and how to use it — with examples.
This is the user/operator-facing companion to the engineering docs
(`ARCHITECTURE.md`, `DATA_MODEL.md`, `API_MAP.md`, `AI_ASSISTANT.md`).

---

## 1. What this is

**QA Task Assigner** is a web app for **Samsung Android QA teams** that replaces
ad-hoc Excel test management. It tracks projects → test requests → tasks, team
workload, leave, and progress — and it ships with an **on-premises AI agent** that can
operate the schedule in natural language. Nothing ever leaves your network: the AI
runs against a local LLM (Ollama / Samsung Gauss / Intel OpenVINO).

The two flagship capabilities ("QAOS" vision):

1. **An editable Gantt workspace** — the timeline is the primary workspace, not a
   report. Drag to move, resize, draw dependencies, reassign, undo — everything
   persists and reschedules live.
2. **An explainable AI Operations Assistant** — a tool-calling agent that assigns,
   reschedules, and rebalances work, returning a **rationale + confidence + undo**
   for every action, extended into an **AI Project Planner** (brief → editable plan)
   and an **AI Timeline Simulator** (what-if scenarios with ranked mitigations).

---

## 2. Requirements

### System

| Component | Requirement |
|---|---|
| Backend | Python **3.11+**, pip |
| Frontend | Node.js **18+** (tested on 24), npm |
| Database | **SQLite** (zero-config, local dev) or **PostgreSQL** (LAN/production) |
| AI features (optional) | Any **OpenAI-compatible local LLM** endpoint — e.g. `ollama serve` with `llama3.1`, Samsung Gauss, Intel OpenVINO model server |
| Browser | Any modern browser; the UI is keyboard-friendly and usable down to laptop width |

### Functional requirements the product satisfies

- Role-based access: **manager** (full control), **tester** (own work + task edits),
  **viewer** (read-only).
- Full QA task lifecycle: 15 Samsung-QA task types across functional / non-functional /
  compliance, 5 statuses, 4 priorities, manual/automated tracking, build versions,
  device targeting, estimates vs. actuals.
- Real scheduling: typed finish-to-start dependencies (cycles rejected), working-day
  calendars (weekends + approved leave per assignee), critical-path computation.
- Every mutation is **audited** (`AuditLog`), AI mutations are tagged `[AI]`, and every
  AI write is **explainable** and **undoable**.
- Bulk/destructive AI actions require **explicit human confirmation**.
- Everything the UI can do, the AI can do — through the **same endpoints** (no backdoors).

---

## 3. Getting started

```bash
# 1. Backend  →  http://localhost:8000  (interactive API docs at /docs)
cd backend
pip install -r requirements.txt
cp .env.example .env          # set SECRET_KEY for anything non-local
python -m app.seed            # demo data (also creates the schema)
python run.py                 # or: uvicorn app.main:app --reload

# 2. Frontend  →  http://localhost:5173  (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

**Default logins** (from the seed):

| Role | Email | Password |
|---|---|---|
| Manager | `admin@qa.local` | `admin123` |
| Testers (8) | `priya@qa.local`, `ravi@qa.local`, `anjali@qa.local`, … | `tester123` |

The seed creates 2 projects (Camera v16, Gallery MR2), 6 test requests, 18 tasks with
dependencies, 7 Galaxy devices, and 2 leave records. For Gantt performance testing,
`python -m app.seed --large` adds a synthetic ~450-task project.

### Enabling the AI

The AI features (chat assistant, Planner) are **off by default**. In `backend/.env`:

```ini
AGENT_ENABLED=true
LLM_BASE_URL=http://localhost:11434/v1   # Ollama default
LLM_MODEL=qwen2.5:7b
LLM_API_KEY=ollama                        # any non-empty string for Ollama
```

Then pull the model (`ollama pull qwen2.5:7b`) and restart the backend. The chat widget
header shows the connection state; `GET /agent/status` reports it programmatically.

**Model choice matters.** The agent needs a model that supports **native tool calling**
and follows multi-step plans. Tested on an 8 GB GPU: `qwen2.5:7b` handles the full tool
loop reliably (recommended); `llama3.1:8b` manages single-tool queries but derails on
multi-step chains; plain `llama3` has no tool support at all. Pick a model that fits
entirely in VRAM — partial CPU/GPU offload is slow and fragile on some architectures.
The **Simulator** and all REST mirrors work *without* an LLM — only free-text
drafting (chat + `POST /agent/plan`) needs one.

---

## 4. Configuration reference (`backend/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./qa_tasks.db` | SQLAlchemy URL; e.g. `postgresql+psycopg2://qa:qa@host:5432/qa_tasks` |
| `SECRET_KEY` | `change-me-in-production` | JWT signing key — **set a long random string** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Session length (8 h) |
| `UPLOAD_DIR` / `MAX_UPLOAD_SIZE_MB` | `./uploads` / `20` | Attachment storage + size cap |
| `EMAIL_ENABLED`, `EMAIL_HOST`, … | off | Optional SMTP notifications on assignment |
| `AGENT_ENABLED` | `false` | Master switch for LLM-backed features |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | Ollama defaults | Any OpenAI-compatible endpoint |
| `CORS_ORIGINS` | localhost:5173 | Comma-separated allowed origins |

---

## 5. Core concepts

```
Project  →  TestCycle (optional)  →  TestRequest  →  Task
User (manager / tester / viewer)     DeviceModel     Leave
TaskDependency (typed, many-to-many) AuditLog        Notification
```

**Task types (exact values — the AI and API depend on them):**
`functional_sanity`, `functional_full_sanity`, `functional_feature_verification`,
`functional_menu_tree`, `issue_reproduction`, `fix_verification`,
`side_effect_verification`, `nonfunc_kpi_launch_time`, `nonfunc_fps`,
`nonfunc_memory_profiling`, `nonfunc_memory_leak`, `nonfunc_power_consumption`,
`compliance_google_its`, `compliance_google_cts`, `compliance_sensor_fusion`.

**Statuses:** `pending → in_progress → completed` (plus `blocked`, `cancelled`).
**Priorities:** `critical`, `high`, `medium`, `low`.

**Scheduling semantics** (used everywhere — Gantt, AI tools, Planner, Simulator):
- A dependency `A → B` is **finish-to-start**: B starts no earlier than the first
  working day after A ends. Cycles are always rejected.
- A **working day** skips weekends and the assignee's **approved** leave
  (pending/rejected leave never moves dates).
- Rescheduling is **conservative**: only *violated* dependents are pushed forward;
  user-set dates are never pulled earlier.
- The **critical path** is the zero-slack chain that determines the end date.

---

## 6. Features & how to use them

### 6.1 Dashboard (`/`)

At-a-glance: task counts by status, overdue count, team size, per-tester workload
bars (active tasks + estimated hours), project completion, overdue list, and
approved leaves in the next 30 days. Stat cards link into the filtered views.

### 6.2 Tasks (`/tasks`)

- **Two views**: a table and a **kanban** board (toggle top-right). On the kanban,
  **drag a card between columns** to change status.
- **Filters**: text search, status, priority, assignee, project, overdue-only.
- **Inline status change** in the table via the status pill dropdown — optimistic,
  instant, no page reload.
- Click a title → **detail modal**: full metadata, **comments** (Enter to send),
  **attachments** (upload/download, 20 MB cap), edit button.
- Completing a task auto-stamps `completed_date`.

*Example:* filter Project = "Camera v16 (One UI 8)" + status = Blocked to stand-up
review the blockers, drag each resolved card to In Progress.

### 6.3 Gantt workspace (`/gantt`) — USP #1

The primary planning surface. Rows are grouped by assignee; only the visible window
renders, so a 450-task plan stays smooth.

| Interaction | How |
|---|---|
| Move a task | Drag the bar; dates snap to the assignee's working calendar; violated dependents are pushed automatically |
| Reassign | Drag the bar **vertically onto another person's section** |
| Resize | Drag the bar's left edge (change start) or right edge (change due) |
| Draw a dependency | Drag the **○ handle** at the bar's right edge onto another task (cycles are rejected with a toast) |
| Rename | Double-click the title → Enter saves, Esc cancels |
| Right-click menu | Rename · Duplicate · Split · Convert to milestone · Create dependency · Unlink from … |
| Multi-select | Ctrl/Cmd+click bars; drag moves the whole selection; ←/→ nudges ±1 day |
| Undo / redo | **Ctrl+Z / Ctrl+Y** (or the toolbar buttons) — works for every edit above |
| Zoom | Day / Week / Month |
| Color-by | Status / Priority / Assignee |
| **Critical path** | Toolbar toggle — zero-slack tasks glow red, everything else dims |
| **Workload heatmap** | Toolbar toggle — per-person strips tint green→amber→red by overlapping active tasks per day |

Every edit is **optimistic** (instant), persisted through the scheduling endpoints,
reconciled on the server response, and rolled back with an error toast on failure.

*Example:* the build slipped — drag "HDR full sanity" a week right. Its dependent
"HDR side-effect check" is pushed automatically, the arrows follow, and the critical
path re-highlights. Changed your mind? Ctrl+Z restores both tasks' dates.

### 6.4 AI Operations Assistant (chat widget, every page) — USP #2

The floating ✨ button opens the assistant. It has **16 tools** — 9 read
(team, workload, projects, requests, tasks, devices, leave conflicts, critical path,
underloaded testers, simulation) and 7 write (create/update tasks, bulk create,
reschedule, dependencies, balanced assignment).

**Example prompts:**

```
Who has the lightest workload right now?
Create a sanity task for HDR on the S25 Ultra under the HDR request, due Friday, assign it to whoever is free.
Mark task 12 completed — 6 actual hours.
Rebalance next week's camera sanity tasks off Priya.
What's the critical path of Camera v16?
What happens if Ravi is out next Wednesday to Friday?
```

**What makes it trustworthy:**

- Every write returns a **rationale** ("Assigned 3 tasks by estimated hours, largest
  first onto the least-loaded tester; loads (h) before {...} → after {...}; approved
  leave was avoided for every assignment.") and a **confidence** badge (color-coded
  in the chat card).
- **Undo** button per action — executes a machine-readable payload through the normal
  endpoints. **View in Gantt** links to the affected tasks.
- **Confirmation gate**: any bulk write of **5+ items** returns a plan instead of
  committing. The widget shows **"Yes, do it" / "Cancel"** quick replies; only your
  explicit yes commits. This is enforced *in the tools*, not just the prompt.
- Every AI mutation lands in `AuditLog` tagged `[AI]` under your user.

### 6.5 AI Project Planner (`/planner`)

Plain-English brief → a complete, **editable** draft plan. **Nothing is created until
you click Commit.**

*Example brief:*

> Galaxy Camera v16 next week — HDR, Night Mode, Portrait Video, 50MP, Expert RAW;
> 5 testers, 2 devices, 3 working days

1. **Generate plan** (needs the local LLM): the AI drafts requests → tasks with exact
   task types, estimates, and dependencies.
2. The system then **deterministically** validates and enriches it: invalid enums are
   fixed (with a warning), device names resolve to real devices, unassigned tasks are
   spread **workload-balanced** across testers, cycle-forming dependencies are dropped
   with a warning, and the whole draft is **scheduled** through the real engine
   (weekends + approved leave respected).
3. Review: the AI's rationale, a warnings banner, an editable table (title, type,
   estimate, assignee, device, priority), and a mini-timeline. Edit anything, then
   **Re-schedule edits** to recompute dates.
4. **Commit N tasks** — creates the requests, tasks, and dependencies through the
   audited tools (tagged `[AI planner]`), and jumps to the Gantt. Commit *refuses*
   (rather than silently fixes) cycles or a missing target project.

### 6.6 AI Timeline Simulator (`/simulator`)

Answer "what happens if…" **without touching the real plan**. Scenarios are computed
in-memory and are deterministic; nothing is ever written by a simulation.

**Perturbations** (combine freely in one scenario):
- 🏖 *Person on leave* — e.g. Priya out Mon–Fri next week
- ⏳ *Task slips* — task #15 delayed 3 days
- ✂️ *Remove task* — descope it (its dependents are freed)
- ➕ *Add scope* — a new 16 h task, optionally after an existing one

**You get back:** an impact summary ("2 task(s) slip; the plan's end date moves
2026-08-06 → 2026-08-13 (+7 days)"), the affected-task list with **baseline-vs-scenario
overlay bars**, became-critical flags, and **ranked mitigations**, each explained:

> **#1 (90%)** Reassign 1 affected task (HDR sanity on S25 Ultra) from Priya Sharma to
> Anjali Desai → recovers 7 day(s); scenario end moves 2026-08-13 → 2026-08-06.

Click **Apply** on a mitigation and the reassignment goes through the normal audited
task endpoints — never automatically, never through a backdoor. The same engine is
available in chat: *"what if Priya is out next week?"* calls the `run_simulation` tool.

### 6.7 Test Requests (`/test-requests`), Projects (`/projects`), Cycles

- Test requests group tasks under a project (optionally under a test cycle); they
  carry a requester, priority, and status, and show a live task count.
- Projects have status, color (used in the Gantt/reports), and date range. Deleting a
  project cascades to its requests and tasks — the confirm dialog says so.
- Managers create/edit; testers can create/edit requests and tasks; viewers read.

### 6.8 Team (`/team`)

Member cards with role, active/inactive, and live load (active tasks + estimated
hours). Managers add members, reset passwords, change roles/colors, deactivate.
`GET /users/underloaded` (and the matching AI tool) lists who has headroom.

### 6.9 Leaves (`/leaves`)

Request leave (planned / sick / emergency / comp-off) with a date range and reason.
Managers **approve/reject** inline (✓ / ✗) — approval notifies the requester and,
crucially, **approved leave immediately affects scheduling**: the Gantt, the AI
tools, the Planner, and the Simulator all route work around it. Leave/task overlap
conflicts are surfaced via `GET /leaves/conflicts` and per-task
`GET /tasks/{id}/leave-conflicts`.

### 6.10 Reports (`/reports`)

Workload by tester (tasks + hours), tasks by type (all 15), and project completion —
plus **Export tasks CSV** (respects filters via the API:
`GET /dashboard/export/tasks?project_id=1&status=completed`).

### 6.11 Device Models (`/devices`)

The Samsung device lab: brand/series/model/OS. Devices referenced by tasks are
**deactivated instead of deleted** to keep history intact. The AI resolves device
names in briefs ("S25 Ultra") to these records.

### 6.12 Notifications (bell, top bar)

In-app notifications for assignment (human or AI), comments on your tasks, leave
requests (to managers) and decisions (to requesters). Unread badge, mark-all-read;
optional email via SMTP.

---

## 7. API examples

Interactive docs live at `http://localhost:8000/docs`. All endpoints (except login)
take `Authorization: Bearer <jwt>`.

```bash
# login
TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@qa.local","password":"admin123"}' | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"

# create a task
curl -s -X POST localhost:8000/tasks -H "$AUTH" -H "Content-Type: application/json" -d '{
  "test_request_id": 1, "title": "Night Mode sanity — S25",
  "task_type": "functional_sanity", "priority": "high",
  "assigned_to": 3, "start_date": "2026-07-13", "due_date": "2026-07-14",
  "estimated_hours": 8, "device_model_id": 2
}'

# move it (snaps to the assignee's working calendar; pushes violated dependents)
curl -s -X PATCH localhost:8000/tasks/19/move -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"start_date": "2026-07-20"}'
# → {"task": {...}, "affected": [pushed dependents], "critical_path": [ids]}

# link a dependency (predecessor must finish first) — 400 on cycle, 409 on duplicate
curl -s -X POST localhost:8000/tasks/20/dependencies -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"depends_on_task_id": 19}'

# leave-aware bulk reschedule (5+ tasks require "confirm": true)
curl -s -X POST localhost:8000/tasks/reschedule -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"task_ids": [19, 20], "start_date": "2026-08-03"}'
# → {"rescheduled": [...], "pushed_dependents": [...],
#    "rationale": "Rescheduled 2 task(s) ... snapped to each assignee's working calendar ...",
#    "confidence": 0.9, "undo": {"kind": "update_tasks", "tasks": [...]}}

# workload-balanced assignment, moving work OFF user 2
curl -s -X POST localhost:8000/tasks/assign-balanced -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"task_ids": [21, 22, 23], "exclude_user_ids": [2]}'

# critical path of a project
curl -s -H "$AUTH" "localhost:8000/tasks/critical-path?project_id=1"

# what-if simulation (read-only — never writes)
curl -s -X POST localhost:8000/simulations -H "$AUTH" \
  -H "Content-Type: application/json" -d '{
    "project_id": 1,
    "perturbations": [
      {"type": "leave", "user_id": 2, "start_date": "2026-08-03", "end_date": "2026-08-07"},
      {"type": "slip", "task_id": 15, "days": 3}
    ]}'
# → predicted_delay_days, affected_tasks, critical-path change, ranked mitigations

# chat with the agent (needs AGENT_ENABLED + a local LLM)
curl -s -X POST localhost:8000/agent/chat -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Who has the lightest workload?"}]}'
# → {"reply", "actions", "explanation": [{tool, rationale, confidence}], "pending_confirmation"}
```

The full surface is catalogued in `docs/API_MAP.md`.

---

## 8. AI safety & audit model

| Guarantee | Mechanism |
|---|---|
| One data path | The AI touches the DB **only** through `agent_tools`; every tool has a REST mirror calling the same function |
| Explainability | Write tools return `{rationale, confidence, undo}`; `/agent/chat` aggregates an `explanation` array |
| Human in the loop | Bulk writes (≥ 5 items) return `needs_confirmation` + a plan; only an explicit user yes re-calls with `confirm=true`; the Planner **never auto-commits**; Simulator mitigations apply only on click |
| Auditability | Every mutation writes `AuditLog` (entity, field, old → new, user); AI actions are tagged `[AI]` / `[AI planner]` |
| Reversibility | Undo payloads (`update_tasks` / `delete_tasks` / `add_dependency` / `remove_dependency`) execute through the normal endpoints; the Gantt has full undo/redo |
| Privacy | The LLM is local; no data leaves the network |

---

## 9. Development

```bash
# tests (116: scheduling engine, endpoints, agent tools, planner, simulator)
cd backend && python -m pytest tests -q

# migrations (Alembic since E0 — every schema change ships one)
alembic upgrade head            # fresh DB
alembic stamp head              # adopt a pre-Alembic DB
alembic revision --autogenerate -m "what changed"   # after editing models.py
alembic check                   # drift detection

# big dataset for Gantt performance work
python -m app.seed --large      # ~450-task project

# frontend production build
cd frontend && npm run build
```

**Adding an AI tool** (the pattern): function in `agent_tools.py` returning
`{result…, rationale, confidence, undo}` + schema in `TOOLS` + entry in
`TOOL_FN_MAP` (+ `WRITE_TOOLS` if it mutates) + a REST mirror + tests.
Details: `docs/AI_ASSISTANT.md`. Conventions: `docs/CODING_STANDARDS.md`.
Decisions live in `docs/adr/` (0001–0006).

---

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| Login fails with the seed accounts | Run `python -m app.seed` first; check the backend is on :8000 |
| Chat says "Agent disabled" | Set `AGENT_ENABLED=true` in `backend/.env`, restart the backend |
| Chat says "LLM unreachable" | Start your model (`ollama run llama3.1`); verify `LLM_BASE_URL` (`/v1` suffix for Ollama) |
| "would create a cycle" (400) | You linked A→B where B already (transitively) precedes A — remove the opposing edge first |
| A task won't move earlier | Its predecessor ends later — rescheduling never violates finish-to-start; move the predecessor or unlink |
| Dates jump when moving a task | The assignee has approved leave or the target is a weekend — dates snap to working days by design |
| 5+ bulk action "didn't happen" | It returned a confirmation plan; reply yes (chat) or send `confirm: true` (API) |
| Frontend can't reach the API | The dev server proxies `/api` → `:8000`; make sure both are running |
