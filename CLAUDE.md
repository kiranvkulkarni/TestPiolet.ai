# CLAUDE.md

> Read this first, every session. It is the single source of truth for how to work on
> this project. If this conflicts with a doc, this file wins — then fix the doc.
> Companion docs live in `docs/`; the build sequence and ready-to-use prompts live in
> `build-plan/`.

## What this project is

**QA Task Assigner** — a web app for **Samsung Android QA teams** to manage test tasks,
track leave, view timelines, and report progress, replacing ad-hoc Excel management. It
already works and is fairly complete. It ships with a **built-in AI agent** (floating
chat) that assigns tasks, checks workload, updates statuses, and drafts test plans in
natural language, powered by a **fully on-premises LLM** (Ollama / Samsung Gauss / Intel
OpenVINO via an OpenAI-compatible API).

**North star ("QAOS"):** evolve this from a task tracker into an *AI-native QA operating
system* — the schedule becomes a live model the AI can plan, operate, and stress-test.
The two flagship differentiators we are building toward:

1. **An in-place editable Gantt workspace** (not a read-only chart — the primary workspace).
2. **A flexible AI Operations Assistant** (tool-calling agent that operates the model,
   with explanations), extended into an **AI Project Planner** and **AI Timeline Simulator**.

See `docs/PRODUCT_VISION.md` for the full picture.

## Golden rule: extend, don't rebuild

This is a **brownfield** project. Do **not** regenerate files or reinvent structure.
Read the relevant existing module, follow its patterns, and make the smallest change that
delivers the feature. New code should look like it was written by whoever wrote the file
next to it.

## The stack (as it actually is)

**Backend** — `backend/`
- Python 3.11 · FastAPI 0.115 · SQLAlchemy 2.0 · Pydantic v2 / pydantic-settings.
- DB: **SQLite** for local dev, **PostgreSQL** for the LAN server (`psycopg2`).
  **Alembic migrations** since E0 (ADR-0003): every schema change ships with a migration
  (`alembic revision --autogenerate` → review → `alembic upgrade head`). `create_all`
  still runs on boot for dev convenience; see `backend/README.md`.
- Auth: JWT via `python-jose` (HS256, 8-hour tokens), `passlib[bcrypt]`.
- AI: the **`openai`** client pointed at a local LLM base URL; OpenAI-style tool calling.
- Files: `aiofiles` uploads to `UPLOAD_DIR`. Email: optional SMTP (`email_service.py`).

**Frontend** — `frontend/`
- React 19 · Vite · TypeScript · **Tailwind CSS v4** (`@tailwindcss/vite`).
- UI primitives: **Radix UI** (dialog, select, dropdown, tabs, tooltip, …) + `clsx` +
  `tailwind-merge` + `lucide-react` icons + `react-hot-toast`.
- Server state: **TanStack Query**. Client/auth state: **Zustand**. HTTP: **axios**.
- Routing: `react-router-dom` v7. Charts: **Recharts**. Dates: `date-fns`.
- Gantt (since E2): **custom editable timeline** in `components/gantt/`
  (`GanttWorkspace.tsx` + pure `timeline.ts` + `useUndoStack.ts`) — drag/resize/link/
  reassign/inline-edit/undo-redo, virtualized rows. `gantt-task-react` was removed
  (ADR-0004).

Full detail: `docs/ARCHITECTURE.md`. Never silently swap a library — that's an ADR.

## Repo layout (real)

```
backend/app/
  main.py            FastAPI app + router wiring + /health (create_all on boot)
  config.py          Settings (env, prefix-less; DATABASE_URL, SECRET_KEY, LLM_*, …)
  database.py        engine, SessionLocal, Base, get_db dependency
  models.py          SQLAlchemy models + all Enums (see docs/DATA_MODEL.md)
  schemas.py         Pydantic request/response schemas
  auth.py            password hashing, JWT, current-user dependencies
  utils.py           write_audit + create_notification helpers
  scheduling.py      pure CPM engine: topo order, calendars, critical path (E1)
  agent_engine.py    LLM tool-calling loop (TOOLS, TOOL_FN_MAP, SYSTEM_PROMPT, run_agent)
  agent_tools.py     the actual tool functions (query + mutate the DB)
  email_service.py   optional SMTP notifications
  seed.py            demo data (manager + 8 testers + devices + sample tasks)
  routers/           auth, users, device_models, projects, test_cycles,
                     test_requests, tasks, leaves, comments, files,
                     dashboard, notifications, agent
backend/alembic/     migrations (baseline = current models; see backend/README.md)
backend/tests/       pytest suite for the agent tools
frontend/src/
  api/               axios client + endpoint wrappers
  store/             Zustand stores (authStore)
  pages/             Dashboard, Tasks, GanttView, TestRequests, Projects, Team,
                     Leaves, Reports, DeviceModels, Login
  components/        agent/ChatWidget, gantt/* (editable timeline), layout/*,
                     shared/*, tasks/*
  types/             shared TS types    utils/  helpers
```

