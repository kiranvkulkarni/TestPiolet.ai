## Objective
Turn the Gantt from a read-only chart into the primary **editable workspace** (USP #1).

## Read first
`CLAUDE.md`, `docs/UX_GUIDELINES.md` (Gantt section), `docs/ARCHITECTURE.md`,
`docs/adr/0004-gantt-workspace-approach.md`, `frontend/src/pages/GanttView.tsx`,
`frontend/src/api/*`, and the E1 endpoints (`/tasks/move|resize|dependencies`, `/tasks/gantt`).

## Functional requirements
- Drag a bar to **move** it; drag its edges to **resize** — persist via E1 endpoints with
  **optimistic updates**, reconcile on response, roll back on error.
- **Draw dependencies** by dragging between tasks; reject cycles (surface the 4xx nicely).
- **Inline-edit** the task title on the row (double-click → input → Enter saves / Esc cancels).
- **Reassign** by dragging a task onto another person's row.
- **Zoom** day/week/month; **virtualize** rows/time so large projects stay smooth.
- **Critical-path** highlight (from the `critical` flag); **workload-heatmap** overlay toggle.
- **Right-click menu:** Duplicate · Split · Convert to Milestone · Create Dependency.
- **Multi-select** + bulk move; **undo/redo** (command stack) on all edits.
- Color-by selector: status / priority / assignee.

## Database changes
None (E1 covered them).

## API changes
None new; consume E1. If a genuine gap appears, add a small endpoint + ADR.

## Frontend
Rework `GanttView.tsx`. Per ADR-0004, prototype on `gantt-task-react`; if it can't do
dependency-drawing / inline edit / virtualization / undo-redo well, build a custom
SVG/canvas timeline component and record the decision in ADR-0004. Use TanStack Query for
data + optimistic mutations; keyboard support throughout.

## Acceptance criteria
- [ ] Move/resize/link/reassign all persist and reschedule dependents live.
- [ ] Inline title edit works with keyboard; undo/redo reverts the last N edits.
- [ ] Critical path + workload heatmap render correctly.
- [ ] Smooth interaction on a seeded large project (hundreds+ of tasks).
- [ ] ADR-0004 updated with the library-vs-custom outcome.

## Out of scope
AI-driven scheduling (E3+); scenarios (E5).
