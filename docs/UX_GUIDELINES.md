# UX Guidelines

The product should feel fast and direct — closer to a modern design/dev tool than to a
traditional PM app. These apply to every screen.

## Invariants (never violate)

- **Keyboard-friendly everywhere.** Every primary action reachable without the mouse;
  visible focus states; `Esc` closes transient UI.
- **Edits feel instant.** Use optimistic updates (TanStack Query) and reconcile on the
  server response; never block the UI on a round-trip for a simple edit.
- **Inline edit over edit forms.** Double-click a name/field to edit in place; `Enter`
  saves, `Esc` cancels. Reserve modals for genuinely multi-field creation.
- **Avoid modals unless necessary.** Prefer inline, popovers, and side panels.
- **Never force a full-page reload.** Preserve scroll and context across actions.
- **Every feature exposes an API the AI can call.** UI and agent go through the same
  endpoints.
- **Explain AI actions.** When the agent changes things, show what changed and why
  (rationale + confidence), with an easy undo.

## Voice & microcopy

Name things by what the user controls, not the implementation. Active voice on controls
("Assign", "Approve", "Save changes"), and the same verb through the whole flow (a
"Publish" button produces a "Published" toast). Errors state what happened and how to fix
it, plainly; empty states invite the next action rather than just saying "no data".

## The Gantt workspace (flagship — see build-plan/prompts)

Treat it as the primary workspace, not a report:
- Drag a bar to move; drag edges to resize; the change persists and reschedules.
- Draw a dependency by dragging between tasks; reject cycles.
- Inline-edit the task title on the bar/row.
- Reassign by dragging a task to another person's row.
- Zoom day → week → month; virtualize so large plans stay smooth.
- Highlight the **critical path**; offer a **workload heatmap** overlay.
- Right-click for Duplicate / Split / Convert to Milestone / Create Dependency.
- Multi-select + bulk move; **undo/redo** on everything.
- Color by status, priority, or assignee (user-chosen).
Performance is a feature: aim for smooth interaction on large projects.

## AI assistant interactions

- Dockable/floating chat available everywhere (the existing ChatWidget).
- For 5+ or destructive actions, show a concise plan and require confirmation.
- Stream or promptly show progress; summarize actions taken with a rationale.
- Let the user click through from an AI action to the affected tasks in the Gantt/list.

## Accessibility & responsiveness

Respect reduced-motion; maintain color contrast (don't rely on color alone for status —
pair with label/icon); usable down to a laptop width, graceful on tablets.
