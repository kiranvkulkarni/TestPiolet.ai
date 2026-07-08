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
- `GET  /tasks/gantt` — Gantt-shaped payload (feeds `GanttView`).
- `POST /tasks` · `POST /tasks/bulk` · `POST /tasks/bulk-update`
- `GET  /tasks/{id}` · `PUT /tasks/{id}` · `PATCH /tasks/{id}/status` · `DELETE /tasks/{id}`
- `GET  /tasks/{id}/leave-conflicts` — assignee leave overlap check.
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

## AI agent
- `GET  /agent/status` — whether the agent is enabled + LLM reachable.
- `POST /agent/chat` — `{messages: [...]}` → `{reply, actions}` (runs the tool loop).

## Conventions for new endpoints
- Keep the resource prefix + verb pattern above; return Pydantic schemas from `schemas.py`.
- New write endpoints for the Gantt workspace belong on `/tasks` (e.g. move/resize/link);
  keep them small and idempotent-friendly for optimistic UI.
- Anything the AI should be able to do should have a normal endpoint **and** an
  `agent_tools` function — don't give the agent a private backdoor.
