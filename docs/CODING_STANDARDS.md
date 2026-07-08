# Coding Standards

Match the code that's already here. These are the conventions that keep new work
consistent with the existing project.

## Backend (Python / FastAPI)

- **Structure:** one router file per resource under `app/routers/`, mounted in `main.py`.
  Keep handlers thin; small helpers are fine. Don't introduce a service/repository layer
  unless a feature clearly needs it — and if you do, that's an ADR.
- **Types:** full type hints. Pydantic v2 schemas in `schemas.py` for every request/
  response; never return raw ORM objects.
- **DB access:** depend on `get_db`; use SQLAlchemy 2.0 style. Commit in the handler/tool
  that owns the mutation. Watch N+1s on list endpoints.
- **Enums:** use the `models.py` enums; when serializing, remember values may be enum or
  str (existing tools use `x.value if hasattr(x, "value") else str(x)`).
- **Auth:** protect endpoints with the current-user / role dependencies in `auth.py`.
- **Errors:** raise `HTTPException` with a clear status + message; don't leak stack traces.
- **AI tools:** pure-ish functions `(db, **kwargs) -> dict`, defensive parsing, small JSON
  results. Keep the tool and a real REST endpoint in sync.
- **Audit:** write an `AuditLog` row on meaningful mutations (target: uniformly).
- **Style:** PEP 8; if you add tooling, `ruff` + `black` (line length 100) is the default.
- **Migrations:** Alembic (since E0, ADR-0003) — every schema change ships with a
  migration: edit `models.py`, `alembic revision --autogenerate`, review, `upgrade head`.
  `alembic check` must report no drift. Workflow details in `backend/README.md`.

## Frontend (React / TS)

- **Components:** function components + hooks only. Reuse `components/shared/*` (Modal,
  Badge, Avatar, ConfirmDialog) and Radix primitives; don't hand-roll a new dialog.
- **Server state:** TanStack Query — one hook per resource wrapping an `api/` function.
  Mutations invalidate the right query keys; prefer **optimistic updates** for edits.
- **Client state:** Zustand (`authStore` pattern). Don't put server data in Zustand.
- **HTTP:** go through the shared axios client in `api/`; it attaches the JWT. Add new
  calls as typed wrappers, not inline `fetch`.
- **Types:** shared types in `types/`; keep them aligned with the backend schemas.
- **Styling:** Tailwind v4 utility classes; compose conditional classes with `clsx` /
  `tailwind-merge`. Icons from `lucide-react`; toasts via `react-hot-toast`.
- **Routing:** `react-router-dom` v7; pages under `pages/`, mounted in `App.tsx`.
- **UX:** honor the invariants in `UX_GUIDELINES.md` (keyboard, instant edits, inline
  edit, minimal modals, no full reloads).

## Git

- Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Small, reviewable changes — ideally one feature/milestone slice per PR.
- Update the relevant `docs/` file and the changelog in the same change.

## Definition of Done

Code matches these standards · risky logic is tested · backend boots, frontend builds,
seed still works · docs + changelog updated · ADR added if a decision was made.
