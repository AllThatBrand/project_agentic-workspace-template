# Skill: start-session

## Trigger phrases
start session, start-session, let's start, begin session

## Purpose
Bring the agent and team member fully up to date before any work begins.
Always run this at the start of a session, before touching any task.

## Steps

### 1. Pull latest repo (local only)
If running in a local environment (Cursor, VS Code, terminal):
- Run: `git pull --rebase`
- If conflicts exist: stop and surface them to the user before continuing
- If already up to date: note it and continue

### 2. Show what changed since last session
- Run: `git log --oneline HEAD@{1}..HEAD`
- Summarise changes in plain language grouped by folder:
  - `.agent/` changes → context or instructions updated
  - `tasks/` changes  → sprint or backlog updated
  - `docs/` changes   → decisions or specs updated
  - `memory/` changes → previous session notes added
- If nothing changed: say so clearly

### 3. Read and surface CONTEXT.md
- Read `.agent/CONTEXT.md` in full
- Present to the user as a structured briefing:
  - Current sprint + end date
  - Open tasks in scope for this session
  - Last 3 decisions
  - Open Mode A items (if any)

### 4. Read instructions.md silently
- Read `.agent/instructions.md` in full
- Apply all standing rules for the duration of this session
- Do not summarise instructions back unless asked

### 5. Confirm readiness
End with a short confirmation:
> "Ready. {{CLIENT_NAME}} · Sprint [X] · [N] tasks in scope.
> Last session: [DATE] by [AUTHOR]. What are we working on?"

## Notes
- For Claude.ai web users with no local repo: skip steps 1 and 2.
  Paste CONTEXT.md as the first message instead.
- Never begin task work before completing this skill.
- If CONTEXT.md is missing or empty: alert the user — the repo
  may not be set up correctly yet.
