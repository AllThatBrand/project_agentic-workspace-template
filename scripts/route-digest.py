#!/usr/bin/env python3
"""
route-digest.py
Parses digest/YYYY-MM-DD.csv produced by n8n and routes each row
to the correct folder based on type.

Format (semicolon-delimited, no quoting required):
  type;project;title;content
  decision;PROJ;Hero section layout change;Client confirmed final hero layout...
  question;PROJ;What is project status;Client asked about the project status?
  mode-a;PROJ;Fix logo swap;Swap requested via email; updated and published.

Parsing rules:
  - Delimiter: ; (semicolon)
  - Split on first 3 semicolons only (maxsplit=3)
    → semicolons inside content are safe and never treated as delimiters
  - type, project, title are REQUIRED — row skipped with error if missing
  - content is OPTIONAL — defaults to empty string
  - No quoting of field values needed or expected

# FORMAT CONTRACT: see also n8n daily-digest workflow Node 6 prompt.
# If you change column order or delimiter, update the Claude prompt to match.

Usage: python scripts/route-digest.py digest/YYYY-MM-DD.csv
"""

import sys
import re
from pathlib import Path

ROOT        = Path(__file__).parent.parent
VALID_TYPES = {"decision", "client-comms", "mode-a", "question"}
REQUIRED    = {"type", "project", "title"}


# ── parser ────────────────────────────────────────────────────────────

def parse_csv(text: str) -> list[dict]:
    """
    Split each line on the first 3 semicolons only.
    Content (col 4) receives everything after the 3rd semicolon,
    including any semicolons it may contain.
    """
    rows  = []
    lines = text.strip().splitlines()

    if not lines:
        return []

    for i, line in enumerate(lines[1:], start=2):  # line 1 is header
        line = line.strip()
        if not line:
            continue

        parts = line.split(";", 3)  # maxsplit=3 — content gets remainder

        rows.append({
            "type":    parts[0].strip() if len(parts) > 0 else "",
            "project": parts[1].strip() if len(parts) > 1 else "",
            "title":   parts[2].strip() if len(parts) > 2 else "",
            "content": parts[3].strip() if len(parts) > 3 else "",
            "_line":   i,
        })

    return rows


# ── validation ────────────────────────────────────────────────────────

def validate(row: dict) -> bool:
    line    = row["_line"]
    missing = [f for f in REQUIRED if not row.get(f, "").strip()]
    if missing:
        raise ValueError(
            f"Line {line}: missing required field(s): {', '.join(missing)}\n"
            f"  Row: type={row['type']!r} project={row['project']!r} title={row['title']!r}"
        )
    t = row["type"].strip().lower()
    if t not in VALID_TYPES:
        raise ValueError(
            f"Line {line}: unknown type {t!r}. "
            f"Valid: {', '.join(sorted(VALID_TYPES))}"
        )
    return True


# ── routers ───────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def route_decision(row: dict, date: str):
    d = ROOT / "docs" / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{date}-{row['project'].lower()}-{_slug(row['title'])}.md"
    out.write_text(
        f"# {row['title']}\n\n"
        f"**Date:** {date}  \n"
        f"**Project:** {row['project']}  \n"
        f"**Source:** Daily digest  \n\n"
        f"{row.get('content', '')}\n"
    )
    print(f"  → docs/decisions/{out.name}")


def route_client_comms(row: dict, date: str):
    d = ROOT / "docs" / "client-comms"
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{date}-{row['project'].lower()}-{_slug(row['title'])}.md"
    out.write_text(
        f"# {row['title']}\n\n"
        f"**Date:** {date}  \n"
        f"**Project:** {row['project']}  \n\n"
        f"{row.get('content', '')}\n"
    )
    print(f"  → docs/client-comms/{out.name}")


def route_question(row: dict, date: str):
    """Client questions route to client-comms with [question] prefix."""
    row = dict(row)
    row["title"] = f"[question] {row['title']}"
    route_client_comms(row, date)


def route_mode_a(row: dict, date: str):
    qt = ROOT / "memory" / "quick-tasks.md"
    qt.parent.mkdir(parents=True, exist_ok=True)

    if not qt.exists():
        qt.write_text(
            "# Quick tasks log\n\n"
            "| Date | Project | Title | Content | Status |\n"
            "|------|---------|-------|---------|--------|\n"
        )

    content = row.get("content", "").replace("|", "/")  # escape table pipes
    with qt.open("a") as f:
        f.write(
            f"| {date} "
            f"| {row['project']} "
            f"| {row['title']} "
            f"| {content} "
            f"| open |\n"
        )
    print(f"  → memory/quick-tasks.md (appended)")


ROUTERS = {
    "decision":    route_decision,
    "client-comms": route_client_comms,
    "question":    route_question,
    "mode-a":      route_mode_a,
}


# ── main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: route-digest.py digest/YYYY-MM-DD.csv")
        sys.exit(1)

    digest_path = ROOT / sys.argv[1]
    if not digest_path.exists():
        print(f"ERROR: file not found: {digest_path}")
        sys.exit(1)

    date = digest_path.stem  # YYYY-MM-DD
    rows = parse_csv(digest_path.read_text())
    print(f"Routing {len(rows)} rows from {digest_path.name}")

    errors  = []
    routed  = 0
    skipped = 0

    for row in rows:
        try:
            validate(row)
            t = row["type"].strip().lower()
            ROUTERS[t](row, date)
            routed += 1
        except ValueError as e:
            errors.append(str(e))
            skipped += 1
            print(f"  ✗ skipped: {e}")

    print(f"\nDone: {routed} routed, {skipped} skipped.")

    if errors:
        print("\nValidation errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)  # non-zero exit → GitHub Actions marks step as failed
