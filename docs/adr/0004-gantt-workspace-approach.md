# ADR-0004: Editable Gantt workspace approach

- **Status:** proposed
- **Date:** 2026-07-07

## Context
The flagship USP is an *in-place editable* Gantt workspace (drag/resize/dependency-draw/
inline-edit/critical-path/heatmap/undo-redo, smooth on large plans). The current
`gantt-task-react` gives a mostly read-only chart.

## Decision
Prototype the interactions on top of `gantt-task-react` first. If it can't hit the
interaction/perf bar (likely for dependency drawing, inline edit, virtualization, undo/
redo), build a **custom SVG/canvas timeline** component. Decide at the end of the Gantt
milestone and record the outcome here.

## Consequences
Fast start via the library; a known fork point to a custom renderer if needed. Custom
means we own performance (virtualization) — accepted, since interaction quality is the USP.

## Alternatives considered
Commit to the library up front (risks capping the USP). Commit to custom up front (slower
to first value). Prototyping first balances both.
