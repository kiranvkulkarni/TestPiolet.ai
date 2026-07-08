## Objective
Level up the agent into an Operations Assistant that reschedules/assigns intelligently and
**explains every action** with a confidence (USP #2).

## Read first
`CLAUDE.md`, `docs/AI_ASSISTANT.md` (the whole thing), `backend/app/agent_engine.py`,
`backend/app/agent_tools.py`, `frontend/src/components/agent/ChatWidget.tsx`, plus the E1
scheduling module + endpoints.

## Functional requirements
- Add tools (function + `TOOLS` schema + `TOOL_FN_MAP`, and a matching REST endpoint each):
  `reschedule_tasks` (leave/calendar-aware, via scheduling module), `set_dependency`,
  `remove_dependency`, `assign_bulk` (balance by workload), `get_critical_path`,
  `find_underloaded_testers`.
- **Explainable AI:** write tools return `{result, rationale, confidence}`; `run_agent`
  aggregates an `explanation` alongside `actions`. Example rationale: which constraints
  were checked, who had capacity, whether the end date moved.
- **Confirmation flow:** for bulk (5+) or destructive actions, the agent proposes a plan
  and waits for a "yes" turn before committing (extend the existing 5+ discipline).
- Write `AuditLog` rows for every AI mutation (actor = the agent + current user).

## Database changes
None beyond E1.

## API changes
New REST endpoints mirroring the new tools; `/agent/chat` response gains `explanation`.

## Frontend
ChatWidget: render the plan/confirmation step, the rationale + confidence per action, and
a link from an action to the affected tasks in the Gantt/list. Add an undo affordance.

## Acceptance criteria
- [ ] "Rebalance next week's camera sanity tasks off Priya" reschedules + reassigns, and
      returns a clear rationale + confidence.
- [ ] Bulk/destructive actions require confirmation before committing.
- [ ] Every AI mutation appears in `AuditLog`.
- [ ] Tools have tight schemas with exact enum values; tested against seeded data.

## Out of scope
Full plan generation (E4); non-destructive scenarios (E5).
