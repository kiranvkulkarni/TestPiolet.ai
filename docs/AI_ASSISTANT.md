# AI Assistant

The agent is an **explainable Operations Assistant** (since E3): it operates the
schedule through tools, returns a rationale + confidence for every write, and asks for
confirmation before bulk changes.

## How it works

- **Transport:** the `openai` Python client points at a local, OpenAI-compatible LLM
  (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`) — Ollama, Samsung Gauss, or Intel OpenVINO.
  Nothing leaves the network.
- **Loop:** `agent_engine.run_agent(messages, db, current_user_id)` sends the system
  prompt + conversation with `tools=TOOLS`, `tool_choice="auto"`, `temperature=0.1`, and a
  10-iteration guard. On each `tool_calls`, it dispatches via `TOOL_FN_MAP`, appends tool
  results, and loops until the model returns plain text. Returns
  `(reply, actions, explanation, pending_confirmation)`.
- **Exposure:** `POST /agent/chat` → `{reply, actions, explanation, pending_confirmation}`
  (with `GET /agent/status` for a health/enabled check).
- **Frontend:** `components/agent/ChatWidget.tsx` — floats on every page; renders one
  card per action (rationale + confidence badge + **Undo** + "View in Gantt"), and shows
  Yes/Cancel quick-replies when a plan is awaiting confirmation.

### The system prompt encodes real QA workflow
It lists the exact 15 task-type strings and a workflow: check workload before assigning,
fetch a valid `test_request_id` before creating, resolve device names to IDs, check leave
conflicts when dates are given, prefer the purpose-built scheduling tools over many
`update_task` calls, never set `confirm=true` without an explicit user yes, offer to log
actual hours on completion, and ask one clarifying question when ambiguous.

## The sixteen tools

**Read:** `get_team_members`, `get_workload_summary`, `get_projects`,
`get_test_requests`, `get_tasks` (filters: status/assignee/project/overdue),
`get_device_models`, `check_leave_conflicts`, `get_critical_path` (zero-slack chain +
project end), `find_underloaded_testers` (headroom vs. threshold or team average).

**Write** — each returns `{result…, rationale, confidence, undo}` and writes `AuditLog`
rows marked `[AI]` under the current user:
- `create_task` · `create_tasks_bulk` · `update_task` (the originals)
- `reschedule_tasks` — bulk move, snapped to each assignee's working calendar
  (weekends + approved leave); pushes violated dependents via the E1 engine.
- `set_dependency` / `remove_dependency` — typed edges; cycles rejected; the successor
  is pushed only if the new link is violated.
- `assign_bulk` — workload-balanced assignment (largest task → least-loaded tester),
  avoids approved leave, supports `exclude_user_ids` to move work OFF someone.

Each write tool has a **matching REST endpoint** (no private backdoors): the E1
move/resize/link/unlink endpoints, plus `POST /tasks/reschedule`,
`POST /tasks/assign-balanced`, `GET /tasks/critical-path`, `GET /users/underloaded` —
the REST mirrors call the same tool functions.

## Explainability contract

- `rationale` — one plain sentence covering what was checked and what changed
  ("…snapped to each assignee's working calendar; pushed 2 dependent task(s)…",
  "loads (h) before {…} → after {…}; approved leave was avoided…").
- `confidence` — 0..1 heuristic; lowered when dependents were pushed, leave conflicts
  were unavoidable, or dates overlap leave.
- `undo` — a machine-executable payload (`update_tasks` restore-fields /
  `delete_tasks` / `add_dependency` / `remove_dependency`) the ChatWidget executes
  through the normal REST endpoints.

## Confirmation flow (5+ items)

Bulk write tools (`create_tasks_bulk`, `reschedule_tasks`, `assign_bulk`) do **not**
commit at ≥ 5 items unless `confirm=true`. They return
`{needs_confirmation, plan, note}`; the engine sets `pending_confirmation` on the
response; the model presents the plan; the ChatWidget offers Yes/Cancel quick replies;
only an explicit user yes leads to the tool being re-called with `confirm=true`.

## How to add a tool (the pattern — follow it exactly)

1. Write `def my_tool(db: Session, ...args, **_) -> dict:` in `agent_tools.py`, returning a
   small JSON-serializable dict. Reuse existing models/queries; keep it defensive.
   Write tools must return `rationale`, `confidence`, `undo`, and write `AuditLog` rows.
2. Add its schema to `TOOLS` in `agent_engine.py` (`type: "function"`, name, description,
   parameters with the **exact enum strings** where relevant).
3. Register it in `TOOL_FN_MAP` (and `WRITE_TOOLS` if it mutates).
4. If it mutates data, also expose a matching REST endpoint that calls the same function.
5. Test it against seeded data in `backend/tests/`.

## AI Project Planner (since E4)

`app/agent_planner.py` + `pages/Planner.tsx`. Two deliberately separated halves:

- **`generate_raw_draft`** — the only LLM call: a strict-JSON planning prompt fed with
  the brief + a compact team/device context. Output shape: requests → tasks with refs,
  exact task-type enums, estimates, device names, `depends_on_refs`.
- **`validate_and_enrich`** — deterministic (fully tested without an LLM): fixes invalid
  enums (with warnings), resolves device names to real IDs, assigns unowned tasks
  workload-balanced, drops cycle-forming dependency edges (with warnings), and schedules
  the whole draft through the E1 engine (weekends + approved leave). Never writes.
- **`commit_plan`** — runs only on the manager's explicit Commit; re-validates hard
  constraints (project, refs, cycles) and **refuses** rather than silently fixing, then
  creates everything through the audited agent tools (`create_tasks_bulk` with
  `confirm=True` — the click is the confirmation — and `set_dependency`).

Endpoints (manager-only): `POST /agent/plan` (brief → draft; 503 if agent disabled),
`POST /agent/plan/refresh` (re-validate an edited draft; deterministic, no LLM),
`POST /agent/plan/commit`. The Planner page shows warnings, the AI's rationale, an
editable table (title/type/estimate/assignee/device/priority), and a mini-timeline.

## AI Timeline Simulator (since E5)

`app/simulator.py` + `pages/Simulator.tsx` + the `run_simulation` agent tool
(mirrored by `POST /simulations`). Scenarios are **computed in-memory, never
persisted, never written** (ADR-0006): the current plan becomes pure engine inputs,
a baseline run and a perturbed run are diffed, and mitigation candidates are ranked
by re-simulation.

- **Perturbations:** `leave` (person out for a range), `slip` (task delayed N days),
  `remove_task`, `add_task` (optionally `after_task_id` for a dependency).
- **Output:** affected tasks (baseline vs scenario spans, per-task delay,
  became-critical flags), predicted end-date delay, critical-path change, ranked
  reassignment **mitigations** each with an explanation, recovered days, new end
  date, confidence, and a machine-executable `apply` payload
  (`update_tasks` shape). Deterministic for a given scenario.
- **Applying a mitigation** goes through the normal audited endpoints
  (`PUT /tasks/{id}`) from the Simulator page or the ChatWidget — never a backdoor,
  and never automatically.

## Guardrails

- Keep `temperature` low for tool selection; validate/parse tool args defensively (the
  loop already tolerates bad JSON).
- Never expand a tool's blast radius silently — a tool that can delete or mass-reassign is
  an ADR + a confirmation flow.
- The model must never set `confirm=true` on its own — only after an explicit user yes.
- Small local models miss sometimes: keep tool schemas tight, descriptions concrete, and
  prefer several narrow tools over one do-everything tool.
