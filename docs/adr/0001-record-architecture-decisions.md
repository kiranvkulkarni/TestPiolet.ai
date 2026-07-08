# ADR-0001: Record architecture decisions

- **Status:** accepted
- **Date:** 2026-07-07

## Context
This project is evolved largely via Claude Code across many sessions. Decisions made in
one session are invisible to the next unless written down.

## Decision
Keep a lightweight ADR per significant decision in `docs/adr/`, numbered sequentially,
using `template.md`. Small and factual. Claude reads these before architectural changes.

## Consequences
Future sessions see *why*, not just *what*. Small per-decision cost, enforced by the
Definition of Done.

## Alternatives considered
Comments in code (get lost); one big design doc (goes stale, no history). ADRs give a
decision log with provenance.
