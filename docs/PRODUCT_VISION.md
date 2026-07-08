# Product Vision

## Today

QA Task Assigner is a working web app that replaces Excel-based tracking for Samsung
Android QA teams. It covers the real workflow: projects → test cycles → test requests →
tasks, with QA-specific task types (functional, non-functional KPI/FPS/memory/power,
Google compliance ITS/CTS/sensor-fusion), device models, leave planning, dashboards,
reports, and a natural-language AI agent that already assigns work and drafts plans
against a fully on-premises LLM.

## The gap

It's a good tracker, but the schedule is still mostly a *record* of decisions, not a
*model* the team (or the AI) can reason over. Dependencies are minimal (one `depends_on`
link), there's no critical path, the Gantt is a read-only view, and the AI can create and
update tasks but can't yet plan a cycle end-to-end, reschedule intelligently, or answer
"what happens if…".

## North star — "QAOS"

Evolve the product so the **plan becomes a computable model**. Once it is:
- the **AI can plan** a test cycle from a plain-English brief,
- the **AI can operate** the model safely through tools (and explain every action),
- the **AI can simulate** changes ("Priya is on leave next week — what slips?"), and
- the **Gantt becomes the workspace** where humans edit that same model directly.

## The two flagship USPs

### 1. In-place editable Gantt workspace
Not a reporting chart — the primary place work gets planned. Drag to move, drag edges to
resize, draw dependencies, inline-edit names, reassign by dragging across rows, zoom from
days to months, highlight the critical path, show a workload heatmap, undo/redo. Should
feel closer to a design tool than to MS Project.

### 2. Flexible AI Operations Assistant
The existing agent, leveled up: more tools (reschedule, set dependency, bulk assign,
generate plan, run simulation), a confirmation step for large/destructive actions, and
**Explainable AI** — every action returns a short rationale and a confidence, e.g.
"Moved 14 tasks · Priya was at 95% capacity, Ravi had room · dependencies still valid ·
end date unchanged · confidence 0.9."

## Further differentiators (roadmap, not v1)

AI Project Planner (brief → epics/tasks/deps/estimates/assignments preview → commit) ·
AI Timeline Simulator (non-destructive what-if) · AI daily stand-up summaries · AI
release-readiness check with a confidence score · knowledge search over test history ·
device-conflict / lab-utilization visualization · timeline snapshots ("time machine").

## Who it's for

- **QA Manager** (primary): owns assignment, capacity, and the release-readiness call.
- **Tester** (primary): needs clarity on what's assigned, blocked, and next.
- **Viewer** (secondary): read-only visibility for stakeholders.

## Principles (tie-breakers, earlier wins)

1. **The model is the product** — features either edit the plan or reason over it.
2. **The AI operates through tools, and always explains** — no black-box mutations.
3. **Fast enough to feel direct** — optimistic edits; the Gantt stays smooth on large plans.
4. **QA-native by default** — cycles, task types, devices, leave/workload are first-class.
5. **Trust through reversibility** — audit trail + undo; the AI is just another actor in it.
6. **Extend the working product** — evolve, don't rewrite.
