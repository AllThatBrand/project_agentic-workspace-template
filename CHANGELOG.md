# Changelog

All notable changes to this template are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [1.2.0] — 2026-11-23

### Changed
- The website repo is no longer a `website/` Git submodule. It is a separate repo, cloned next to the project repo and recorded in `.agent/project.md` (`Repo (website)`, `Website checkout`). ADR: `docs/decisions/2026-11-23-website-repo-separate-not-submodule.md` (ATB-200).
- `README.md`, the implementation spec (§3, §7) and diagram 5 updated to match.

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
