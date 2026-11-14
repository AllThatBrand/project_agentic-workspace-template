---
name: log-mode-a
description: >
  Capture a quick task done outside the tracker (an email request, a quick fix, a verbal ask) as a
  one-line screened inbox note that the next end-session turns into knowledge or a carried item.
  Use when the user says "log this", "log quick task", "log mode a", or "this was a quick fix, log
  it".
okf_tooling: 0.1.0
---

# log-mode-a

`okf-check` below means `python scripts/okf-check.py` (on Windows `py -3 scripts/okf-check.py`).

1. `okf-check paused log-mode-a`. Exit 2 → print its line and stop.
2. Infer, or ask for, one line: source (email, Slack, call, verbal), what was asked, what was done,
   and whether anything is still open. Confirm it with the user in one sentence.
3. Apply the refusal table from `okf.config` `refuse:` to that line: no prices, contact details,
   personal matters or credentials. Describe them without the detail.
4. Write `inbox/quick-YYYY-MM-DD-<slug>.md` containing only that line (no frontmatter).
5. `okf-check screen --post inbox/quick-YYYY-MM-DD-<slug>.md`. Exit 2 → show the hits, fix the
   line with the user, repeat.
6. Do not commit. Tell the user: "Logged; the next end-session will pick it up." The debt report
   lists quick notes until then.
