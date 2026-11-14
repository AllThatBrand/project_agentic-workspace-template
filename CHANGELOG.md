# Changelog

All notable changes to this template are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased] — 2.0.0

Released after the OKF pilots (kcm, terabeauty). Tooling version `okf-tooling 0.1.0`.

### Added
- `.okf/` OKF v0.2 knowledge bundle: `client.md`, typed folders, generated indexes
- `okf.config` — branch, tracker, topics, frozen and report folders, refusal destinations, reviewers, `paused`
- `AGENTS.md` — single agent entry file; `.cursor/rules/okf-core.mdc`
- `scripts/okf-check.py` — rules C1-C24 and C17b, screening, run state, stamp, carried log, index, log, debt and spot-check reports, migrate
- `scripts/okf_validate.py` — vendored OKF conformance validator (MIT)
- Skills in `.agents/skills/`: end-session (with catch-up and migration review), log-comms, start-session, log-mode-a; `.claude/skills/` stubs
- `.github/workflows/okf.yml` — check, unit, hook and weekly jobs
- `inbox/carried.md` — carried follow-up event log
- `tests/okf/` — unit tests, G6 trap fixture, golden-test comparison

### Removed
- `.agent/CONTEXT.md`, `scripts/generate-context.py`, `context-update.yml`
- `digest/`, `scripts/route-digest.py`, `digest-router.yml`
- `memory/` (MEMORY.md, quick-tasks.md, sessions/)
- `tasks/current-sprint.md`, `tasks/backlog.md` (work state lives in the tracker)
- `.agent/project.md` (now `.okf/client.md`), `.agent/skills/*.md`, `.cursorrules`

### Changed
- `CLAUDE.md`, `GEMINI.md` — plain files importing `@AGENTS.md` (were symlinks)
- `.agent/instructions.md` — no memory or `[skip ci]` rules; knowledge rules point to `AGENTS.md`
- `docs/decisions/2026-03-22-…` moved into `.okf/decisions/`, superseded by `2026-11-13-okf-adopted`
- `README.md` — new structure, entry points, debt report, how to copy the tooling

## [1.1.0] — 2026-03-26

### Added
- `memory/MEMORY.md` — memory index file for project-scoped agent memory
- Memory section in `.agent/instructions.md` — directs agent to use `memory/` as sole memory location
- `.gitignore` with `.claude/settings.local.json`
- `VERSION` file for template versioning
- `CHANGELOG.md`

### Changed
- `scripts/generate-context.py` — replaced JIRA project pointer with memory pointer in agent context output
- `.github/workflows/context-update.yml` — removed env var pass-through (`JIRA_PROJECT_KEY`, `PROJECT_NAME`); script now reads values from `.agent/project.md` directly
- `README.md` — removed "Set GitHub repo variables" setup step (no longer needed)

## [1.0.0] — 2026-03-22

### Added
- Initial template: `.agent/` structure (CONTEXT.md, project.md, instructions.md, skills/)
- `docs/` — decisions, specs, client-comms
- `tasks/` — current-sprint.md, backlog.md
- `memory/` — quick-tasks.md, sessions/
- `digest/` — n8n PR landing zone
- `scripts/` — generate-context.py, route-digest.py
- GitHub Actions workflows: context-update.yml, digest-router.yml
- README with repo structure, automation table, and setup checklist
