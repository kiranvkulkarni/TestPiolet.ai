# ADR-0005: Typed dependency table; deprecate the single `depends_on` FK

- **Status:** accepted (implemented in E1)
- **Date:** 2026-07-08

## Context

Tasks had a single self-FK (`Task.depends_on`) — one predecessor per task, untyped.
The scheduling engine, the editable Gantt (E2) and the Simulator (E5) need real
many-to-many, typed dependencies with cycle rejection.

## Decision

Add a **`task_dependencies`** table (`from_task_id`, `to_task_id`, `type`, unique per
edge; `finish_to_start` is the only type today) and make it the **single source of
truth** for dependencies. For the legacy column:

1. The E1 migration **copies** existing `depends_on` values into the table
   (skipping NULLs and self-references).
2. `Task.depends_on` is **deprecated but kept** (no destructive change): legacy writes
   through `POST/PUT /tasks` are mirrored into the table (cycle-checked), and unlinking
   an edge clears a matching `depends_on` value. Scheduling, the Gantt payload and the
   new endpoints read **only** the table.
3. The column is dropped in a later milestone once nothing writes it (post-E3, when the
   AI tools move to `set_dependency`/`remove_dependency`).

## Consequences

Multiple predecessors per task, typed edges, and cycle safety enforced in one place
(`_validate_new_edge` + `scheduling.would_create_cycle`). Two storage places exist
during the deprecation window, held consistent by write-through mirroring — the cost of
not breaking existing clients/seed data.

## Alternatives considered

- Drop `depends_on` immediately (rejected: destructive; prompt requires no destructive
  change to `tasks`).
- Keep both readable and merge at query time (rejected: two sources of truth, drift).
