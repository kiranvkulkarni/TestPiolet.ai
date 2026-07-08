# Roadmap — the QAOS evolution

The app already covers auth, team, projects, cycles, requests, tasks (Kanban + list +
bulk + comments + attachments), a read-only Gantt view, dashboard, reports, leave,
notifications, and a working 10-tool AI agent. **We are not rebuilding any of that.**
This roadmap is the *delta* toward the QAOS vision. Work top to bottom, one at a time;
each milestone has a ready-to-paste prompt in `prompts/`.

## Definition of Done (every milestone)
Code matches `docs/CODING_STANDARDS.md` · risky logic tested · backend boots + frontend
builds + seed works · relevant `docs/` file + CHANGELOG updated · ADR if a decision was
made.

---

### ✅ E0 — Harden the baseline → `prompts/E0-harden-baseline.md`
Introduce Alembic (ADR-0003) with a baseline migration; standardize `AuditLog` writes on
mutations; add tests for the agent tools. Enables safe schema evolution. **No user-facing
change.**

### ✅ E1 — Dependencies + scheduling engine → `prompts/E1-scheduling-engine.md`
Add a `task_dependencies` table (typed, many-to-many; reject cycles) and a **pure-Python
scheduling module** (topological order, forward/backward pass, critical path, respects
leave/working days). Add `move` / `resize` / `link` / `unlink` write endpoints on `/tasks`.
Backend-first; no new UI yet. **Foundation for the Gantt workspace and the Simulator.**

### ✅ E2 — Editable Gantt workspace (USP #1) → `prompts/E2-gantt-workspace.md`
Turn the Gantt into the primary workspace: drag-move, edge-resize, draw dependencies,
inline-edit titles, drag-to-reassign, zoom, critical-path highlight, workload-heatmap
overlay, right-click menu, multi-select, undo/redo, virtualization. Prototype on
`gantt-task-react`, fork to custom if needed (ADR-0004).

### ✅ E3 — Explainable AI + Operations Assistant (USP #2) → `prompts/E3-explainable-ai.md`
`run_agent` returns a rationale + confidence with each action; destructive/bulk actions
get a confirmation turn. Add tools: `reschedule_tasks`, `set_dependency`,
`remove_dependency`, `assign_bulk` (workload-balanced), `get_critical_path`,
`find_underloaded_testers`. Surface explanations in the ChatWidget.

### ✅ E4 — AI Project Planner → `prompts/E4-ai-planner.md`
A plain-English brief → a **preview** of test requests + tasks + estimates + assignments +
dependencies (validated against the model). Manager edits, then commits via existing
create tools. Never auto-commit.

### ✅ E5 — AI Timeline Simulator → `prompts/E5-timeline-simulator.md`
Non-destructive scenarios: fork the plan, apply a perturbation (leave / slip / scope),
recompute via the scheduling engine, return affected tasks + predicted delay + critical-
path change + ranked mitigations, all explained. Overlay results on the Gantt.

---

## Post-v1 backlog
AI daily stand-up · AI release-readiness (confidence score) · knowledge search over test
history (vector/graph) · Docker Compose packaging · device-conflict / lab-utilization
view · timeline snapshots ("time machine") · Slack/Teams notifications.
