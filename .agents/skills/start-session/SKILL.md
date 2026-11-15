---
name: start-session
description: >
  Start a work session read-only: load AGENTS.md and the .okf/ index, show the knowledge debt
  report and any open pipeline runs, and offer to resume an unfinished close or catch up. Use when
  the user says "start session", "good morning", "what's the state", or opens a session and asks
  where things stand. Never pulls, commits or writes files.
okf_tooling: 0.1.1
---

# start-session

`okf-check` below means `python scripts/okf-check.py` (on Windows `py -3 scripts/okf-check.py`).

This skill is read-only. It runs no `git pull`, writes no file and starts no run. Pulling is an
explicit user action.

1. Read `AGENTS.md`, then `.okf/index.md` and the folder indexes relevant to the user's task.
2. `okf-check --report debt` and show its output as is.
3. `okf-check run list --open`.
4. Offer, in one line each, only what applies:
   - an open or `failed` run → "resume close <slug>" (then run `okf-check run resume <slug>`,
     which may stamp, commit and push — only after the user agrees);
   - signal 5 or 6 above zero → "catch up" (end-session in catch-up mode);
   - inbox notes or carried items over their age limit → name them.
5. Wait for the user's task.
