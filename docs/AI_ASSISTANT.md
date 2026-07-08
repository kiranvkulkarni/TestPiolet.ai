# AI Assistant

The agent already works. This documents how it works and how to extend it toward the
Operations Assistant / Planner / Simulator vision without breaking the pattern.

## How it works today

- **Transport:** the `openai` Python client points at a local, OpenAI-compatible LLM
  (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`) — Ollama, Samsung Gauss, or Intel OpenVINO.
  Nothing leaves the network.
- **Loop:** `agent_engine.run_agent(messages, db, current_user_id)` sends the system
  prompt + conversation with `tools=TOOLS`, `tool_choice="auto"`, `temperature=0.1`, and a
  10-iteration guard. On each `tool_calls`, it dispatches via `TOOL_FN_MAP`, appends tool
  results, and loops until the model returns plain text. Returns `(reply, actions)`.
- **Exposure:** `POST /agent/chat` (with `GET /agent/status` for a health/enabled check).
- **Frontend:** `components/agent/ChatWidget.tsx` — floats on every page.

### The system prompt encodes real QA workflow
It lists the exact 15 task-type strings and a workflow: check workload before assigning,
fetch a valid `test_request_id` before creating, resolve device names to IDs, check leave
conflicts when dates are given, confirm before creating 5+ tasks, offer to log actual
hours on completion, and ask one clarifying question when ambiguous. Preserve this
discipline when extending.

## The ten tools (today)

Read: `get_team_members`, `get_workload_summary`, `get_projects`, `get_test_requests`,
`get_tasks` (filters: status/assignee/project/overdue), `get_device_models`,
`check_leave_conflicts`.
Write: `create_task`, `create_tasks_bulk`, `update_task`.

Each is a plain function `(db, **kwargs) -> dict` in `agent_tools.py`, mirrored by a JSON
schema in `TOOLS` and an entry in `TOOL_FN_MAP`. **Tools are the only way the AI touches
the DB.**

## How to add a tool (the pattern — follow it exactly)

1. Write `def my_tool(db: Session, ...args, **_) -> dict:` in `agent_tools.py`, returning a
   small JSON-serializable dict. Reuse existing models/queries; keep it defensive.
2. Add its schema to `TOOLS` in `agent_engine.py` (`type: "function"`, name, description,
   parameters with the **exact enum strings** where relevant).
3. Register it in `TOOL_FN_MAP`.
4. If it mutates data, also expose/confirm a matching REST endpoint (no private backdoors),
   and write an `AuditLog` row.

## Extension plan (roadmap)

### Explainable AI (do this early, it's cross-cutting)
Have write tools return not just the change but a **rationale** and **confidence**, and
have `run_agent` surface an `explanation` alongside `actions`. Example the UI can render:
"Moved 14 tasks · Priya at 95% capacity, Ravi had room · dependencies still valid · end
date unchanged · confidence 0.9." Destructive/bulk actions should require a confirmation
turn before committing.

### Operations Assistant tools to add
`reschedule_task(s)` (respecting calendars/leave), `set_dependency` / `remove_dependency`,
`assign_bulk` (balance by workload), `get_critical_path(project|cycle)`,
`find_underloaded_testers`, `explain_schedule_change`.

### AI Project Planner
A tool (or small orchestration) that turns a brief — "Galaxy Camera v16 next week: HDR,
Night Mode, Portrait Video, 50MP, Expert RAW; 5 testers, 2 devices, 3 days" — into a
**preview** of test requests + tasks + estimates + assignments + dependencies. Present it,
let the manager edit, then commit via the existing create tools. Never auto-commit.

### AI Timeline Simulator
A **non-destructive** path: fork the current plan into a scenario, apply a perturbation
(leave, slip, scope), recompute via the scheduling module, and return affected tasks,
predicted delay, critical-path change, and ranked mitigations — with explanations. Needs
the real dependency model + scheduling module first (see DATA_MODEL notes).

## Guardrails

- Keep `temperature` low for tool selection; validate/parse tool args defensively (the
  loop already tolerates bad JSON).
- Never expand a tool's blast radius silently — a tool that can delete or mass-reassign is
  an ADR + a confirmation flow.
- Small local models miss sometimes: keep tool schemas tight, descriptions concrete, and
  prefer several narrow tools over one do-everything tool.
