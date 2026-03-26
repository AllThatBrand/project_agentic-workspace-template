# {{CLIENT_NAME}} · standing instructions

These rules apply for the duration of every agent session on this project.
Read silently during start-session. Do not summarise back unless asked.

## Communication
- Client language: {{LANGUAGE}}
- All client-facing copy must be reviewed by the client contact before publishing
- Use professional but friendly tone in all client communications

## Deployment rules
- Never deploy to production without explicit confirmation from the CEO or the PM
- Always test on both desktop and mobile before marking ready for QA
- Test on Chrome and Safari minimum

## JIRA
- JIRA project key: {{JIRA_PROJECT_KEY}}
- Always reference {{JIRA_PROJECT_KEY}}-[number] when discussing specific tickets
- Do not close a JIRA ticket unless DoD checklist is fully met

## Framer-specific
- Always target parent nodes when updating text components, not leaf nodes
- Verify changes in Framer preview before publishing
- Check mobile breakpoints after any layout change

## Commit conventions
- Never commit directly to main — always use a branch
- Automation commits: `chore: [description] [skip ci]`
- Session commits: `session: YYYY-MM-DD · [summary] [skip ci]`
- Digest routing: `chore: route digest YYYY-MM-DD [skip ci]`
- Wait for user confirmation before committing

## Never do
- Do not commit directly to main — always use a branch
- Do not deploy on Fridays (client preference)
- Do not share client information outside this repo or the private Google Drive folder

## Memory
- Use `memory/` as the sole memory location for all persistent context.
- Do NOT use the default Claude memory directory (~/.claude/projects/.../memory/).
- Memory index lives at `memory/MEMORY.md`.
- Write new memories as individual .md files inside `memory/` with frontmatter (name, description, type).
- Update `memory/MEMORY.md` as a one-line-per-entry index.
- Memory types: user, feedback, project, reference.
- Session notes go in `memory/sessions/YYYY-MM-DD.md`.
- Quick tasks go in `memory/quick-tasks.md`.

## When unsure
- Stop and ask the CEO or the PM before proceeding
- Document the uncertainty in the session note under "open threads"
