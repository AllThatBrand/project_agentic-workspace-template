---
type: Decision
title: OKF knowledge bundle adopted
description: Project knowledge moves into an OKF v0.2 bundle maintained by the end-session, log-comms and catch-up pipeline.
status: draft
generated: {by: "process:atb-okf-migration/0.1.0", at: 2026-11-14T21:45:21+01:00}
atb:
  supersedes: 2026-03-22-prim-agent-repo-structure-adopted.md
---
# OKF knowledge bundle adopted

**Date:** 2026-11-13. **Source:** the design "OKF knowledge pipeline" (AllThatBrand admin).

## Decision

Project knowledge lives in `.okf/` as typed concepts (Decision, Rule, Finding, Person, Client,
System, Runbook, Comms). New knowledge is written as drafts and becomes stable only through one
human review at the end of a session. Raw sources (mail, transcripts, chat logs) never enter git.

## Replaces

The 2026-03-22 structure: the auto-generated `.agent/CONTEXT.md`, the `memory/` layer, the
digest router and the JIRA sprint sync. `AGENTS.md` is the single agent entry file.
