# ADR-0003: Introduce migrations before evolving the schema

- **Status:** accepted (implemented in E0)
- **Date:** 2026-07-07, accepted 2026-07-08

## Context
The schema is currently created with `Base.metadata.create_all` and there are no
migrations. The QAOS evolution will change the schema (real dependencies, scenarios,
richer audit). Without migrations, schema changes risk data loss on existing deployments.

## Decision
Introduce **Alembic** before the first schema-changing milestone. Baseline a migration
against the current models, then require a migration with every subsequent schema change.

## Consequences
Safe, reviewable schema evolution on the LAN/Postgres deployment; a small setup cost and
a new step in the feature lifecycle. SQLite dev still works.

## Alternatives considered
Keep `create_all` (rejected: unsafe once real data exists). Hand-written SQL migrations
(rejected: Alembic integrates with SQLAlchemy models we already have).
