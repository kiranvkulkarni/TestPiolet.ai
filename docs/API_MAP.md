# API Map

The current REST surface, from `backend/app/routers/`. All JSON; auth via
`Authorization: Bearer <jwt>` except login. Interactive docs at `/docs` when running.
Use this to find the endpoint to extend rather than inventing a new one.

## System & auth
- `GET  /health` — liveness.
- `POST /auth/login` — email + password → JWT.
- `GET  /auth/me` — current user.

## Users & team
- `GET  /users` · `POST /users` · `GET /users/{id}` · `PUT /users/{id}`
- `GET  /users/{id}/workload` — active-task load for one user.
- `GET  /users/underloaded?threshold_hours=` — testers with headroom (E3; mirrors the
  AI tool).

## Projects
- `GET /projects` · `POST /projects` · `GET /projects/{id}` · `PUT /projects/{id}` · `DELETE /projects/{id}`
- `GET /projects/{id}/test-requests` — requests under a project.

## Test cycles
- `GET /test-cycles` · `POST /test-cycles` · `GET /test-cycles/{id}` · `PUT /test-cycles/{id}` · `DELETE /test-cycles/{id}`

## Test requests
- `GET /test-requests` · `POST /test-requests` · `GET /test-requests/{id}` · `PUT /test-requests/{id}` · `DELETE /test-requests/{id}`
- `GET /test-requests/{id}/tasks` — tasks under a request.

## Tasks (the core)
- `GET  /tasks` — list (filters).
- `GET  /tasks/gantt` — Gantt-shaped payload (feeds `GanttView`); since E1 each row
  carries `dependencies` (predecessor ids), `critical` and `slack_days`; since E2 also
  `dependency_edges` (`{id, from_task_id}` — the row id is what `DELETE …/dependencies/{dep_id}` needs).
- `POST /tasks` · `POST /tasks/bulk` · `POST /tasks/bulk-update`
- `GET  /tasks/{id}` · `PUT /tasks/{id}` · `PATCH /tasks/{id}/status` · `DELETE /tasks/{id}`
- `GET  /tasks/{id}/leave-conflicts` — assignee leave overlap check.
- Scheduling (E1; each returns the task, the pushed dependents, and the critical path):
  `PATCH /tasks/{id}/move` (new start; snaps to the assignee's working calendar),
  `PATCH /tasks/{id}/resize` (new due date **or** working-day duration),
  `POST /tasks/{id}/dependencies` (link a predecessor; 400 on cycle, 409 on duplicate),
  `DELETE /tasks/{id}/dependencies/{dep_id}` (unlink; never reschedules).
- Operations (E3; REST mirrors of the AI tools — same code path, rationale + confidence
  + undo in the response; 5+ items need `confirm: true`):
  `POST /tasks/reschedule` (bulk leave-aware move), `POST /tasks/assign-balanced`
  (workload-balanced assignment), `GET /tasks/critical-path?project_id=`.
- Comments: `GET|POST /tasks/{id}/comments`, `PUT|DELETE /tasks/{id}/comments/{comment_id}`.
- Attachments: `GET|POST /tasks/{id}/attachments`,
  `GET /tasks/{id}/attachments/{att_id}/download`, `DELETE /tasks/{id}/attachments/{att_id}`.

## Leaves
- `GET /leaves` · `GET /leaves/calendar` · `GET /leaves/conflicts`
- `POST /leaves` · `GET /leaves/{id}` · `PUT /leaves/{id}` · `PATCH /leaves/{id}/approve` · `DELETE /leaves/{id}`

## Device models
- `GET /device-models` · `POST /device-models` · `PUT /device-models/{id}` · `DELETE /device-models/{id}`

## Dashboard & reports
- `GET /dashboard/summary` · `/team-workload` · `/task-types` · `/project-progress` · `/overdue` · `/upcoming-leaves`
- `GET /dashboard/export/tasks` — CSV export (accepts filters).

## Notifications
- `GET /notifications` · `GET /notifications/unread-count` · `PATCH /notifications/{id}/read` · `POST /notifications/read-all`

## Simulations
- `POST /simulations` — `{project_id?, perturbations: [...]}` → non-destructive what-if
  (E5, ADR-0006): affected tasks, predicted delay, critical-path change, ranked
  mitigations with `apply` payloads. **Read-only** — mirrors the agent's
  `run_simulation` tool.

## AI agent
- `GET  /agent/status` — whether the agent is enabled + LLM reachable.
- `POST /agent/chat` — `{messages: [...]}` →
  `{reply, actions, explanation, pending_confirmation}` (runs the tool loop; each
  committed write carries `{tool, rationale, confidence}` in `explanation`).
- Planner (E4, manager-only): `POST /agent/plan` (brief → validated draft; writes
  nothing), `POST /agent/plan/refresh` (re-validate/re-schedule an edited draft;
  deterministic, no LLM), `POST /agent/plan/commit` (create the reviewed draft via the
  audited agent tools).

## Conventions for new endpoints
- Keep the resource prefix + verb pattern above; return Pydantic schemas from `schemas.py`.
- New write endpoints for the Gantt workspace belong on `/tasks` (e.g. move/resize/link);
  keep them small and idempotent-friendly for optimistic UI.
- Anything the AI should be able to do should have a normal endpoint **and** an
  `agent_tools` function — don't give the agent a private backdoor.
