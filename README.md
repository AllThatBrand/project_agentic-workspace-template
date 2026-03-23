# {{CLIENT_NAME}} · Project Repo

Agent-optimised project repository for the {{CLIENT_NAME}} client project at {{AGENCY_NAME}}.

---

## Quick start

### Starting a session (Cursor / VS Code / terminal)
Say or type: `start session`
The agent will pull latest, show what changed, and brief you from CONTEXT.md.

### Starting a session (Claude.ai web)
Paste the contents of `.agent/CONTEXT.md` as your first message.

### Logging a quick task (Mode A)
Say: `log this` or `log mode a`

### Ending a session
Say: `end session` or `wrap up`
The agent will write a session note and stage your commits.

---

## Repo structure

```
.agent/          Agent front door — always read first
  CONTEXT.md     Auto-generated snapshot of current project state (≤300 words)
  project.md     Client, stack, contacts, tools — fill in once at kickoff
  instructions.md Standing rules for every session
  skills/        Agent skills — start-session, log-mode-a, end-session

docs/
  decisions/     Architectural and client decisions (ADRs)
  specs/         Project specs and shared SoW
  client-comms/  Key client communication summaries

tasks/
  current-sprint.md  Auto-synced from JIRA every Sunday 20:00
  backlog.md         Groomed backlog overview

memory/
  quick-tasks.md     Mode A work log — append-only
  sessions/          Session notes — one file per day

digest/            n8n PR landing zone — daily Slack + Gmail digest

scripts/
  generate-context.py  Rebuilds CONTEXT.md (run by GitHub Actions)
  route-digest.py      Routes digest CSV to correct folders

.github/workflows/
  context-update.yml   Regenerates CONTEXT.md on every merge
  digest-router.yml    Routes digest on merge, then regenerates CONTEXT.md

website/           Git submodule → {{CLIENT_NAME}} website repo
```

---

## Automation

| What | When | How |
|------|------|-----|
| CONTEXT.md regenerated | Every merge to main | GitHub Actions: context-update.yml |
| Daily digest PR created | 3 AM | n8n: daily-digest workflow |
| Digest routed to folders | On the PM's PR merge | GitHub Actions: digest-router.yml |
| Sprint synced from JIRA | Sunday 20:00 | n8n: sprint-sync workflow |
| Session note committed | After /session command | n8n: session-webhook workflow |

---

## First-time setup checklist

- [ ] Fill in all `{{PLACEHOLDERS}}` in `.agent/project.md`
- [ ] Write project-specific rules in `.agent/instructions.md`
- [ ] Fill in `docs/specs/sow-shared.md` from the shared SoW
- [ ] Set GitHub repo variables: `PROJECT_NAME={{CLIENT_NAME}}`, `JIRA_PROJECT_KEY={{JIRA_PROJECT_KEY}}`
- [ ] Add website repo as submodule: `git submodule add [url] website/`
- [ ] Run `python scripts/generate-context.py` locally to verify
- [ ] Push and confirm `context-update.yml` runs cleanly
- [ ] Set up n8n daily-digest and sprint-sync workflows
- [ ] Register Slack `/session` slash command

---

## Team

| Person   | Role      | Availability |
|----------|-----------|--------------|
| [Name]   | CEO       | —            |
| [Name]   | Junior PM | Part time    |
| [Name]   | Developer | Full time    |
| [Name]   | QA        | Part time    |

---

## Key docs

- **[Implementation Spec](docs/specs/ATB-Agent-Repo-Implementation-Spec.md)** — full specification: workflow, folder structure, file templates, automation scripts, and implementation checklist
- **[Mermaid Diagrams](docs/specs/ATB-Agent-Repo-Mermaid-Diagrams.md)** — visual diagrams of the workflow, digest pipeline, sync rules, and folder ownership
- **[Shared SoW](docs/specs/sow-shared.md)** — project scope, deliverables, milestones (no financials)
- **[First decision](docs/decisions/2026-03-22-prim-agent-repo-structure-adopted.md)** — why this repo structure was adopted
- JIRA: https://{{JIRA_DOMAIN}}/jira/software/projects/{{JIRA_PROJECT_KEY}}
