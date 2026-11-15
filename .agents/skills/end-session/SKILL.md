---
name: end-session
description: >
  Close a work session by moving what was learned into the .okf/ knowledge bundle through the OKF
  pipeline: screen, inbox note and commit A, draft, check, one human review, stamp, carry, index,
  commit B and push. Also runs "catch up" (knowledge from recent commits) and "review migration
  <folder>" (confirm migrated drafts). Use when the user says "end session", "wrap up", "we're done
  for today", "catch up", or "review migration <folder>". Never runs on its own.
okf_tooling: 0.1.1
---

# end-session

`okf-check` below means `python scripts/okf-check.py` (on Windows `py -3 scripts/okf-check.py`).
Write the full form when you run it. Every step is a script call or one model task; do not
improvise git commands beyond the ones named here.

## 0. Before anything

1. `okf-check paused end-session`. Exit 2 → print its line to the user and stop.
2. Pick the mode:
   - **end-session**: the user is closing the session.
   - **catch-up**: the user said "catch up" (usually because the debt report shows commits since
     the last close). Input is only `git log` of those commits (messages and `--stat`), at most 30.
   - **migration-review**: the user said "review migration <folder>". Skip to section M.
   - **fixture mode** (golden tests only): "end session from fixture <path>" uses only that file as
     the step-1 input.
3. `okf-check run list --open`. A `failed` or half-done run of this session → offer
   `okf-check run resume <slug>` instead of starting a new one. `waiting` runs (parked log-comms)
   are collected in step 3.

## 1. Screen

1. Propose a slug `YYYY-MM-DD-<two-to-four-words>` and run
   `okf-check run start --mode <end-session|catch-up> --slug <slug>`. Use the slug it prints.
2. Gather the step-1 input: what this session produced (changed files, ticket keys, decisions,
   what failed, open threads) — never the chat transcript itself — plus the text of every
   `inbox/quick-*.md` (log-mode-a notes).
3. `okf-check screen --pre --run <slug>`.
4. Apply the refusal table from `okf.config` `refuse:`: commercial terms, contract terms, contact
   details, personal matters, people who are not participants, long verbatim quotes, security
   incident details and credentials never enter git. For each item:
   `okf-check run refuse <slug> --category <c> --note "<what, without the detail>"`.
5. `okf-check run set <slug> --state screened`.

## 2. Inbox note and commit A

1. Write `inbox/<slug>.md`: a short screened note of the session (no frontmatter). Include the
   quick-note texts.
2. `okf-check screen --post --run <slug> inbox/<slug>.md`. Exit 2 → fix or refuse, then repeat.
3. `git add -- inbox/<slug>.md` and
   `git commit -m "inbox: <slug>" -m "Knowledge-Run: <slug>" -- inbox/<slug>.md`.
4. Delete the `inbox/quick-*.md` files you copied (they were never committed).
5. `okf-check run set <slug> --state inbox-committed --commit-a <hash>`.

## 3. Classify and draft

For each item in the note decide one of: a concept (Decision, Rule, Finding, Person, Client,
System, Runbook, Comms), a ticket link, a carried item (an internal follow-up with no ticket), or
"neither" (not lasting). Transient environment state (an expired login, disk space, a one-off
search miss) is "neither", never a tool fact. A name you leave out of a note because the person
is not a participant is still a refusal: record it with `run refuse --category third-party`.

- Before creating a file, `okf-check --closest "<title>" [--type T]` and edit the closest file if
  it is the same subject.
- New files are `status: draft` with `generated: {by: agent:<tool>/<model>, at: <now>}`.
- After each write: `okf-check run add-path <slug> <path>`. Exit 2 (another run owns it) → edit a
  different file or `okf-check run move-path <other> <path> --to <slug>`.
- Carried items and "neither" go into the run:
  `okf-check run set <slug> --carried '[{"event":"open","text":"…"},{"event":"close","id":"C-0003","text":"done in KCM-1710"}]'`
  and `okf-check run set <slug> --neither '[{"item":"…","reason":"…"}]'`.
- Waiting log-comms runs (`okf-check run list --waiting`): `okf-check run collect <slug> <waiting-slug>…`.
- `okf-check run set <slug> --state drafted`.

## 4. Check

`okf-check --run <slug>` and `okf-check screen --post --run <slug>`. Fix warnings you can fix; a
file that cannot be fixed is dropped at review. `okf-check run set <slug> --state checked`.

## 5. Review (the one human decision)

Show exactly this screen and wait:

```
Knowledge from inbox/<slug>.md                            run <slug>
 [1] rules/linear-usage.md                    edit  +4 -1   Rule (stamped on accept)
 [2] people/vendor-contact-a.md               new           Person   ⚑ 1 flag
Flags: [2] line 9 "name not a known Person or participant"
Dropped by check: none
Ticket links: KCM-1710
Carried: C-0007 "…" (new), C-0003 → close
Neither: "…" (not lasting)
Refused: commercial ×1 → <destination>
Accept all unflagged [a], list numbers to drop, or open flags [f]:
```

- Collected log-comms runs are shown as a separate group under their own heading
  (`From log-comms <slug>: <source>`) with their own accept-all/drop answer; record the answers as
  path lists in the same `run review` call.
- "Accept all" covers files without flags; each flagged file needs keep, edit or drop.
- Record it: `okf-check run review <slug> --accept <paths…> --drop <paths…> --keep-flag <n…>`.
  Dropping restores or deletes the file. After any drop, run step 4 again on what remains.
- Corrections ("change X") → edit, `run add-path`, back to step 4.

## 6-9. Stamp, carry, index, commit B

Run in order; each is idempotent and `okf-check run resume <slug>` continues from a failure:

1. `okf-check stamp --run <slug>` (needs `gh` logged in; a reviewed file that changed goes back
   to review).
2. `okf-check carried --run <slug>`.
3. `okf-check index --run <slug>`.
4. `okf-check run commit <slug>` — writes commit B `knowledge: <slug>` with its trailers, deletes
   the inbox note, and pushes to `branch`. A push failure leaves the run `failed` at step 9; tell
   the user and resume later.

Tell the user in one line what was kept, carried and refused.

## M. Migration review

1. `okf-check run start --mode migration-review --folder <folder> --slug YYYY-MM-DD-migration-<folder>`
   (folder `.` for `client.md`). It claims every migration draft there; the run starts at
   `drafted`.
2. Steps 4, 5 and 6-9 as above. Commit B carries `Knowledge-Mode: migration`; there is no inbox
   note or commit A.
