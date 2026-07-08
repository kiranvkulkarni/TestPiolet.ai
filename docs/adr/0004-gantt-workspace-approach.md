# ADR-0004: Editable Gantt workspace approach

- **Status:** accepted — **custom timeline component** (decided in E2)
- **Date:** 2026-07-07, decided 2026-07-08

## Context

The flagship USP is an *in-place editable* Gantt workspace (drag/resize/dependency-draw/
inline-edit/critical-path/heatmap/undo-redo, smooth on large plans). The original
`gantt-task-react` gave a mostly read-only chart.

## Decision

**Build custom** (`frontend/src/components/gantt/`). The E2 evaluation of
`gantt-task-react` was quick and conclusive: it offers `onDateChange` drag/resize, but
has **no** dependency drawing, no inline edit, no drag-to-reassign, no multi-select,
no virtualization (it renders every row — unusable at the 450-task perf project), no
undo/redo hooks, and its row model can't express assignee grouping for the workload
heatmap. Rather than fork the library, we own a small custom stack:

- `timeline.ts` — pure date↔pixel math, zoom scales, header building.
- `useUndoStack.ts` — command stack (undo/redo closures around API calls).
- `GanttWorkspace.tsx` — one scroll container, manually windowed rows
  (only visible rows render), sticky label column, absolutely-positioned bar divs,
  one SVG overlay for dependency arrows, CSS-gradient weekend shading.

`gantt-task-react` was removed from `package.json`.

## Consequences

We own the interaction surface (that *is* the USP) and the performance: windowed rows
keep the DOM at ~40 nodes-per-screen regardless of plan size; day-grid lines are CSS
gradients, not DOM. Cost: our own pointer-event handling (drag thresholds, pointer
capture) and date math — mitigated by keeping `timeline.ts` pure and the server as the
source of truth for scheduling (optimistic UI reconciles via refetch; E1 endpoints do
the real rescheduling).

## Alternatives considered

Commit to the library up front (rejected — caps the USP, no path to dependency drawing
or virtualization). Fork the library (rejected — its internal rendering model still
re-renders everything). Canvas rendering (deferred — DOM+SVG is smooth at the current
scale and keeps accessibility/text rendering simple; revisit only if plans grow 10×).
