## Objective
From a plain-English brief, generate a **preview** plan (requests + tasks + estimates +
assignments + dependencies) the manager can edit and then commit. Never auto-commit.

## Read first
`CLAUDE.md`, `docs/AI_ASSISTANT.md` (Planner section), `docs/DATA_MODEL.md`, the E1
scheduling module, the E3 tools, `backend/app/agent_engine.py`.

## Functional requirements
- A planning path (tool or small orchestration) that takes a brief like: "Galaxy Camera
  v16 next week — HDR, Night Mode, Portrait Video, 50MP, Expert RAW; 5 testers, 2 devices,
  3 working days" and produces a structured **draft**: test requests → tasks (with exact
  task-type enums) → estimates → suggested assignments (workload-balanced) → dependencies
  → a scheduled timeline, plus risks/resource conflicts.
- Return the draft as data for a **review UI**; validate it against the model (valid enums,
  real device/user IDs, no dependency cycles) before it can be committed.
- Commit only on explicit confirmation, reusing `create_tasks_bulk` + dependency tools;
  everything lands in `AuditLog`.

## Database changes
None (optionally persist drafts; if so, add a table + migration + ADR).

## API changes
`POST /agent/plan` (brief → validated draft); commit reuses existing create endpoints.

## Frontend
A planner panel: enter brief → see the proposed plan (editable table + mini-timeline) →
adjust → Commit. Show the AI's reasoning and any flagged conflicts.

## Acceptance criteria
- [ ] The example brief yields a credible, editable plan with valid enums/IDs and no cycles.
- [ ] Nothing is written until the manager clicks Commit.
- [ ] Committed plan appears in tasks/Gantt and in `AuditLog`.

## Out of scope
Non-destructive what-if simulation (E5).
