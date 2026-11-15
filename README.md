# {{CLIENT_NAME}} · Project Repo

Agent-optimised project repository for the {{CLIENT_NAME}} client project at {{AGENCY_NAME}}.
Project knowledge lives in an [Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format)
v0.2 bundle (`.okf/`), maintained by three agent skills. Tooling version: `okf-tooling 0.1.1`.

---

## Quick start

| Say | Skill | What happens |
|---|---|---|
| `start session` | `start-session` | Read-only briefing: `AGENTS.md`, `.okf/index.md`, the debt report, open runs. Never pulls or commits. |
| `end session` / `wrap up` | `end-session` | Screens what the session produced, drafts knowledge, shows **one review screen**, then stamps, commits and pushes. |
| `catch up` | `end-session` (catch-up mode) | Same pipeline over recent commits that no close has covered yet. |
| `log this email` / `log this meeting` | `log-comms` | Screens a source and keeps a Comms record; raw text never enters git. |
| `log this` / `log quick task` | `log-mode-a` | One screened line in `inbox/quick-*.md` for the next close. |

Every agent (Claude Code, Codex, Cursor, Gemini) starts from `AGENTS.md`.

---

## Repo structure

```
AGENTS.md            Agent entry file (CLAUDE.md, GEMINI.md and .cursor/rules import it)
okf.config           Per-repo settings: branch, tracker, topics, refusal destinations, reviewers
.okf/                Knowledge bundle (OKF v0.2)
  index.md           Generated index; start here
  client.md          The client and the engagement
  decisions/ rules/ findings/ people/ systems/ runbooks/ comms/
inbox/               Short-lived screened notes; carried.md is the follow-up event log
.agent/
  instructions.md    Standing rules for every session
.agents/skills/      The four pipeline skills (.claude/skills/ holds discovery stubs)
docs/
  specs/             Project specs and shared SoW (outside the bundle)
  client-comms/      Reports sent to the client
scripts/
  okf-check.py       Rules, screening, run state, stamp, index, debt report (stdlib only)
  okf_validate.py    Vendored OKF conformance validator
.github/workflows/okf.yml   Checks on every push; weekly log and debt issue
tests/               Tooling tests (not copied into client repos)
```

---

## The debt report

`python scripts/okf-check.py --report debt` (read-only, under 10 seconds) lists knowledge not yet
extracted: inbox notes, old carried items, verified files changed since, concepts past
`stale_after`, commits since the last close, uncommitted changes, open runs and unpushed closes.
A weekly GitHub issue "OKF debt — week YYYY-Www" carries it plus a five-concept spot check.

## Running the checks

```bash
python scripts/okf-check.py            # rules C1-C24 on the bundle (0 = no blocking finding)
python scripts/okf_validate.py .okf    # OKF v0.2 conformance (needs PyYAML)
python -m unittest discover -s tests/okf -t .
```

Python 3.11 or later (`py -3` on Windows).

---

## First-time setup checklist

- [ ] Fill in every `<…>` placeholder in `okf.config` and `.okf/client.md` (the check lists them as C24)
- [ ] Fill in the `{{PLACEHOLDERS}}` in `.agent/instructions.md` and this README
- [ ] Add people as `.okf/people/<first-last>.md` (role and organisation only)
- [ ] Fill in `docs/specs/sow-shared.md` from the shared SoW
- [ ] Enable GitHub Actions; confirm the `okf` workflow passes
- [ ] Run "review migration decisions" once to confirm the starting Decisions

## Copying the tooling into an existing repo

Copy from the template tag `okf-tooling-v<version>`: `scripts/okf-check.py`,
`scripts/okf_validate.py` (+ `.LICENSE`), `.agents/skills/*/SKILL.md`, `.claude/skills/*/SKILL.md`
and `.github/workflows/okf.yml`. Do not copy `tests/`. A tooling fix is copied into every pilot
repo in the same sitting with commit subject `chore: okf-tooling <version>`.

---

## Key docs

- **[OKF adopted](.okf/decisions/2026-11-13-okf-adopted.md)** — why the knowledge bundle replaced the v1 layout
- **[Shared SoW](docs/specs/sow-shared.md)** — project scope, deliverables, milestones (no financials)
- **[v1 Implementation Spec](docs/specs/ATB-Agent-Repo-Implementation-Spec.md)** — history: the superseded layout
- JIRA: https://{{JIRA_DOMAIN}}/jira/software/projects/{{JIRA_PROJECT_KEY}}
