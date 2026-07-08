# ADR-0002: Current stack (recorded as-is)

- **Status:** accepted
- **Date:** 2026-07-07

## Context
Recording the stack the working product already uses, so future changes are deliberate.

## Decision
- Backend: FastAPI · SQLAlchemy 2.0 · Pydantic v2 · JWT (python-jose, HS256) · bcrypt.
- DB: SQLite (dev) / PostgreSQL (LAN) via `psycopg2`.
- AI: on-prem, OpenAI-compatible LLM (Ollama / Samsung Gauss / Intel OpenVINO) through
  the `openai` client with tool calling.
- Frontend: React 19 · Vite · TypeScript · Tailwind v4 · Radix UI · TanStack Query ·
  Zustand · axios · react-router v7 · Recharts · `gantt-task-react` · date-fns.

## Consequences
On-prem LLM keeps QA data local. One Python codebase for API + AI. React/Radix/Tailwind
give a composable, themeable UI. `gantt-task-react` gets us a chart quickly but likely
caps the editable-workspace ambition (see ADR-0004).

## Alternatives considered
Hosted LLM (rejected: data residency). MySQL (not used here; the repo targets SQLite/
Postgres). A backend service layer (deferred — add only when a feature needs it).
