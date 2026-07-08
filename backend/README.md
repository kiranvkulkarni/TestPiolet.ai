# Backend — QA Task Assigner

FastAPI + SQLAlchemy 2.0. See the repo root `README.md` for the full run guide and
`../CLAUDE.md` for working rules.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env            # set SECRET_KEY
python -m app.seed              # demo data (also creates the schema)
python run.py                   # → http://localhost:8000 (/docs)
```

## Migrations (Alembic, since E0)

The schema is tracked with Alembic; `alembic/versions/` starts from a **baseline**
revision that matches `models.py` exactly.

- **Fresh database:** `alembic upgrade head` (or just boot the app / run the seed —
  `create_all` still runs on startup for dev convenience and produces the same schema).
- **Existing database created before Alembic:** stamp it once so it's tracked without
  being recreated: `alembic stamp head`.
- **Changing the schema (E1+):** edit `models.py`, then
  `alembic revision --autogenerate -m "<what changed>"`, review the generated file,
  and `alembic upgrade head`. Every schema change ships with a migration (ADR-0003).
- `alembic check` reports drift between `models.py` and the migration head.

The DB URL comes from `DATABASE_URL` in `.env` (see `alembic/env.py`); an environment
variable overrides it, which is handy for generating migrations against a scratch DB.

## Tests

```bash
python -m pytest tests -q
```

Covers the AI agent tools (the only path by which the AI touches the DB): read-tool
filters, workload math, leave-conflict detection, and the write tools including
validation failures, bulk rollback, `AuditLog` rows, and assignment notifications.
