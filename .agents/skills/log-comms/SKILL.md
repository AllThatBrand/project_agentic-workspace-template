---
name: log-comms
description: >
  Log an inbound or outbound communication (email thread, meeting notes, call notes, pasted text)
  into the .okf/ bundle as a screened Comms record, plus any Decisions, Person updates, carried
  items or ticket links it yields. Raw sources never enter git. Use when the user says "log this
  email", "log this meeting", "log the call with …", or pastes a source and asks to record it.
okf_tooling: 0.1.0
---

# log-comms

`okf-check` below means `python scripts/okf-check.py` (on Windows `py -3 scripts/okf-check.py`).
Write the full form when you run it.

## 0. Before anything

1. `okf-check paused log-comms`. Exit 2 → print its line and stop.
2. Read `okf.config` `comms.adapters`. Only those adapters may be used.
3. Dedupe: look up the source reference (thread id, or the paste reference after step 1) in
   `.okf/comms/*` `atb.covers.source`, in `Knowledge-Source` trailers
   (`git log --format=%(trailers:key=Knowledge-Source,valueonly)`) and in `okf-check run list --open`.
   A match → tell the user "already logged in <where>" and stop, or log only messages newer than
   the latest `last_at`.

## 1. Fetch and screen

1. Propose a slug `YYYY-MM-DD-<words>` and run
   `okf-check run start --mode log-comms --slug <slug> --source <ref>`. It prints the scratch
   folder. Nothing from the source is written anywhere else.
2. Adapter:
   - **paste**: write the pasted text to `<scratch>/source.txt`. Also save it as
     `~/okf-pastes/<date>-<sha8>.txt` (sha8 = first 8 hex of sha256 of the text with whitespace
     runs collapsed); the reference is `paste:<date>-<sha8>`. Pastes are deleted after 30 days.
   - **composio-gmail**: find the ACTIVE Gmail connection (`composio connections list`), fetch
     its profile and pipe the JSON to `okf-check account-check --alias <alias>`. Exit 2 → stop and
     tell the user only the domain it printed. Then fetch the thread message by message into
     `<scratch>/messages/<n>.json` (thread search truncates). A message or attachment you could
     not read goes into `atb.not_read` and a "Not read" line in the Comms body. Reference:
     `gmail:<alias>/thread/<thread-id>`.
3. `okf-check screen --pre --run <slug>` (strips quoted and forwarded text, builds the denylist
   from Cc lines and signatures).
4. Apply the refusal table (`okf.config` `refuse:`) and record each refusal with
   `okf-check run refuse <slug> --category <c> --note "<what, without the detail>"`.
5. Participants: people already in `.okf/people/` or who spoke or wrote. People only on Cc are
   counted, never named. Record named participants:
   `okf-check run set <slug> --participants '["First Last", …]'`.
6. `okf-check run set <slug> --state screened`.

## 2. Pointer note and commit A

Write `inbox/<slug>.md` with only these lines (no summary enters git before review):

```
date: <YYYY-MM-DD>
channel: <email|meeting|call|chat>
direction: <in|out|both>
source: <ref>
run: <slug>
```

`git add -- inbox/<slug>.md`, `git commit -m "inbox: <slug>" -m "Knowledge-Run: <slug>" -- inbox/<slug>.md`,
then `okf-check run set <slug> --state inbox-committed --commit-a <hash>`.

## 3. Draft

- A Comms file `comms/YYYY-MM-DD-<words>.md` is created only if the source yields a Decision, a
  Person update, a carried item or a ticket link. Frontmatter: `type: Comms`, `status: draft`,
  `generated`, and `atb: {direction, channel, covers: {source, first_at, last_at, count},
  participants_counted, not_read}`.
- Quotes only for a request, commitment, decision or deadline, at most 25 words each.
- Promises are recorded only as carried IDs or ticket keys. Outbound mail is logged only after it
  is sent.
- Person changes from Comms may touch only `atb.role`, `atb.organisation`, `atb.projects`.
- `okf-check run add-path <slug> <path>` after each write; carried items and "neither" via
  `okf-check run set <slug> --carried '…' --neither '…'`; `--covers '{…}'` with the message range.
- Nothing to keep → no Comms file; commit B records "Nothing to keep from this source."

## 4. Park or close

- `okf-check run list --open` shows an open run other than `<slug>` → `okf-check run set <slug> --state drafted`,
  then `--state waiting`, tell the user it will be reviewed at the next end-session, and stop.
- Otherwise `okf-check run set <slug> --state drafted` and continue with steps 4-9 of
  `.agents/skills/end-session/SKILL.md` (check, review, stamp, carry, index, commit B).
