## Objective
Make the schema safe to evolve and the AI tools trustworthy: add Alembic migrations,
standardize audit logging, and test the agent tools. No user-facing change.

## Read first
`CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/adr/0003-introduce-migrations.md`,
`backend/app/database.py`, `backend/app/models.py`, `backend/app/agent_tools.py`.

## Functional requirements
- Add Alembic; generate a **baseline** migration matching current `models.py` (so existing
  SQLite/Postgres DBs are stamped, not recreated). Document `alembic upgrade head` in the
  backend README.
- Add a small helper to write `AuditLog` rows and call it consistently on task/leave/
  project mutations in the routers and in the AI write tools (`create_task`,
  `create_tasks_bulk`, `update_task`).
- Add `pytest` and tests for the read tools (`get_tasks` filters, `get_workload_summary`,
  `check_leave_conflicts`) and the write tools against a temporary SQLite DB + seeded data.

## Database changes
No schema change. Alembic baseline only.

## API changes
None.

## Frontend
None.

## Acceptance criteria
- [ ] `alembic upgrade head` works on a fresh SQLite DB and matches `create_all` output.
- [ ] Mutations write `AuditLog` rows (verified in a test).
- [ ] `pytest` green; agent-tool tests cover filters + a create + an update.
- [ ] Backend still boots; seed still works.

## Out of scope
Any new feature or endpoint; changing the schema shape (that starts in E1).
