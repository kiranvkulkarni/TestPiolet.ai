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

## Extension plan (roadmap)

### AI Project Planner (E4)
A tool (or small orchestration) that turns a brief — "Galaxy Camera v16 next week: HDR,
Night Mode, Portrait Video, 50MP, Expert RAW; 5 testers, 2 devices, 3 days" — into a
**preview** of test requests + tasks + estimates + assignments + dependencies. Present it,
let the manager edit, then commit via the existing create tools. Never auto-commit.

### AI Timeline Simulator (E5)
A **non-destructive** path: fork the current plan into a scenario, apply a perturbation
(leave, slip, scope), recompute via the scheduling module, and return affected tasks,
predicted delay, critical-path change, and ranked mitigations — with explanations.

## Guardrails

- Keep `temperature` low for tool selection; validate/parse tool args defensively (the
  loop already tolerates bad JSON).
- Never expand a tool's blast radius silently — a tool that can delete or mass-reassign is
  an ADR + a confirmation flow.
- The model must never set `confirm=true` on its own — only after an explicit user yes.
- Small local models miss sometimes: keep tool schemas tight, descriptions concrete, and
  prefer several narrow tools over one do-everything tool.
