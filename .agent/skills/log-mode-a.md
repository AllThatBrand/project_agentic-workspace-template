# Skill: log-mode-a

## Trigger phrases
log this, log mode a, log quick task, this was a quick fix log it

## Purpose
Capture Mode A work that happens outside the formal Scrum process.
Prevents quick tasks from disappearing with no trace.
Feeds the open Mode A items section of CONTEXT.md.

## Steps

### 1. Gather the four fields
Ask the user (or infer from conversation context) for:
- **Source:** where the request came from (Email / Slack / WhatsApp / Verbal)
- **Request:** one sentence — what was asked
- **Resolution:** one sentence — what was done
- **Status:** open / resolved / needs-follow-up

If all four are clear from the conversation, do not ask — infer and confirm.

Example confirmation:
> "Logging: Email from client · requested hero image swap ·
> updated Framer component · resolved. Correct?"

### 2. Append to memory/quick-tasks.md
Append a single row in this format:
```
| YYYY-MM-DD | Source | Request (one sentence) | Resolution (one sentence) | Status |
```

Never overwrite existing entries. Always append.
Create the file with a header row if it does not exist:
```
| Date | Source | Request | Resolution | Status |
|------|--------|---------|------------|--------|
```

### 3. Check if it should become a JIRA ticket
If any of the following are true, suggest creating a {{JIRA_PROJECT_KEY}} JIRA ticket instead:
- Resolution took or is expected to take more than 2 hours
- The same request has appeared more than once in memory/quick-tasks.md
- It involves a decision that affects other parts of the project
- Client explicitly referenced it as part of scope

If none apply: log and move on.

### 4. Confirm
> "Logged to memory/quick-tasks.md. Status: [STATUS]."

## Notes
- This skill should feel lightweight. If it adds friction, it won't be used.
- The log is append-only. Entries are never edited or deleted by the agent.
- The PM reviews quick-tasks.md during sprint planning to decide
  if any items should be promoted to JIRA backlog tickets.
