# ADR-0006: Timeline-simulator scenarios are computed in-memory, not persisted

- **Status:** accepted (implemented in E5)
- **Date:** 2026-07-08

## Context

The Timeline Simulator (E5) forks the current plan, applies a perturbation (leave /
slip / scope change), recomputes through the scheduling engine, and reports impact +
mitigations. The prompt left storage open: a `scenarios` table with JSON payloads, or
in-memory computation.

## Decision

**Compute in-memory; persist nothing.** `app/simulator.py` builds the baseline and the
perturbed scenario as pure `scheduling.py` inputs, runs both, and diffs the results.
A simulation is a read-only request/response — the real plan is never written, and no
scenario rows are created. The pure engine handles the 450-task perf project in
milliseconds, so recomputing on demand is cheaper than managing stored-scenario
staleness (every task/leave edit would invalidate saved results).

## Consequences

Zero schema/migration surface and no stale-scenario lifecycle. Scenarios are not
shareable or diffable-over-time yet — when "save this scenario / compare last week's"
becomes a real need, add the `scenarios` table then (id, project_id, name,
perturbations JSON, created_by) and supersede this ADR. Mitigations are applied only
through the normal audited endpoints, never from stored state.

## Alternatives considered

- `scenarios` table now (rejected: no current requirement for persistence; adds
  staleness + lifecycle for speculative value).
- Fork real rows into "shadow" tasks (rejected: pollutes the task table and every query
  that doesn't know about scenarios).
