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
- Wait for user confirmation before committing
- Knowledge commits (`inbox:`, `knowledge:`) are written by end-session; do not write them by hand

## Never do
- Do not deploy on Fridays (client preference)
- Do not share client information outside this repo or the private Google Drive folder

## Knowledge
- Knowledge rules live in `AGENTS.md`. Commit format for knowledge is owned by end-session.

## When unsure
- Stop and ask the CEO or the PM before proceeding
- Document the uncertainty in an inbox note (log-mode-a) so the next end-session picks it up
