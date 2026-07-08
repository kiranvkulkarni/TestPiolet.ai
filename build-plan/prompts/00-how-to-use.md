# How to use these prompts

Each file is a ready-to-paste prompt for one milestone (see `../ROADMAP.md`). Workflow:

1. In Claude Code, make sure `CLAUDE.md` is loaded (it is, if it's in the repo root).
2. Paste the milestone prompt as your message. It already tells Claude which files to
   read first, the requirements, the DB/API/UI changes, and the acceptance criteria.
3. Let Claude follow the feature lifecycle in `CLAUDE.md` (design → build → test → docs).
4. Review against the **Acceptance criteria** at the bottom of the prompt before merging.
5. Do one milestone per branch/PR. Don't jump ahead.

Prompts are a starting point — tighten them with anything specific you want. Keep them
updated as the code changes so they stay a faithful "next step".

Template for writing your own:

```
## Objective
<one sentence>

## Read first
<the exact docs/files to load>

## Functional requirements
<bulleted, testable>

## Database changes
<tables/columns/migration>

## API changes
<endpoints, request/response>

## Frontend
<pages/components, Query hooks, UX notes>

## Acceptance criteria
<checklist that proves it works>

## Out of scope
<what NOT to touch this round>
```
