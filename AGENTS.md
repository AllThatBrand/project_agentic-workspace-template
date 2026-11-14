# Agent entry · <client name>

Read this file first in every session. Standing rules live in `.agent/instructions.md`.

## Knowledge
Project knowledge lives in `.okf/` (Open Knowledge Format v0.2). Start at `.okf/index.md`. Types:
- **Decision**: what was chosen, by whom, when (`decisions/YYYY-MM-DD-<words>.md`).
- **Rule**: how we work, one topic per file (`rules/<topic>.md`, topics in `okf.config`).
- **Finding**: something checked and found true at a date (`findings/YYYY-MM-DD-<words>.md`).
- **Person**: role and organisation; never contact details (`people/<first-last>.md`).
- **Client**: the client and the engagement (`client.md`).
- **System**: a site, service or integration and how it is built (`systems/<name>.md`).
- **Runbook**: how to do a task; tool facts go in `runbooks/tools.md`.
- **Comms**: a screened record of an email, meeting or call (`comms/YYYY-MM-DD-<words>.md`).

## Writing knowledge
- Write new knowledge as drafts (`status: draft`). Only a review in end-session makes it `stable`.
- Say when you rely on a draft.
- Name yourself in `generated.by` as `agent:<tool>/<model>`.
- Find the right file before creating one: `python scripts/okf-check.py --closest "<title>"`.
- Never put prices, contract terms, contact details, personal matters, credentials or long quotes
  in git. Where they go instead is listed under `refuse:` in `okf.config`.

## Skills (trigger phrases)
- "start session": `.agents/skills/start-session/SKILL.md` (read-only; never pulls or commits).
- "end session", "wrap up", "catch up", "review migration <folder>": `.agents/skills/end-session/SKILL.md`.
- "log this email", "log this meeting": `.agents/skills/log-comms/SKILL.md`.
- "log this", "log quick task": `.agents/skills/log-mode-a/SKILL.md`.

No automatic end-session: a close runs only when the user asks for it.
