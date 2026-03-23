# Skill: end-session

## Trigger phrases
end session, end-session, we're done for today, wrap up, closing session

## Purpose
Write a session summary that gives the next person (or agent) full context
without having to reconstruct what happened from git history.

## Steps

### 1. Write session note to memory/sessions/YYYY-MM-DD.md
Use today's date. If a file for today already exists, append with a
time-stamped separator: `--- [HH:MM] ---`

Use this structure exactly:
```
## Session · YYYY-MM-DD
**Who:** [person who ran the session]
**Duration:** [approximate]

**Sprint tasks worked on:**
- {{JIRA_PROJECT_KEY}}-123 · [what was done] · [status: in progress / done / blocked]

**Decisions made:**
- [Any decision that affects future work — even small ones]
- None (if nothing was decided)

**What the agent tried that didn't work:**
- [Failed approaches, dead ends — critical for the next session]
- None

**Open threads:**
- [Anything unresolved that needs follow-up]
- None

**Next session should start with:**
- [Specific instruction for the next person or agent]
```

### 2. Check for promotable Mode A items
Scan memory/quick-tasks.md for any items marked `needs-follow-up`.
If found, surface them:
> "These Mode A items may need attention before next session: [list]"

### 3. Commit changes (local only)
If running in a local environment:
- Stage all changes in `.agent/`, `docs/`, `tasks/`, `memory/`
- Suggest a commit message:
  `session: YYYY-MM-DD · [one line summary of what was done] [skip ci]`
- Wait for user confirmation before committing
- Never force push or commit to main directly

### 4. Confirm
> "Session closed. Summary written to memory/sessions/YYYY-MM-DD.md.
> [N] files committed. Next session: read CONTEXT.md and this summary."

## Notes
- The "what didn't work" section is the most valuable part.
  Agents repeat mistakes when this is empty.
- If the session was Mode A only (no sprint tasks): still run this skill —
  the session note confirms the quick task was handled.
- For Claude.ai web users: use Slack /session command and paste the
  generated summary — n8n will commit it to the repo automatically.
