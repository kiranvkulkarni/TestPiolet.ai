## Objective
Answer "what happens if…" without touching the real plan: non-destructive scenarios with
predicted impact and ranked, explained mitigations.

## Read first
`CLAUDE.md`, `docs/PRODUCT_VISION.md` (Simulator), `docs/AI_ASSISTANT.md`, the E1
scheduling module, `docs/DATA_MODEL.md` (scenarios note).

## Functional requirements
- A **scenario** = a non-destructive fork of the current plan (tasks + dependencies +
  calendars). Store it (table with JSON payload) or compute in-memory — decide + ADR.
- Perturbations: **resource leave** (person out for a range), **task slip** (delay N days),
  **scope change** (add/remove tasks).
- Recompute via the scheduling module; diff against the baseline → affected tasks,
  **predicted delay**, critical-path change.
- **Mitigations:** search reassignment/resequencing options, rank them, and **explain**
  each ("reassign 3 tasks to Ravi → recovers 2 days; end date restored; confidence 0.85").
- Expose as an agent tool (`run_simulation`) and/or a REST endpoint; surface results as a
  Gantt overlay comparing baseline vs scenario.

## Database changes
Optional `scenarios` table (id, project_id, name, perturbation JSON, result JSON) + migration.

## API changes
`POST /simulations` (or agent tool `run_simulation`) → impact + mitigations; read-only.

## Frontend
A scenario panel + Gantt overlay (baseline vs simulated), affected-task list, delay
summary, ranked mitigations with explanations and a "apply this mitigation" action that
routes through the normal (audited) mutation path.

## Acceptance criteria
- [ ] "Priya out next week" returns affected tasks + predicted delay + ranked mitigations,
      and the real plan is unchanged.
- [ ] Results are deterministic for a given scenario; explanations are present.
- [ ] Applying a mitigation goes through the audited endpoints, not a backdoor.

## Out of scope
Auto-applying mitigations without confirmation.