## Domain model (one screen)

`Project → TestCycle (optional) → TestRequest → Task`. A `Task` has a type (15 QA types:
functional/nonfunc/compliance), status, priority, automation type, dates, estimate,
device, and typed many-to-many dependencies via `TaskDependency` (the old single
`depends_on` FK is deprecated/mirrored — ADR-0005). Scheduling math (critical path,
working calendars) lives in the framework-free `app/scheduling.py`. Plus `DeviceModel`,
`Leave`, `User` (manager/tester/viewer), `Comment`, `Attachment`, `AuditLog`,
`Notification`. Integer primary keys. Canonical detail + enums: `docs/DATA_MODEL.md`.

## The AI agent (what exists)

`agent_engine.run_agent(messages, db, current_user_id)` runs an OpenAI-style tool loop
(temperature 0.1, 10-iteration guard) against the local LLM. Ten tools today:
`get_team_members`, `get_workload_summary`, `get_projects`, `get_test_requests`,
`get_tasks`, `get_device_models`, `check_leave_conflicts`, `create_task`,
`create_tasks_bulk`, `update_task`. Exposed at `POST /agent/chat`, `GET /agent/status`.
To add capability, add a function in `agent_tools.py`, a schema in `TOOLS`, and an entry
in `TOOL_FN_MAP`. Details + the extension plan: `docs/AI_ASSISTANT.md`.

## How to run

```bash
# Backend
cd backend && pip install -r requirements.txt
cp .env.example .env            # set SECRET_KEY; DATABASE_URL defaults to SQLite
python -m app.seed              # demo data
python run.py                   # or: uvicorn app.main:app --reload  → :8000 (/docs)

# Frontend
cd frontend && npm install && npm run dev   # → :5173
```
Default logins (from seed): manager `admin@qa.local` / `admin123`; testers
`<name>@qa.local` / `tester123`. AI agent is **off** until `AGENT_ENABLED=true` and a
local LLM is reachable at `LLM_BASE_URL`.

## Working rules (non-negotiable)

- **Extend, don't rebuild** (see golden rule). Match existing patterns per module.
- **One feature at a time**, following `build-plan/ROADMAP.md`. Ready prompts are in
  `build-plan/prompts/`.
- **The AI never touches the DB except through `agent_tools`** — one code path, auditable.
- **Every mutation should be explainable and auditable.** Reuse `AuditLog`; for AI actions
  we are moving toward returning a rationale + confidence (Explainable AI).
- **Every architectural change gets an ADR** in `docs/adr/` (use `template.md`). This
  includes swapping a library, adding migrations, or changing the schema shape.
- **Keep it runnable.** Backend boots, frontend builds, seed works, after every change.
- **Tests where they earn their keep** — start with the scheduling/critical-path logic
  and agent tools (pure, high-value). Don't chase coverage on trivial CRUD.

## Feature lifecycle (per feature)

understand the existing code → design + edge cases → schema change (+ migration, once
Alembic exists) → API → backend logic → frontend (Query hook + UI) → test the risky parts
→ self-review → update the relevant `docs/` file + `CHANGELOG` → done.

## UX invariants (never violate)

Keyboard-friendly everywhere · edits feel instant (optimistic UI via TanStack Query) ·
inline edit over separate edit forms · avoid modals unless necessary · never force a full
page reload · every feature exposes an API shaped so the AI agent can call it later.
Full guidance: `docs/UX_GUIDELINES.md`.

## Where to look

- Features & usage guide (user-facing, with examples) → `docs/USER_GUIDE.md`
- Vision & USPs → `docs/PRODUCT_VISION.md`
- Architecture & stack → `docs/ARCHITECTURE.md`
- Schema & enums → `docs/DATA_MODEL.md`
- API surface → `docs/API_MAP.md`
- AI agent & extension plan → `docs/AI_ASSISTANT.md`
- Conventions → `docs/CODING_STANDARDS.md` · UX → `docs/UX_GUIDELINES.md`
- Decisions → `docs/adr/`
- What to build next, with prompts → `build-plan/ROADMAP.md`, `build-plan/prompts/`
