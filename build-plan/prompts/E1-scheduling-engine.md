## Objective
Give the plan real, typed dependencies and a pure scheduling engine (critical path,
leave-aware dates), plus write endpoints to move/resize/link tasks. Backend only.

## Read first
`CLAUDE.md`, `docs/DATA_MODEL.md` (dependency limits), `docs/ARCHITECTURE.md` (evolution
seams), `backend/app/models.py`, `backend/app/routers/tasks.py`.

## Functional requirements
- New `task_dependencies` table: `(id, from_task_id, to_task_id, type)` with `type` =
  finish_to_start for now; enforce **no cycles** on create. Keep the legacy `depends_on`
  working (migrate it into the table or read both) — decide and ADR it.
- New module `backend/app/scheduling.py` — **framework-free** (no FastAPI/SQLAlchemy
  imports): given tasks (id, estimate/duration, fixed dates) + dependencies + a working
  calendar (weekends + approved leave per assignee), compute derived start/end and the
  **critical path**. Deterministic. Unit-tested (cycles, parallel paths, calendar gaps).
- New endpoints on `/tasks`: `PATCH /tasks/{id}/move` (new start, shift/keep duration),
  `PATCH /tasks/{id}/resize` (new duration/due), `POST /tasks/{id}/dependencies`,
  `DELETE /tasks/{id}/dependencies/{dep_id}`. Each returns the affected/rescheduled tasks.
- Extend `GET /tasks/gantt` to include dependencies + a `critical` flag per task.

## Database changes
Add `task_dependencies` (+ Alembic migration). No destructive changes to `tasks`.

## API changes
The move/resize/link/unlink endpoints above; enriched `/tasks/gantt` payload.

## Frontend
None this round (E2 consumes it). Optionally verify via `/docs`.

## Acceptance criteria
- [ ] `scheduling.py` has no framework imports and >90% test coverage on its logic.
- [ ] Creating a cyclic dependency is rejected with a clear 4xx.
- [ ] Moving a task reschedules dependents and recomputes the critical path.
- [ ] Approved leave shifts an assignee's computed dates.
- [ ] Migration applies cleanly; backend boots; seed works.

## Out of scope
Any UI; AI tools (E3); non-destructive scenarios (E5).
