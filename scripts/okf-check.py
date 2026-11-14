#!/usr/bin/env python3
# okf-tooling: 0.1.0
"""okf-check: rules, screening, run state and stamping for an ATB OKF v0.2 bundle.

Standard library only, Python 3.11+. Spec: okf-workspace/spec.md (atb-admin), sections 3-9.

Exit codes (spec 8.1):
  0  clean, warnings, or advisory failures (printed as "FAIL (advisory)")
  1  a blocking finding (C17, C17b), a usage error or an internal error
  2  a command-level refusal or mismatch: paused, account-check mismatch, screen hits,
     run conflicts, carried --seed regex hit. The rule check itself never exits 2.

Usage (`okf-check` = `python scripts/okf-check.py`):
  okf-check [--run S] [paths]                 rules C1-C24, C17b
  okf-check screen --pre --run S
  okf-check screen --post [--run S] [paths]
  okf-check --closest "<title>" [--type T]
  okf-check stamp --run S
  okf-check index [--run S]
  okf-check log
  okf-check run start|add-path|move-path|refuse|set|review|collect|commit|resume|abandon|list ...
  okf-check carried --run S | carried list --open | carried --seed FILE --run SLUG
  okf-check --report debt | --report spot-check [--week YYYY-Www]
  okf-check migrate <paths>
  okf-check paused <skill>
  okf-check account-check --alias <a>        (profile JSON on stdin)
"""
from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

TOOLING_VERSION = "0.1.0"
MIGRATION_ACTOR = f"process:atb-okf-migration/{TOOLING_VERSION}"
TYPES = ("Decision", "Rule", "Finding", "Person", "Client", "System", "Runbook", "Comms")
OLD_TYPES = ("user", "feedback", "project", "reference", "memory", "note")
FOLDER_TYPE = {"decisions": "Decision", "rules": "Rule", "findings": "Finding", "people": "Person",
               "systems": "System", "runbooks": "Runbook", "comms": "Comms"}
TYPE_FOLDER = {v: k for k, v in FOLDER_TYPE.items()}
DATED = r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md"
NAME_RE = {
    "Decision": re.compile(rf"^decisions/{DATED}$"),
    "Finding": re.compile(rf"^findings/{DATED}$"),
    "Comms": re.compile(rf"^comms/{DATED}$"),
    "Person": re.compile(r"^people/[a-z]+(-[a-z]+)+\.md$"),
    "Client": re.compile(r"^client\.md$"),
    "System": re.compile(r"^systems/[a-z0-9-]+\.md$"),
    "Runbook": re.compile(r"^runbooks/[a-z0-9-]+\.md$"),
}
# stale_after: None = not allowed, int = required with default days, 0 = required, no default
STALE = {"Decision": None, "Rule": None, "Runbook": None, "Comms": None,
         "Finding": 365, "Person": 365, "Client": 365, "System": 180}
COMMON_FIELDS = {"type", "title", "description", "status", "generated", "verified",
                 "stale_after", "sources", "tags", "atb"}
ATB_ALL = {"verified_via", "verified_hash", "scope"}
ATB_KEYS = {
    "Decision": {"superseded_by", "supersedes"}, "Rule": {"topic", "cites_decision"},
    "Finding": {"replaces"}, "Person": {"organisation", "role", "projects", "contact_location"},
    "Client": {"contract_location", "tracker"}, "System": {"owner", "environment"},
    "Runbook": set(),
    "Comms": {"direction", "channel", "covers", "participants_counted", "not_read"},
}
STATUSES = ("draft", "stable", "deprecated")
STATES = {
    "started": {"screened", "drafted", "abandoned"},
    "screened": {"inbox-committed", "abandoned"},
    "inbox-committed": {"drafted", "abandoned"},
    "drafted": {"checked", "waiting", "abandoned"},
    "waiting": {"drafted", "abandoned"},
    "checked": {"reviewed", "drafted", "abandoned"},
    "reviewed": {"stamped", "checked"},
    "stamped": {"carried"},
    "carried": {"indexed"},
    "indexed": {"committed"},
    "committed": {"done"},
}
OPEN_STATES = set(STATES) - {"done"}
MODES = ("end-session", "catch-up", "log-comms", "migration-review")
SLUG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")
# Ported from terabeauty scripts/validate-workspace.py (FORBIDDEN_AUTO, no_forbidden_in_hook).
FORBIDDEN_AUTO = ("git pull", "git pull --rebase", "git add", "git commit", "git push",
                  "write_text", "cat >", "tee ")
HOOK_CALL = re.compile(r"^\s*(?:if\s+|then\s+|elif\s+|&&\s*|\|\|\s*)*(py -3|python3|python) "
                       r"scripts/okf-check\.py --report debt\b")
HOOK_PROBE = re.compile(r"^\s*(?:if\s+|elif\s+)?(py -3|python3|python) -c "
                        r"'import sys; sys\.exit\(sys\.version_info < \(3, 11\)\)'")


class Fail(Exception):
    """Usage or internal error: exit 1."""


class Refuse(Exception):
    """Command-level refusal or mismatch: exit 2."""


# ----------------------------------------------------------------------------- utilities

def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().replace(microsecond=0).isoformat()


def parse_time(value: str) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t


def git(*args: str, check: bool = True, cwd: Path | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd or ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise Fail(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).returncode == 0


def find_root() -> Path:
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(r.stdout.strip()) if r.returncode == 0 else Path.cwd()


ROOT = find_root()


def rel(p: Path | str) -> str:
    p = Path(p)
    if not p.is_absolute():
        p = (Path.cwd() / p)
    try:
        return p.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def read_text(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="replace")
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    return unicodedata.normalize("NFC", raw.replace("\r\n", "\n").replace("\r", "\n"))


def blob_of(path: str) -> str | None:
    p = ROOT / path
    if not p.exists():
        return None
    return git("hash-object", "--", path).strip()


def at_ref(ref: str | None, path: str) -> str | None:
    if not ref:
        return None
    r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True)
    if r.returncode != 0:
        return None
    t = r.stdout.decode("utf-8", errors="replace").lstrip("\ufeff")
    return t.replace("\r\n", "\n").replace("\r", "\n")


def common_dir() -> Path:
    d = Path(git("rev-parse", "--git-common-dir").strip())
    return (d if d.is_absolute() else ROOT / d) / "okf"


# ----------------------------------------------------------------------------- frontmatter

class ParseError(Exception):
    def __init__(self, line: int, msg: str):
        super().__init__(f"line {line}: {msg}")
        self.line = line


KEY_RE = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s(.*)|)$")


def _scalar(text: str, line: int) -> str:
    t = text.strip()
    if not t:
        return ""
    if t[0] == '"':
        if len(t) < 2 or t[-1] != '"':
            raise ParseError(line, "unterminated double-quoted scalar")
        out, i, body = [], 0, t[1:-1]
        while i < len(body):
            c = body[i]
            if c == "\\":
                if i + 1 < len(body) and body[i + 1] in '"\\':
                    out.append(body[i + 1]); i += 2; continue
                raise ParseError(line, "only \\\" and \\\\ escapes are allowed")
            if c == '"':
                raise ParseError(line, "unescaped quote")
            out.append(c); i += 1
        return "".join(out)
    if t[0] == "'":
        if len(t) < 2 or t[-1] != "'":
            raise ParseError(line, "unterminated single-quoted scalar")
        return t[1:-1].replace("''", "'")
    if t[0] in "&*!|>%@`":
        raise ParseError(line, f"'{t[0]}' (anchors, tags, multi-line strings) not allowed")
    if " #" in t:
        raise ParseError(line, "comments are not allowed")
    return t


def _value_start(cur: list[str]) -> bool:
    """A quote opens a scalar only at the start of a value (after ',', ':', '[' or '{')."""
    t = "".join(cur).rstrip()
    return not t or t[-1] in ",:[{"


def _split_flow(inner: str, line: int) -> list[str]:
    parts, depth, cur, quote = [], 0, [], None
    for c in inner:
        if quote:
            cur.append(c)
            if c == quote:
                quote = None
            continue
        if c in "\"'" and _value_start(cur):
            quote = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur)); cur = []
            continue
        cur.append(c)
    if quote or depth:
        raise ParseError(line, "unbalanced flow collection")
    if "".join(cur).strip():
        parts.append("".join(cur))
    return [p.strip() for p in parts]


def _flow(text: str, line: int, depth: int = 0):
    t = text.strip()
    if depth > 2:
        raise ParseError(line, "flow collections nested too deep")
    if t.startswith("{"):
        if not t.endswith("}"):
            raise ParseError(line, "unterminated flow map")
        out = {}
        for part in _split_flow(t[1:-1], line):
            k, sep, v = part.partition(":")
            if not sep:
                raise ParseError(line, f"flow map item without ':' ({part})")
            out[k.strip()] = _flow(v, line, depth + 1)
        return out
    if t.startswith("["):
        if not t.endswith("]"):
            raise ParseError(line, "unterminated flow list")
        return [_flow(p, line, depth + 1) for p in _split_flow(t[1:-1], line)]
    return _scalar(t, line)


def parse_yaml(text: str, first_line: int = 1):
    """Parse the ATB YAML subset (spec 3.3). Returns dict; raises ParseError."""
    lines = []
    for n, raw in enumerate(text.split("\n"), start=first_line):
        if not raw.strip():
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ParseError(n, "tab indentation")
        if raw.lstrip().startswith("#"):
            raise ParseError(n, "comments are not allowed")
        if raw.strip() in ("---", "...") :
            raise ParseError(n, "multi-document markers are not allowed")
        lines.append((n, len(raw) - len(raw.lstrip(" ")), raw.strip()))
    value, i = _block(lines, 0, 0, 1)
    if i != len(lines):
        raise ParseError(lines[i][0], "unexpected indentation")
    return value if isinstance(value, dict) else {}


def _block(lines, i, indent, depth):
    if i >= len(lines):
        return {}, i
    if depth > 3:
        raise ParseError(lines[i][0], "block maps nested deeper than 3")
    if lines[i][2].startswith("- ") or lines[i][2] == "-":
        out = []
        while i < len(lines) and lines[i][1] == indent and (lines[i][2].startswith("- ") or lines[i][2] == "-"):
            n, _, content = lines[i]
            item = content[2:].strip()
            if item.startswith("{"):
                out.append(_flow(item, n))
            elif KEY_RE.match(item) and not item.startswith(("http:", "https:")):
                raise ParseError(n, "block maps inside lists are not allowed; use a flow map")
            else:
                out.append(_scalar(item, n))
            i += 1
        return out, i
    out = {}
    while i < len(lines) and lines[i][1] == indent:
        n, _, content = lines[i]
        m = KEY_RE.match(content)
        if not m:
            raise ParseError(n, f"expected 'key: value', got '{content[:40]}'")
        key, val = m.group(1), (m.group(2) or "").strip()
        if key in out:
            raise ParseError(n, f"duplicate key '{key}'")
        i += 1
        if val:
            out[key] = _flow(val, n) if val[0] in "[{" else _scalar(val, n)
        elif i < len(lines) and (lines[i][1] > indent or (lines[i][1] == indent and lines[i][2].startswith("-"))):
            sub, i = _block(lines, i, lines[i][1], depth + 1)
            out[key] = sub
        else:
            out[key] = ""
    if i < len(lines) and lines[i][1] > indent:
        raise ParseError(lines[i][0], "unexpected indentation")
    return out, i


def split_doc(text: str) -> tuple[list[str] | None, str, int]:
    """Return (frontmatter lines, body, body start line). None when no frontmatter."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text, 1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "\n".join(lines[i + 1:]), i + 2
    return None, text, 1


class Doc:
    def __init__(self, path: str, text: str):
        self.path, self.text = path, text
        self.fm_lines, self.body, self.body_line = split_doc(text)
        self.meta: dict = {}
        self.error: str | None = None
        if self.fm_lines is None:
            self.error = "no frontmatter block"
        else:
            try:
                self.meta = parse_yaml("\n".join(self.fm_lines), 2)
            except ParseError as e:
                self.error = str(e)

    @classmethod
    def load(cls, path: str) -> "Doc":
        return cls(path, read_text(ROOT / path))

    @property
    def atb(self) -> dict:
        a = self.meta.get("atb")
        return a if isinstance(a, dict) else {}

    def render(self) -> str:
        return "---\n" + "\n".join(self.fm_lines or []) + "\n---\n" + self.body

    def save(self) -> None:
        (ROOT / self.path).write_text(self.render(), encoding="utf-8", newline="\n")

    # --- in-place writers (spec 3.3: only owned keys, other lines byte-identical)
    def _top(self, key: str) -> int | None:
        for i, l in enumerate(self.fm_lines or []):
            if re.match(rf"^{re.escape(key)}:(\s|$)", l):
                return i
        return None

    def _block_end(self, i: int) -> int:
        j = i + 1
        while j < len(self.fm_lines) and (self.fm_lines[j].startswith((" ", "-")) or not self.fm_lines[j].strip()):
            j += 1
        return j

    def set_top(self, key: str, value: str) -> None:
        i = self._top(key)
        line = f"{key}: {value}"
        if i is None:
            self.fm_lines.append(line)
        else:
            end = self._block_end(i)
            self.fm_lines[i:end] = [line]
        self.meta[key] = value

    def set_atb(self, key: str, value: str) -> None:
        i = self._top("atb")
        if i is None:
            self.fm_lines += ["atb:", f"  {key}: {value}"]
        else:
            end = self._block_end(i)
            for j in range(i + 1, end):
                if re.match(rf"^\s+{re.escape(key)}:(\s|$)", self.fm_lines[j]):
                    self.fm_lines[j] = f"  {key}: {value}"
                    break
            else:
                self.fm_lines.insert(end, f"  {key}: {value}")
        self.meta.setdefault("atb", {}) if isinstance(self.meta.get("atb"), dict) else self.meta.update(atb={})
        self.meta["atb"][key] = value

    def append_verified(self, by: str, at: str) -> None:
        entry = f"  - {{by: {q(by)}, at: {q(at)}}}"
        i = self._top("verified")
        if i is None:
            self.fm_lines += ["verified:", entry]
        elif self.fm_lines[i].strip() in ("verified:", "verified: []"):
            end = self._block_end(i)
            self.fm_lines[i] = "verified:"
            self.fm_lines.insert(end, entry)
        else:
            raise Fail(f"{self.path}: 'verified' must be a block list to append to")
        v = self.meta.get("verified")
        self.meta["verified"] = (v if isinstance(v, list) else []) + [{"by": by, "at": at}]


def q(value: str) -> str:
    """Quote a scalar only when the subset grammar needs it."""
    s = str(value)
    risky = (s == "" or s != s.strip() or s[0] in "-?:,[]{}#&*!|>'\"%@`"
             or ": " in s or " #" in s or any(c in s for c in ",[]{}") or s.endswith(":"))
    if not risky:
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def emit(value, indent: int = 0) -> list[str]:
    """Serialise a dict for new files (migrate, run-created concepts)."""
    pad = " " * indent
    out = []
    for k, v in value.items():
        if isinstance(v, dict):
            if indent >= 2 or all(not isinstance(x, (dict, list)) for x in v.values()) and k in ("generated", "covers", "tracker"):
                out.append(f"{pad}{k}: {flow(v)}")
            else:
                out.append(f"{pad}{k}:")
                out += emit(v, indent + 2)
        elif isinstance(v, list):
            if v and all(isinstance(x, dict) for x in v):
                out.append(f"{pad}{k}:")
                out += [f"{pad}  - {flow(x)}" for x in v]
            else:
                out.append(f"{pad}{k}: {flow(v)}")
        else:
            out.append(f"{pad}{k}: {q(v)}")
    return out


def flow(v) -> str:
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {flow(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(flow(x) for x in v) + "]"
    return q(v)


# ----------------------------------------------------------------------------- config

def load_config(required: bool = True) -> dict | None:
    p = ROOT / "okf.config"
    if not p.exists():
        if required:
            raise Fail("no okf.config in the repo root")
        return None
    try:
        return parse_yaml(read_text(p))
    except ParseError as e:
        raise Fail(f"okf.config: {e}")


def cfg_list(cfg: dict, key: str) -> list:
    v = cfg.get(key)
    return v if isinstance(v, list) else []


def paused_entry(cfg: dict, skill: str) -> dict | None:
    skill = "end-session" if skill in ("catch-up", "migration-review") else skill
    for e in cfg_list(cfg, "paused"):
        if isinstance(e, dict) and e.get("skill") == skill:
            return e
        if e == skill:
            return {"skill": skill, "reason": "no reason given", "since": "?"}
    return None


def check_paused(cfg: dict, skill: str) -> None:
    e = paused_entry(cfg, skill)
    if e:
        raise Refuse(f"paused: {e.get('skill')} since {e.get('since', '?')}: {e.get('reason', '')}")


# ----------------------------------------------------------------------------- regex pack (6.3)

def near(line: str, s: int, e: int, pat: str) -> bool:
    return re.search(pat, line[max(0, s - 40): e + 40], re.IGNORECASE) is not None


CURRENCY = r"[$€£]|\b(?:CHF|USD|EUR|dollars?|francs?|euros?)\b"
PATTERNS = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), None),
    ("money", re.compile(r"(?:[$€£]|\bCHF|\bUSD|\bEUR)\s?\d[\d,.']*\s?[kKmM]?\b"), None),
    ("money", re.compile(r"\b\d[\d,.']*\s?(?:k|m|thousand|million|dollars|francs|euros)\b", re.I), CURRENCY),
    ("hours", re.compile(r"\b\d+(?:\.\d+)?\s?(?:h|hrs?|hours)\b"), r"retainer|burn|budget|billable|allocation"),
    ("aws-arn", re.compile(r"arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:\d{12}:"), None),
    ("aws-account", re.compile(r"(?<!\d)\d{12}(?!\d)"), r"aws|account"),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), None),
    ("aws-secret", re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"), r"secret"),
    ("token", re.compile(r"\b(?:ghp|gho|ghs|github_pat|xox[abprs]|sk-[A-Za-z0-9-]*)_?[A-Za-z0-9_-]{16,}"), None),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), None),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), None),
    ("connection-string", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/]+:[^\s@/]+@"), None),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}\b"), None),
]
PHONE_CAND = re.compile(r"(?<![\w+])\+?\(?\d[\d .()]{7,}\d(?!\w)")


def phone_hits(line: str):
    for m in PHONE_CAND.finditer(line):
        c = m.group(0)
        digits = re.sub(r"\D", "", c)
        if len(digits) < 9:
            continue
        if not c.startswith("+") and not re.search(r"\d[ .()]+\d", c):
            continue
        if re.search(r"\d{4}-\d{2}-\d{2}|\b\d{1,2}\.\d{1,2}\.\d{2,4}\b", c):
            continue
        yield m.start(), m.end(), c


def scan_line(line: str):
    """Yield (kind, start, text) for each regex-pack hit in one line."""
    seen = set()
    for kind, rx, ctx in PATTERNS:
        for m in rx.finditer(line):
            if ctx and not near(line, m.start(), m.end(), ctx):
                continue
            if (m.start(), kind) in seen:
                continue
            seen.add((m.start(), kind))
            yield kind, m.start(), m.group(0)
    for s, _, c in phone_hits(line):
        yield "phone", s, c


def scannable(text: str) -> list[tuple[int, str]]:
    """Body lines, plus frontmatter title and description (spec 6.3)."""
    fm, body, start = split_doc(text)
    out = []
    if fm is not None:
        for i, l in enumerate(fm, start=2):
            if re.match(r"^(title|description):", l):
                out.append((i, l))
    else:
        start = 1
    out += list(enumerate(body.split("\n"), start=start))
    return out


def sha8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


def load_allow() -> set[str]:
    p = ROOT / ".okf" / ".screen-allow"
    if not p.exists():
        return set()
    return {l.strip() for l in read_text(p).split("\n") if l.strip()}


def scan_file(path: str, denylist: list[str] = (), allow: set[str] = frozenset()):
    hits = []
    text = read_text(ROOT / path)
    for n, line in scannable(text):
        found = list(scan_line(line))
        for d in denylist:
            if d and d.lower() in line.lower():
                found.append(("denylist", line.lower().index(d.lower()), d))
        for kind, _, _ in found:
            key = f"{path}:{sha8(line)}:{kind}"
            if key in allow:
                continue
            hits.append({"path": path, "line": n, "kind": kind, "sha8": sha8(line)})
    return hits


# ----------------------------------------------------------------------------- run files & lock

class Lock:
    def __init__(self):
        self.path = common_dir() / ".lock"

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(50):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode()); os.close(fd)
                return self
            except FileExistsError:
                age = time.time() - self.path.stat().st_mtime
                if age > 600:
                    raise Fail(f"lock {self.path} is {int(age // 60)} minutes old; "
                               "check no okf-check is running, then delete it")
                time.sleep(0.1)
        raise Fail(f"lock {self.path} is held by another okf-check")

    def __exit__(self, *a):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def run_path(slug: str) -> Path:
    return common_dir() / f"run-{slug}.json"


def load_run(slug: str) -> dict:
    p = run_path(slug)
    if not p.exists():
        raise Fail(f"no run '{slug}'")
    r = json.loads(p.read_text(encoding="utf-8"))
    if r.get("schema") != 1:
        raise Fail(f"run '{slug}': unknown schema {r.get('schema')}")
    return r


def save_run(r: dict) -> None:
    p = run_path(r["slug"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def all_runs() -> list[dict]:
    d = common_dir()
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("run-*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def open_runs() -> list[dict]:
    return [r for r in all_runs() if r.get("state") in OPEN_STATES or r.get("state") == "failed"]


def transition(r: dict, new: str) -> None:
    cur = r["state"]
    if new == "failed" or new in STATES.get(cur, set()):
        r["state"] = new
        return
    if cur == "failed" and new == r.get("failed", {}).get("resume_state"):
        r["state"] = new
        return
    raise Refuse(f"run {r['slug']}: transition {cur} → {new} not allowed")


def fail_run(r: dict, step: int, msg: str, resume_state: str) -> None:
    r["failed"] = {"step": step, "message": msg, "resume_state": resume_state}
    r["state"] = "failed"
    save_run(r)
    raise Fail(f"step {step} failed: {msg}")


# ----------------------------------------------------------------------------- bundle helpers

def concept_paths() -> list[str]:
    base = ROOT / ".okf"
    if not base.exists():
        return []
    return sorted(rel(p) for p in base.rglob("*.md") if p.name not in ("index.md", "log.md"))


def bundle_rel(path: str) -> str:
    return path[len(".okf/"):] if path.startswith(".okf/") else path


def base_ref(cfg: dict | None) -> str | None:
    if os.environ.get("CI") and cfg:
        r = subprocess.run(["git", "merge-base", "HEAD", f"origin/{cfg.get('branch', 'main')}"],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
    return "HEAD" if git_ok("rev-parse", "--verify", "-q", "HEAD") else None


def canonical(meta: dict) -> str:
    lines = []
    for k in sorted(meta):
        if k in ("status", "verified"):
            continue
        v = meta[k]
        if k == "atb" and isinstance(v, dict):
            v = {a: b for a, b in v.items() if a not in ("verified_via", "verified_hash")}
        lines.append(f"{k}: {json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'))}")
    return "\n".join(lines)


def concept_hash(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n"))
    d = Doc("", text)
    body = "\n".join(re.sub(r"[ \t]+$", "", l) for l in d.body.split("\n")).strip("\n")
    payload = canonical(d.meta) + "\n---\n" + body + "\n"
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------- rules (8.2)

class Findings:
    def __init__(self):
        self.items: list[tuple[str, str, str, str]] = []  # severity, rule, where, message

    def add(self, sev: str, rule: str, where: str, msg: str) -> None:
        self.items.append((sev, rule, where, msg))

    def print(self) -> int:
        for sev, rule, where, msg in self.items:
            label = {"warn": "warn", "advisory": "FAIL (advisory)", "blocking": "FAIL"}[sev]
            print(f"{label} {rule} {where}: {msg}")
        b = sum(1 for s, *_ in self.items if s == "blocking")
        a = sum(1 for s, *_ in self.items if s == "advisory")
        w = sum(1 for s, *_ in self.items if s == "warn")
        print(f"okf-check {TOOLING_VERSION}: {b} blocking, {a} advisory, {w} warnings")
        return 1 if b else 0


LINK_RE = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
PLACEHOLDER = re.compile(r"<(?!https?:|mailto:|!--|/)[^<>\n]{1,60}>")
QUOTE_SPAN = re.compile(r"[\"“]([^\"”\n]+)[\"”]")


def check_concept(path: str, doc: Doc, cfg: dict, base: str | None, f: Findings, run: dict | None):
    br = bundle_rel(path)
    if doc.error:
        f.add("warn", "C2", path, f"{doc.error}; fix the frontmatter to the subset in spec 3.3")
        return
    m = doc.meta
    t = m.get("type")
    if t not in TYPES:
        hint = " (old memory type)" if str(t).lower() in OLD_TYPES else ""
        f.add("warn", "C1", path, f"type '{t}'{hint} is not one of {', '.join(TYPES)}")
        return
    extra = set(m) - COMMON_FIELDS
    if extra:
        f.add("warn", "C2", path, f"fields not adopted: {', '.join(sorted(extra))}; move them under atb: or drop them")
    for need in ("title", "status", "generated"):
        if need not in m:
            f.add("warn", "C2", path, f"missing '{need}'")
    if m.get("status") not in STATUSES:
        f.add("warn", "C2", path, f"status '{m.get('status')}' not one of {STATUSES}")
    bad_atb = set(doc.atb) - ATB_ALL - ATB_KEYS[t]
    if bad_atb:
        f.add("warn", "C3", path, f"atb keys not allowed for {t}: {', '.join(sorted(bad_atb))}")
    for target in LINK_RE.findall(doc.body):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        if target.startswith("/"):
            f.add("warn", "C4", path, f"link '{target}' starts with '/'; use a file-relative link")
            continue
        if not (ROOT / path).parent.joinpath(target.split("#")[0]).exists():
            f.add("warn", "C4", path, f"link '{target}' does not resolve")
    if t == "Rule":
        topics = cfg_list(cfg, "topics")
        mt = re.match(r"^rules/([a-z0-9-]+)\.md$", br)
        if not mt or mt.group(1) not in topics:
            f.add("warn", "C5", path, f"Rule file name must be rules/<topic>.md with a topic from okf.config ({', '.join(topics)})")
    elif not NAME_RE[t].match(br):
        f.add("warn", "C5", path, f"file name does not match the {t} pattern {NAME_RE[t].pattern}")
    old = Doc(path, at_ref(base, path)) if at_ref(base, path) is not None else None
    old_status = old.meta.get("status") if old and not old.error else None
    new_status = m.get("status")
    ok = {(None, "draft"), ("draft", "draft"), ("draft", "stable"), ("stable", "stable"),
          ("stable", "deprecated"), ("deprecated", "deprecated")}
    if (old_status, new_status) not in ok:
        if not ((old_status == "draft" and new_status == "deprecated") and doc.atb.get("superseded_by")):
            f.add("advisory", "C6", path, f"status {old_status or '(new)'} → {new_status} is not allowed (spec 3.4)")
    if old_status == "deprecated" and old and old.text != doc.text:
        f.add("advisory", "C6", path, "a deprecated file must not change; write a new concept")
    if t in ("Decision", "Rule") and new_status == "stable":
        ver = m.get("verified") if isinstance(m.get("verified"), list) else []
        if not any(isinstance(v, dict) and str(v.get("by", "")).startswith("human:") for v in ver):
            f.add("warn", "C7", path, "stable Decision/Rule has no human: entry in verified")
        h = doc.atb.get("verified_hash")
        if h and h != concept_hash(doc.text):
            f.add("warn", "C8", path, "content changed since it was verified (hash mismatch); review it in a close")
    if t == "Comms":
        for k in ("direction", "channel", "covers"):
            if k not in doc.atb:
                f.add("warn", "C14", path, f"Comms needs atb.{k}")
        for n, line in enumerate(doc.body.split("\n"), start=doc.body_line):
            spans = [s for s in QUOTE_SPAN.findall(line)] + ([line[1:]] if line.startswith(">") else [])
            for s in spans:
                if len(s.split()) > 25:
                    f.add("warn", "C23", f"{path}:{n}", f"quote of {len(s.split())} words; at most 25")
    if t == "Decision" and new_status == "deprecated":
        sb = doc.atb.get("superseded_by")
        if not sb or not (ROOT / path).parent.joinpath(sb).exists():
            f.add("warn", "C15", path, "deprecated Decision needs an existing atb.superseded_by")
    if t in ("Decision", "Finding", "Comms") and old_status == "stable" and old:
        def norm(d):
            return "\n".join(l.rstrip() for l in d.body.strip("\n").split("\n"))
        if norm(old) != norm(doc):
            f.add("warn", "C20", path, f"{t} body changed after stable; write a new concept instead")
    if t == "Person" and run and run.get("mode") == "log-comms" and old and not old.error:
        allowed = {"role", "organisation", "projects"}
        om, nm = dict(old.meta), dict(m)
        oa, na = dict(om.pop("atb", {}) or {}), dict(nm.pop("atb", {}) or {})
        for k in allowed:
            oa.pop(k, None); na.pop(k, None)
        if om != nm or oa != na or norm_body(old) != norm_body(doc):
            f.add("warn", "C21", path, "log-comms may change only atb.role, atb.organisation, atb.projects")
    st = STALE[t]
    if st is None and "stale_after" in m:
        f.add("warn", "C22", path, f"{t} must not have stale_after")
    if st is not None and "stale_after" not in m:
        f.add("warn", "C22", path, f"{t} needs stale_after")
    if t == "Client":
        for n, line in enumerate(doc.text.split("\n"), start=1):
            for ph in PLACEHOLDER.findall(line):
                f.add("warn", "C24", f"{path}:{n}", f"placeholder {ph} not filled")


def norm_body(d: Doc) -> str:
    return "\n".join(l.rstrip() for l in d.body.strip("\n").split("\n"))


def check_hook(f: Findings) -> None:
    settings = ROOT / ".claude" / "settings.json"
    if not settings.exists():
        return
    try:
        data = json.loads(read_text(settings))
    except json.JSONDecodeError as e:
        f.add("blocking", "C17", ".claude/settings.json", f"not valid JSON: {e}")
        return
    entries = (data.get("hooks") or {}).get("SessionStart") or []
    for entry in entries:
        for h in entry.get("hooks", []) if isinstance(entry, dict) else []:
            if h.get("type") != "command":
                continue
            if "timeout" not in h:
                f.add("blocking", "C17", ".claude/settings.json", "SessionStart hook has no timeout")
            cmd = h.get("command", "")
            script = re.search(r"([\w./-]+\.sh)\b", cmd)
            texts = [("settings.json command", cmd)]
            if script and (ROOT / script.group(1).lstrip("./")).exists():
                p = script.group(1).lstrip("./")
                texts.append((p, read_text(ROOT / p)))
            for where, text in texts:
                for n, line in enumerate(text.split("\n"), start=1):
                    s = line.strip()
                    if not s or s.startswith("#") or s.startswith("printf"):
                        continue
                    if "okf-check" in s:
                        if not (HOOK_CALL.match(s) or HOOK_PROBE.match(s)):
                            f.add("blocking", "C17", f"{where}:{n}", "only `(py -3|python3|python) scripts/okf-check.py --report debt` is allowed")
                        continue
                    if re.search(r"-c 'import sys; sys\.exit", s):
                        if not HOOK_PROBE.match(s):
                            f.add("blocking", "C17", f"{where}:{n}", "version probe does not match the allowed form")
                        continue
                    for tok in FORBIDDEN_AUTO:
                        if re.search(rf"(^|[;&|]\s*){re.escape(tok)}\b", s.lower()):
                            f.add("blocking", "C17", f"{where}:{n}", f"mutating command '{tok.strip()}' in the SessionStart hook")


def check_symlinks(f: Findings) -> None:
    for l in git("ls-files", "--stage").split("\n"):
        if l.startswith("120000"):
            f.add("blocking", "C17b", l.split("\t", 1)[1], "committed symlink; replace it with a plain file")
    for name in ("CLAUDE.md", "GEMINI.md"):
        p = ROOT / name
        if p.is_symlink():
            f.add("blocking", "C17b", name, "must be a plain file, not a symlink")
    if (ROOT / ".cursorrules").exists():
        f.add("blocking", "C17b", ".cursorrules", "remove it; use .cursor/rules/*.mdc")
    rules = ROOT / ".cursor" / "rules"
    entries = [ROOT / "CLAUDE.md", ROOT / "GEMINI.md"]
    if rules.exists():
        for p in sorted(rules.iterdir()):
            if p.suffix == ".md":
                f.add("blocking", "C17b", rel(p), "use .mdc files under .cursor/rules/")
            if p.suffix == ".mdc":
                entries.append(p)
                fm, _, _ = split_doc(read_text(p))
                fm_text = "\n".join(fm or [])
                if not re.search(r"^alwaysApply:\s*true\s*$", fm_text, re.M):
                    f.add("blocking", "C17b", rel(p), "needs alwaysApply: true")
                if not re.search(r"^description:\s*\S", fm_text, re.M):
                    f.add("blocking", "C17b", rel(p), "needs a description:")
    for p in entries:
        if not p.exists() or p.is_symlink():
            continue
        imports = re.findall(r"(?m)^\s*@(\S+)", read_text(p))
        if not imports or any(i not in ("AGENTS.md", "./AGENTS.md") for i in imports):
            f.add("blocking", "C17b", rel(p), "must import @AGENTS.md (or @./AGENTS.md) and nothing else")


def carried_rows(text: str) -> list[list[str]]:
    rows = []
    for l in text.split("\n"):
        if l.startswith("|") and not re.match(r"^\|[\s:-]+\|", l):
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            if cells and cells[0] != "id":
                rows.append(cells)
    return rows


def cmd_check(args: list[str]) -> int:
    cfg = load_config(required=False)
    if cfg is None:
        print("no okf.config: skipped")
        return 0
    f = Findings()
    run = None
    if args[:1] == ["--run"]:
        run = load_run(args[1]); args = args[2:]
    base = base_ref(cfg)
    if run:
        paths = [p for p in run["paths"] if (ROOT / p).exists()]
    elif args:
        paths = [rel(a) for a in args]
    else:
        paths = concept_paths()
        if (ROOT / "inbox").exists():
            paths += sorted(rel(p) for p in (ROOT / "inbox").glob("*.md"))
    allow = load_allow()
    for p in paths:
        if p.startswith(".okf/") and p.endswith(".md") and Path(p).name not in ("index.md", "log.md"):
            check_concept(p, Doc.load(p), cfg, base, f, run)
        if p.startswith((".okf/", "inbox/")) and p.endswith(".md") and (ROOT / p).exists():
            for h in scan_file(p, allow=allow):
                f.add("advisory", "C9", f"{p}:{h['line']}", f"{h['kind']} pattern; refuse it or keep the flag in a close")
    whole = not run and not args
    if whole:
        # C9 on knowledge commit messages since base
        if base and base != "HEAD":
            for c in git("log", "--format=%H%x00%B%x01", f"{base}..HEAD").split("\x01"):
                if "\x00" not in c:
                    continue
                h, msg = c.strip().split("\x00", 1)
                if not msg.startswith(("knowledge:", "inbox:")):
                    continue
                for line in msg.split("\n"):
                    if re.match(r"^[A-Za-z-]+: ", line):
                        continue
                    for kind, _, _ in scan_line(line):
                        f.add("advisory", "C9", f"commit {h[:7]}", f"{kind} pattern in the commit message")
        frozen = [x.rstrip("/") + "/" for x in cfg_list(cfg, "frozen")]
        reports = [x.rstrip("/") + "/" for x in cfg_list(cfg, "reports")]
        status = git("status", "--porcelain", "--untracked-files=all")
        added = [l[3:] for l in status.split("\n") if l[:2] in ("??", "A ", "AM")]
        if base and base != "HEAD":
            added += git("diff", "--name-only", "--diff-filter=A", base, "HEAD").split()
        for p in added:
            if any(p.startswith(fz) for fz in frozen) and not any(p.startswith(r) for r in reports):
                f.add("warn", "C10", p, "new file in a frozen folder")
        deleted = [l[3:] for l in status.split("\n") if l[:2] in (" D", "D ", "AD")]
        if base and base != "HEAD":
            deleted += git("diff", "--name-only", "--diff-filter=D", base, "HEAD").split()
        for p in deleted:
            if p.startswith("inbox/") and not git("log", "--format=%h", "--diff-filter=A", "--", p).strip():
                f.add("warn", "C11", p, "inbox deletion without an earlier commit that added it")
        cpath = "inbox/carried.md"
        if (ROOT / cpath).exists():
            new_rows = carried_rows(read_text(ROOT / cpath))
            old_text = at_ref(base, cpath)
            if old_text is not None:
                old_rows = carried_rows(old_text)
                if new_rows[: len(old_rows)] != old_rows:
                    f.add("advisory", "C12", cpath, "rows were removed or reordered; only append events")
            ids = [r[0] for r in new_rows if len(r) > 2 and r[2] == "open"]
            if len(ids) != len(set(ids)):
                f.add("advisory", "C12", cpath, "an ID is opened twice")
            for item in fold_carried(new_rows):
                age = days_since(item["date"])
                if age is not None and age > 14:
                    f.add("warn", "C16", cpath, f"{item['id']} open {age} days")
        comms = {}
        for p in concept_paths():
            if p.startswith(".okf/comms/"):
                d = Doc.load(p)
                cv = d.atb.get("covers") if isinstance(d.atb.get("covers"), dict) else None
                if cv and cv.get("source"):
                    comms.setdefault(cv["source"], []).append((p, parse_time(cv.get("first_at", "")), parse_time(cv.get("last_at", ""))))
        for src, items in comms.items():
            items = sorted([i for i in items if i[1] and i[2]], key=lambda x: x[1])
            for a, b in zip(items, items[1:]):
                if b[1] <= a[2]:
                    f.add("warn", "C13", b[0], f"time range overlaps {a[0]} for the same source")
        for n in sorted((ROOT / "inbox").glob("*.md")) if (ROOT / "inbox").exists() else []:
            if n.name == "carried.md":
                continue
            age = note_age(rel(n))
            if age is not None and age > 7:
                f.add("warn", "C16", rel(n), f"inbox note is {age} days old; run end-session")
        check_hook(f)
        if str(cfg.get("symlinks", "")) == "forbidden":
            check_symlinks(f)
        ga = ROOT / ".gitattributes"
        gtext = read_text(ga) if ga.exists() else ""
        for pat in (".okf/** text eol=lf", "inbox/** text eol=lf"):
            if pat not in gtext:
                f.add("warn", "C18", ".gitattributes", f"missing line '{pat}'")
        for rp in reports:
            for p in sorted((ROOT / rp).rglob("*.md")) if (ROOT / rp).exists() else []:
                fm, _, _ = split_doc(read_text(p))
                for n, line in enumerate(fm or [], start=2):
                    if re.match(r"^\s*(to|from|cc|bcc):", line, re.I) and PATTERNS[0][1].search(line):
                        f.add("warn", "C19", f"{rel(p)}:{n}", "address in a report's frontmatter; use names only")
        cfg_text = read_text(ROOT / "okf.config")
        for n, line in enumerate(cfg_text.split("\n"), start=1):
            for ph in PLACEHOLDER.findall(line):
                f.add("warn", "C24", f"okf.config:{n}", f"placeholder {ph} not filled")
    return f.print()


def days_since(date: str) -> int | None:
    try:
        d = dt.date.fromisoformat(str(date)[:10])
    except ValueError:
        return None
    return (dt.date.today() - d).days


def note_age(path: str) -> int | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(path).name)
    return days_since(m.group(1)) if m else None


# ----------------------------------------------------------------------------- carried (8.1)

CARRIED_HEADER = "| id | date | event | text | run |\n|---|---|---|---|---|\n"


def fold_carried(rows: list[list[str]]) -> list[dict]:
    items: dict[str, dict] = {}
    for r in rows:
        if len(r) < 5:
            continue
        cid, date, ev, text, run = r[:5]
        if ev == "open":
            items[cid] = {"id": cid, "date": date, "text": text, "run": run}
        elif ev in ("close", "void"):
            items.pop(cid, None)
        elif ev == "amend" and cid in items:
            items[cid]["text"] = text
    return list(items.values())


def next_id(rows: list[list[str]]) -> int:
    nums = [int(r[0][2:]) for r in rows if re.match(r"^C-\d{4}$", r[0])]
    return max(nums, default=0) + 1


def cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ").strip()


def append_carried(events: list[dict], run_slug: str) -> list[dict]:
    p = ROOT / "inbox" / "carried.md"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(CARRIED_HEADER, encoding="utf-8", newline="\n")
    text = read_text(p)
    rows = carried_rows(text)
    if any(len(r) > 4 and r[4] == run_slug for r in rows):
        return [e for e in events]  # already appended (idempotent, spec 4.4 step 7)
    n = next_id(rows)
    lines, out = [], []
    today = dt.date.today().isoformat()
    for e in events:
        ev = e.get("event", "open")
        cid = e.get("id")
        if ev == "open":
            cid = f"C-{n:04d}"; n += 1
        elif not cid:
            raise Fail(f"carried event '{ev}' needs an id")
        out.append({**e, "id": cid})
        lines.append(f"| {cid} | {e.get('date', today)} | {ev} | {cell(e.get('text', ''))} | {run_slug} |")
    if lines:
        if not text.endswith("\n"):
            text += "\n"
        p.write_text(text + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return out


def cmd_carried(args: list[str]) -> int:
    load_config()
    if args[:2] == ["list", "--open"] or args[:1] == ["list"]:
        p = ROOT / "inbox" / "carried.md"
        for item in fold_carried(carried_rows(read_text(p))) if p.exists() else []:
            print(f"{item['id']}  {item['date']}  {item['text']}  ({item['run']})")
        return 0
    if args[:1] == ["--seed"]:
        src, slug = args[1], opt(args, "--run")
        if not slug or not SLUG_RE.match(slug):
            raise Fail("--run needs a slug like YYYY-MM-DD-migration")
        text = read_text(ROOT / src)
        header = None
        events = []
        for l in text.split("\n"):
            if not l.startswith("|") or re.match(r"^\|[\s:-]+\|", l):
                continue
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            if header is None:
                header = [c.lower() for c in cells]
                if "status" not in header:
                    raise Fail(f"{src}: table has no Status column")
                continue
            row = dict(zip(header, cells))
            st = row.get("status", "")
            if not (st == "Open" or st.startswith("On Hold") or st == "needs-follow-up"):
                continue
            txt = (row.get("title") or row.get("request") or "")[:120]
            for kind, _, _ in scan_line(txt):
                raise Refuse(f"{src}: row '{txt[:30]}…' has a {kind} pattern; edit or refuse it first")
            events.append({"event": "open", "text": txt, "date": row.get("date", "")[:10] or dt.date.today().isoformat()})
        if header is None:
            raise Fail(f"{src}: no table found")
        with Lock():
            out = append_carried(events, slug)
        print(f"seeded {len(out)} open items from {src}")
        return 0
    slug = opt(args, "--run")
    if not slug:
        raise Fail("usage: carried --run S | carried list --open | carried --seed FILE --run S")
    with Lock():
        r = load_run(slug)
        if r["state"] != "stamped" and not (r["state"] == "failed" and (r.get("failed") or {}).get("step") == 7):
            raise Refuse(f"run {slug} is {r['state']}; carry needs state stamped")
        r["carried_events"] = append_carried(r.get("carried_events", []), slug)
        r["failed"] = None
        r["state"] = "stamped"
        transition(r, "carried")
        save_run(r)
    print(f"carried: {len(r['carried_events'])} events")
    return 0


def opt(args: list[str], name: str, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
        raise Fail(f"{name} needs a value")
    return default


def multi(args: list[str], name: str) -> list[str]:
    if name not in args:
        return []
    out = []
    for a in args[args.index(name) + 1:]:
        if a.startswith("--"):
            break
        out.append(a)
    return out


# ----------------------------------------------------------------------------- run CLI (4.3)

def clean_pastes() -> None:
    d = Path.home() / "okf-pastes"
    if not d.exists():
        return
    cutoff = time.time() - 30 * 86400
    for p in d.glob("*.txt"):
        if p.stat().st_mtime < cutoff:
            p.unlink()


def unique_slug(slug: str) -> str:
    taken = {r["slug"] for r in all_runs()}
    trailers = git("log", "--format=%(trailers:key=Knowledge-Run,valueonly)", check=False).split()
    taken |= set(trailers)
    cand, n = slug, 2
    while cand in taken or (ROOT / "inbox" / f"{cand}.md").exists():
        cand = f"{slug}-{n}"; n += 1
    return cand


def path_owner(path: str, slug: str) -> str | None:
    for r in open_runs():
        if r["slug"] != slug and path in r.get("paths", {}):
            return r["slug"]
    return None


def head_has(path: str) -> bool:
    return git_ok("cat-file", "-e", f"HEAD:{path}")


def run_start(args: list[str]) -> int:
    cfg = load_config()
    mode, slug = opt(args, "--mode"), opt(args, "--slug")
    if mode not in MODES:
        raise Fail(f"--mode must be one of {', '.join(MODES)}")
    if not slug or not SLUG_RE.match(slug) or len(slug) > 50:
        raise Fail("--slug must look like YYYY-MM-DD-<words> (lowercase, at most 50 characters)")
    check_paused(cfg, "end-session" if mode in ("catch-up", "migration-review") else mode)
    clean_pastes()
    with Lock():
        slug = unique_slug(slug)
        r = {"schema": 1, "slug": slug, "mode": mode, "started": now_iso(), "state": "started",
             "paths": {}, "dropped_by_check": [], "commit_a": None, "commit_b": None,
             "refusals": [], "flags": [], "denylist": [], "participants": [],
             "review": {"accepted": [], "dropped": [], "flags_kept": []},
             "carried_events": [], "neither": [], "collected": [], "source": opt(args, "--source"),
             "covers": None, "scratch": tempfile.mkdtemp(prefix="okf-"), "reviewer": None,
             "failed": None}
        if mode == "migration-review":
            folder = opt(args, "--folder")
            if folder is None:
                raise Fail("--folder is required for migration-review")
            base = ROOT / ".okf" / folder
            files = [base / "client.md"] if folder == "." else sorted(base.glob("*.md"))
            for p in files:
                if not p.exists() or p.name in ("index.md", "log.md"):
                    continue
                d = Doc.load(rel(p))
                gen = d.meta.get("generated") if isinstance(d.meta.get("generated"), dict) else {}
                if d.meta.get("status") == "draft" and str(gen.get("by", "")).startswith("process:atb-okf-migration/"):
                    rp = rel(p)
                    owner = path_owner(rp, slug)
                    if owner:
                        raise Refuse(f"{rp} belongs to open run {owner}")
                    r["paths"][rp] = {"kind": "edit" if head_has(rp) else "new", "blob": blob_of(rp)}
            if not r["paths"]:
                shutil.rmtree(r["scratch"], ignore_errors=True)
                raise Refuse(f"no migration drafts in .okf/{folder}")
            r["state"] = "drafted"
        save_run(r)
    print(f"slug: {slug}\nscratch: {r['scratch']}")
    if mode == "migration-review":
        print(f"claimed: {len(r['paths'])} migration drafts")
    return 0


def cmd_run(args: list[str]) -> int:
    if not args:
        raise Fail("usage: run start|add-path|move-path|refuse|set|review|collect|commit|resume|abandon|list")
    sub, rest = args[0], args[1:]
    if sub == "start":
        return run_start(rest)
    if sub == "list":
        runs = all_runs() if not rest else [r for r in all_runs() if
               ("--open" in rest and (r["state"] in OPEN_STATES or r["state"] == "failed")) or
               ("--waiting" in rest and r["state"] == "waiting")]
        for r in runs:
            if r.get("collected_by"):
                continue
            nxt = NEXT_STEP.get(r["state"], "")
            stale = ""
            if r["state"] == "waiting":
                t = parse_time(r.get("started", ""))
                if t and (dt.datetime.now(dt.timezone.utc) - t).total_seconds() > 72 * 3600:
                    stale = " (stale)"
            print(f"{r['slug']}  {r['mode']}  {r['state']}{stale}  next: {nxt}")
        return 0
    if not rest:
        raise Fail(f"run {sub} needs a slug")
    slug = rest[0]
    if sub == "resume":
        return run_resume(slug)
    if sub == "commit":
        return run_commit(slug)
    cfg = load_config()
    with Lock():
        r = load_run(slug)
        if sub == "add-path":
            for p in [rel(x) for x in rest[1:]]:
                owner = path_owner(p, slug)
                if owner:
                    save_run(r)
                    raise Refuse(f"{p} belongs to open run {owner}; edit another file or `run move-path {owner} {p} --to {slug}`")
                prev = r["paths"].get(p, {})
                r["paths"][p] = {"kind": prev.get("kind") or ("edit" if head_has(p) else "new"), "blob": blob_of(p)}
        elif sub == "move-path":
            p, to = rel(rest[1]), opt(rest, "--to")
            if p not in r["paths"]:
                raise Fail(f"{p} is not in run {slug}")
            r2 = load_run(to)
            r2["paths"][p] = r["paths"].pop(p)
            save_run(r2)
        elif sub == "refuse":
            cat, note = opt(rest, "--category"), opt(rest, "--note", "")
            refuse_tbl = cfg.get("refuse") if isinstance(cfg.get("refuse"), dict) else {}
            if cat not in refuse_tbl:
                raise Fail(f"category '{cat}' not in okf.config refuse: ({', '.join(refuse_tbl)})")
            for kind, _, _ in scan_line(note):
                raise Refuse(f"the refusal note has a {kind} pattern; describe it without the detail")
            r["refusals"].append({"category": cat, "destination": refuse_tbl[cat], "note": note})
        elif sub == "set":
            if opt(rest, "--state"):
                transition(r, opt(rest, "--state"))
            for key, flag in (("commit_a", "--commit-a"), ("commit_b", "--commit-b"), ("source", "--source")):
                if opt(rest, flag):
                    r[key] = opt(rest, flag)
            for key, flag in (("covers", "--covers"), ("neither", "--neither"),
                              ("carried_events", "--carried"), ("participants", "--participants")):
                if opt(rest, flag):
                    try:
                        r[key] = json.loads(opt(rest, flag))
                    except json.JSONDecodeError as e:
                        raise Fail(f"{flag}: not valid JSON ({e})")
        elif sub == "review":
            if r["state"] != "checked":
                raise Refuse(f"run {slug} is {r['state']}; review needs state checked")
            for p in [rel(x) for x in multi(rest, "--drop")]:
                info = r["paths"].pop(p, None)
                if info is None:
                    continue
                if info["kind"] == "new" and (ROOT / p).exists():
                    (ROOT / p).unlink()
                elif info["kind"] == "edit":
                    git("checkout", "HEAD", "--", p)
                r["review"]["dropped"].append(p)
            r["review"]["accepted"] = [{"path": p, "blob": blob_of(p)} for p in
                                       ([rel(x) for x in multi(rest, "--accept")] or list(r["paths"]))
                                       if p in r["paths"]]
            kept = []
            for fid in multi(rest, "--keep-flag"):
                fl = r["flags"][int(fid) - 1]
                kept.append(fl)
                allow = ROOT / ".okf" / ".screen-allow"
                line = f"{fl['path']}:{fl['sha8']}:{fl['kind']}"
                existing = read_text(allow) if allow.exists() else ""
                if line not in existing.split("\n"):
                    allow.parent.mkdir(parents=True, exist_ok=True)
                    allow.write_text(existing + ("" if not existing or existing.endswith("\n") else "\n") + line + "\n",
                                     encoding="utf-8", newline="\n")
            r["review"]["flags_kept"] = kept
            transition(r, "reviewed")
        elif sub == "collect":
            for s2 in rest[1:]:
                w = load_run(s2)
                if w["state"] != "waiting":
                    raise Refuse(f"run {s2} is {w['state']}, not waiting")
                r["paths"].update(w["paths"])
                r["refusals"] += w["refusals"]
                r["flags"] += w["flags"]
                r["collected"].append({"slug": s2, "source": w.get("source"), "covers": w.get("covers"),
                                       "mode": w["mode"]})
                w["paths"] = {}
                w["state"] = "drafted"
                w["collected_by"] = slug
                save_run(w)
        elif sub == "abandon":
            for p, info in r["paths"].items():
                if blob_of(p) != info.get("blob"):
                    print(f"left alone (changed since): {p}")
                    continue
                if info["kind"] == "new" and (ROOT / p).exists():
                    (ROOT / p).unlink()
                elif info["kind"] == "edit":
                    git("checkout", "HEAD", "--", p)
            shutil.rmtree(r.get("scratch") or "", ignore_errors=True)
            r["state"] = "abandoned"
            for c in r.get("collected", []):
                w = load_run(c["slug"]); w["state"] = "waiting"; w.pop("collected_by", None); save_run(w)
        else:
            raise Fail(f"unknown run command '{sub}'")
        save_run(r)
    print(f"run {slug}: {r['state']}")
    return 0


NEXT_STEP = {"started": "1 screen", "screened": "2 inbox note + commit A", "inbox-committed": "3 classify",
             "drafted": "4 check", "waiting": "collected by the next close", "checked": "5 review",
             "reviewed": "6 stamp", "stamped": "7 carry", "carried": "8 index", "indexed": "9 commit B",
             "committed": "9 push", "failed": "resume"}


# ----------------------------------------------------------------------------- stamp (4.6)

def gh_bin() -> str:
    path = shutil.which("gh")
    if not path:
        raise Fail("gh is not installed (https://cli.github.com), then resume close")
    return path


def gh_login(cfg: dict) -> str:
    gh = gh_bin()
    r = subprocess.run([gh, "api", "user", "--jq", ".login"], capture_output=True, text=True)
    if r.returncode != 0:
        raise Fail("not logged in to gh: run `gh auth login`, then resume close")
    login = r.stdout.strip()
    if login not in [str(x) for x in cfg_list(cfg, "reviewers")]:
        raise Fail(f"login '{login}' is not in okf.config reviewers")
    url = git("remote", "get-url", "origin").strip()
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url)
    if not m:
        raise Fail(f"cannot read owner/repo from origin '{url}'")
    r = subprocess.run([gh, "api", f"repos/{m.group(1)}/{m.group(2)}/collaborators/{login}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise Fail(f"login '{login}' is not a collaborator of {m.group(1)}/{m.group(2)}")
    return login


def cmd_stamp(args: list[str]) -> int:
    cfg = load_config()
    slug = opt(args, "--run")
    if not slug:
        raise Fail("usage: stamp --run S")
    with Lock():
        r = load_run(slug)
        if r["state"] == "failed" and r["failed"].get("step") == 6:
            r["state"], r["failed"] = "reviewed", None
        if r["state"] != "reviewed":
            raise Refuse(f"run {slug} is {r['state']}; stamp needs state reviewed")
        changed = [a["path"] for a in r["review"]["accepted"] if blob_of(a["path"]) != a["blob"]]
        if changed:
            transition(r, "checked")
            save_run(r)
            raise Refuse("changed after review, back to review: " + ", ".join(changed))
        try:
            login = gh_login(cfg)
        except Fail as e:
            fail_run(r, 6, str(e), "reviewed")
        now = now_iso()
        accepted = [a["path"] for a in r["review"]["accepted"]]
        superseded = {}
        for p in accepted:
            d = Doc.load(p)
            sup = d.atb.get("supersedes")
            if sup:
                target = rel((ROOT / p).parent / sup)
                if target in r["paths"]:
                    superseded[target] = Path(p).name
        for p in accepted + [t for t in superseded if t not in accepted]:
            d = Doc.load(p)
            if d.error:
                continue
            if p in superseded:
                d.set_top("status", "deprecated")
                d.set_atb("superseded_by", superseded[p])
            elif d.meta.get("status") == "draft":
                d.set_top("status", "stable")
            if d.meta.get("type") in ("Decision", "Rule") and d.meta.get("status") == "stable":
                d.append_verified(f"human:{login}", now)
                d.set_atb("verified_via", "close")
                d.set_atb("verified_hash", concept_hash(d.render()))
            d.save()
            if p in superseded and p not in accepted:
                r["review"]["accepted"].append({"path": p, "blob": None})
            for a in r["review"]["accepted"]:
                if a["path"] == p:
                    a["blob"] = blob_of(p)
            r["paths"][p]["blob"] = blob_of(p)
        r["reviewer"] = login
        transition(r, "stamped")
        save_run(r)
    print(f"stamped {len(accepted)} files as human:{login}")
    return 0


# ----------------------------------------------------------------------------- index & log

def cmd_index(args: list[str]) -> int:
    base = ROOT / ".okf"
    base.mkdir(exist_ok=True)
    written = []
    for folder in FOLDER_TYPE:
        d = base / folder
        d.mkdir(exist_ok=True)
        lines = [f"# {folder.capitalize()}", ""]
        for p in sorted(d.glob("*.md")):
            if p.name in ("index.md", "log.md"):
                continue
            doc = Doc.load(rel(p))
            title = doc.meta.get("title") or p.stem
            desc = doc.meta.get("description")
            lines.append(f"* [{title}]({p.name})" + (f" — {desc}" if desc else ""))
        if len(lines) == 2:
            lines.append("No concepts yet.")
        (d / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        written.append(rel(d / "index.md"))
    root = ['---', 'okf_version: "0.2"', '---', '', '# Knowledge bundle', '']
    if (base / "client.md").exists():
        c = Doc.load(".okf/client.md")
        root.append(f"* [{c.meta.get('title') or 'Client'}](client.md)" +
                    (f" — {c.meta['description']}" if c.meta.get("description") else ""))
    for folder in FOLDER_TYPE:
        n = len([p for p in (base / folder).glob("*.md") if p.name != "index.md"])
        root.append(f"* [{folder.capitalize()}]({folder}/index.md) — {n} concepts")
    (base / "index.md").write_text("\n".join(root) + "\n", encoding="utf-8", newline="\n")
    written.append(".okf/index.md")
    slug = opt(args, "--run")
    if slug:
        with Lock():
            r = load_run(slug)
            if r["state"] == "failed" and r["failed"].get("step") == 8:
                r["state"], r["failed"] = "carried", None
            transition(r, "indexed")
            r["indexes"] = written
            save_run(r)
    print(f"indexed: {len(written)} files")
    return 0


def cmd_log(args: list[str]) -> int:
    cfg = load_config()
    out = git("log", cfg.get("branch", "main"), "--format=%x01%H%x00%ad%x00%s%x00%(trailers:key=Knowledge-Run,valueonly)",
              "--date=short", "--name-status", "--", ".okf/", check=False)
    days: dict[str, list[str]] = {}
    for chunk in out.split("\x01")[1:]:
        head, _, files = chunk.partition("\n")
        parts = head.split("\x00")
        if len(parts) < 4 or not parts[2].startswith("knowledge:"):
            continue
        h, date, run = parts[0], parts[1], parts[3].strip() or parts[2][10:].strip()
        for fl in files.strip().split("\n"):
            if not fl.strip():
                continue
            st, _, path = fl.partition("\t")
            path = path.split("\t")[-1]
            if Path(path).name in ("index.md", "log.md") or not path.endswith(".md"):
                continue
            label = "Creation" if st.startswith("A") else "Update"
            text = at_ref(h, path)
            title = Path(path).stem
            if text is not None:
                d = Doc(path, text)
                title = d.meta.get("title") or title
                if st.startswith("M") and d.meta.get("status") == "deprecated":
                    prev = at_ref(f"{h}^", path)
                    if prev is None or Doc(path, prev).meta.get("status") != "deprecated":
                        label = "Deprecation"
            if st.startswith("D"):
                continue
            days.setdefault(date, []).append(f"* **{label}**: [{title}]({bundle_rel(path)}) (knowledge: {run})")
    lines = ["# Log", ""]
    for date in sorted(days, reverse=True):
        lines += [f"## {date}", ""] + days[date] + [""]
    (ROOT / ".okf").mkdir(exist_ok=True)
    (ROOT / ".okf" / "log.md").write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    print(f"log: {sum(len(v) for v in days.values())} entries")
    return 0


# ----------------------------------------------------------------------------- commit B (4.7)

def build_commit_b(r: dict) -> str:
    accepted = [a["path"] for a in r["review"]["accepted"]]
    mode_tokens = [r["mode"]] + [c["mode"] for c in r.get("collected", []) if c["mode"] not in (r["mode"],)]
    lines = [f"knowledge: {r['slug']}", ""]
    if r.get("neither"):
        lines += ["Neither:"] + [f"- {n.get('item')} — {n.get('reason')}" if isinstance(n, dict) else f"- {n}"
                                 for n in r["neither"]] + [""]
    if not accepted and r["mode"] == "log-comms":
        lines += ["Nothing to keep from this source.", ""]
    opened = sum(1 for e in r.get("carried_events", []) if e.get("event", "open") == "open")
    closed = sum(1 for e in r.get("carried_events", []) if e.get("event") == "close")
    lines.append(f"Knowledge-Run: {r['slug']}")
    if r["mode"] != "migration-review":
        lines.append(f"Knowledge-Inbox: inbox/{r['slug']}.md")
        lines.append(f"Knowledge-Commit-A: {r.get('commit_a') or ''}")
    for src in [r.get("source")] + [c.get("source") for c in r.get("collected", [])]:
        if src:
            lines.append(f"Knowledge-Source: {src}")
    started = parse_time(r.get("started", ""))
    minutes = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() // 60) if started else 0
    lines += [f"Knowledge-Promoted: {len(accepted)}",
              f"Knowledge-Dropped: {len(r['review']['dropped'])}",
              f"Knowledge-Dropped-By-Check: {len(r.get('dropped_by_check', []))}",
              f"Knowledge-Refused: {len(r.get('refusals', []))}",
              f"Knowledge-Flags: {len(r.get('flags', []))}/{len(r['review'].get('flags_kept', []))}",
              f"Knowledge-Neither: {len(r.get('neither', []))}",
              f"Knowledge-Carried: {opened}/{closed}",
              f"Knowledge-Mode: {'migration' if r['mode'] == 'migration-review' else ' '.join(mode_tokens)}",
              f"Knowledge-Run-Minutes: {minutes}"]
    return "\n".join(lines) + "\n"


def run_commit(slug: str) -> int:
    cfg = load_config()
    with Lock():
        r = load_run(slug)
        if r["state"] == "failed" and r["failed"].get("step") == 9:
            r["state"], r["failed"] = r["failed"].get("resume_state", "indexed"), None
        if r["state"] == "indexed":
            existing = git("log", "--format=%H", f"--grep=^Knowledge-Run: {slug}$", "-n", "1",
                           "--extended-regexp", check=False).strip()
            subjects = git("log", "--format=%s", "-n", "1", existing, check=False).strip() if existing else ""
            if existing and subjects.startswith("knowledge:"):
                r["commit_b"] = existing
            else:
                paths = set(r["paths"]) | set(r["review"]["dropped"]) | set(r.get("indexes", []))
                paths |= {"inbox/carried.md", ".okf/.screen-allow"}
                if r["mode"] != "migration-review":
                    paths.add(f"inbox/{slug}.md")
                quick = [p for p in r.get("quick_notes", [])]
                paths |= set(quick)
                present = sorted(p for p in paths if (ROOT / p).exists())
                gone = sorted(p for p in paths if not (ROOT / p).exists() and head_has(p))
                if r["mode"] != "migration-review" and (ROOT / "inbox" / f"{slug}.md").exists():
                    (ROOT / "inbox" / f"{slug}.md").unlink()
                    present.remove(f"inbox/{slug}.md")
                    gone.append(f"inbox/{slug}.md")
                if present:
                    git("add", "--", *present)
                if gone:
                    git("rm", "--cached", "-q", "--ignore-unmatch", "--", *gone)
                msg = build_commit_b(r)
                git("commit", "-q", "-m", msg, "--", *(present + gone))
                r["commit_b"] = git("rev-parse", "HEAD").strip()
            transition(r, "committed")
            save_run(r)
        if r["state"] != "committed":
            raise Refuse(f"run {slug} is {r['state']}; commit needs state indexed")
        branch = cfg.get("branch", "main")
        res = subprocess.run(["git", "push", "origin", f"HEAD:{branch}"], cwd=ROOT, capture_output=True, text=True)
        if res.returncode != 0:
            fail_run(r, 9, f"push failed: {res.stderr.strip()[:200]}", "committed")
        transition(r, "done")
        shutil.rmtree(r.get("scratch") or "", ignore_errors=True)
        for c in r.get("collected", []):
            w = load_run(c["slug"]); w["state"] = "done"; save_run(w)
        save_run(r)
    print(f"done: {r['commit_b'][:7]} pushed to {branch}")
    return 0


def run_resume(slug: str) -> int:
    r = load_run(slug)
    st = r["state"] if r["state"] != "failed" else {6: "reviewed", 7: "stamped", 8: "carried", 9: "indexed"}.get(
        (r.get("failed") or {}).get("step"), "?")
    if r["state"] == "failed" and (r.get("failed") or {}).get("step") == 9:
        st = r["failed"].get("resume_state", "indexed")
    steps = {"reviewed": ["stamp", "carry", "index", "commit"], "stamped": ["carry", "index", "commit"],
             "carried": ["index", "commit"], "indexed": ["commit"], "committed": ["commit"]}
    if st not in steps:
        print(f"run {slug} is {r['state']}; next step is the model's: {NEXT_STEP.get(r['state'], '?')}")
        return 0
    for s in steps[st]:
        if s == "stamp":
            cmd_stamp(["--run", slug])
        elif s == "carry":
            cmd_carried(["--run", slug])
        elif s == "index":
            cmd_index(["--run", slug])
        else:
            return run_commit(slug)
    return 0


# ----------------------------------------------------------------------------- screen (6.2)

QUOTE_CUT = [re.compile(r"^On .+ wrote:$"), re.compile(r"^-----Original Message-----$")]
SIGNOFF = re.compile(r"^(Best|Regards|Thanks|Cheers|Kind regards|Best regards)\b", re.I)
NAME2 = re.compile(r"\b([A-ZÄÖÜ][a-zäöüéèàß]+(?:-[A-Z][a-z]+)?) ([A-ZÄÖÜ][a-zäöüéèàß]+(?:-[A-Z][a-z]+)?)\b")


def strip_quoted(text: str) -> str:
    lines = text.split("\n")
    out = []
    for i, l in enumerate(lines):
        if l.startswith(">"):
            continue
        if any(rx.match(l.strip()) for rx in QUOTE_CUT):
            break
        if re.match(r"^From:", l.strip()) and any(re.match(r"^(Sent|Date):", x.strip()) for x in lines[i + 1:i + 5]):
            break
        out.append(l)
    return "\n".join(out)


def denylist_from(text: str) -> list[str]:
    deny = []
    lines = text.split("\n")
    sig_start = None
    for i, l in enumerate(lines):
        if l.rstrip() == "-- " or SIGNOFF.match(l.strip()):
            sig_start = i + 1
            break
    regions = [l for l in lines if re.match(r"^\s*Cc:", l, re.I)]
    if sig_start is not None:
        regions += lines[sig_start: sig_start + 8]
    for l in regions:
        deny += PATTERNS[0][1].findall(l)
        deny += [c for _, _, c in phone_hits(l)]
        deny += [" ".join(m) for m in NAME2.findall(l)]
    return sorted(set(d.strip() for d in deny if d.strip()))


def message_texts(scratch: Path) -> list[Path]:
    return sorted(p for p in scratch.rglob("*") if p.is_file())


def cmd_screen(args: list[str]) -> int:
    cfg = load_config()
    slug = opt(args, "--run")
    if "--pre" in args:
        if not slug:
            raise Fail("screen --pre needs --run S")
        with Lock():
            r = load_run(slug)
            deny = []
            scratch = Path(r.get("scratch") or "")
            for p in message_texts(scratch) if scratch.exists() else []:
                if p.suffix == ".json":
                    data = json.loads(p.read_text(encoding="utf-8"))
                    strings = []

                    def walk(o, key=""):
                        if isinstance(o, dict):
                            for k, v in o.items():
                                walk(v, k)
                        elif isinstance(o, list):
                            for v in o:
                                walk(v, key)
                        elif isinstance(o, str):
                            strings.append(f"Cc: {o}" if key.lower() == "cc" else o)
                    walk(data)
                    text = "\n".join(strings)
                    deny += denylist_from(text)
                else:
                    text = read_text(p)
                    deny += denylist_from(text)
                    p.write_text(strip_quoted(text), encoding="utf-8")
            r["denylist"] = sorted(set(deny))
            save_run(r)
        print(f"screen --pre: {len(r['denylist'])} denylist entries; quoted text stripped")
        return 0
    if "--post" not in args:
        raise Fail("screen needs --pre or --post")
    paths = [rel(a) for a in args if not a.startswith("--") and a != slug]
    if not slug:
        hits = []
        for p in paths:
            hits += scan_file(p)
        for h in hits:
            print(f"{h['path']}:{h['line']}: {h['kind']}")
        if hits:
            raise Refuse(f"{len(hits)} hits; remove them or ask the user")
        print("screen --post: clean")
        return 0
    with Lock():
        r = load_run(slug)
        paths = paths or [p for p in r["paths"] if (ROOT / p).exists()]
        allow = load_allow()
        known = {str(x) for x in ((cfg.get("screen") or {}).get("allow_names") or [])} if isinstance(cfg.get("screen"), dict) else set()
        known |= {str(x) for x in r.get("participants", [])}
        for p in concept_paths():
            if p.startswith(".okf/people/"):
                known.add(str(Doc.load(p).meta.get("title", "")))
        new_flags = []
        for p in paths:
            new_flags += scan_file(p, r.get("denylist", []), allow)
            for n, line in scannable(read_text(ROOT / p)):
                for a, b in NAME2.findall(line):
                    name = f"{a} {b}"
                    if name in known or f"{p}:{sha8(line)}:name-not-known" in allow:
                        continue
                    new_flags.append({"path": p, "line": n, "kind": "name-not-known", "sha8": sha8(line), "name": name})
        keys = {(f["path"], f["line"], f["kind"]) for f in r["flags"]}
        for fl in new_flags:
            if (fl["path"], fl["line"], fl["kind"]) not in keys:
                r["flags"].append(fl)
        save_run(r)
    for i, fl in enumerate(r["flags"], start=1):
        if fl["path"] in paths:
            print(f"[{i}] {fl['path']}:{fl['line']}: {fl['kind']}")
    if any(fl["path"] in paths for fl in r["flags"]):
        raise Refuse("flags recorded in the run; show them at review")
    print("screen --post: clean")
    return 0


# ----------------------------------------------------------------------------- closest

def cmd_closest(args: list[str]) -> int:
    title = args[0] if args else ""
    t = opt(args, "--type")
    scored = []
    for p in concept_paths():
        d = Doc.load(p)
        if t and d.meta.get("type") != t:
            continue
        cand = f"{d.meta.get('title', '')} {Path(p).stem.replace('-', ' ')}".lower()
        scored.append((difflib.SequenceMatcher(None, title.lower(), cand).ratio(), p, d.meta.get("title", "")))
    for score, p, ti in sorted(scored, reverse=True)[:3]:
        print(f"{score:.2f}  {p}  {ti}")
    return 0


# ----------------------------------------------------------------------------- reports (7, 8.4)

def last_commit_b(branch: str) -> tuple[str | None, str]:
    out = git("log", branch, "--format=%H%x00%ct%x00%(trailers:key=Knowledge-Mode,valueonly)",
              "--grep=^knowledge:", check=False)
    for line in out.split("\n"):
        parts = line.split("\x00")
        if len(parts) >= 3:
            tokens = parts[2].split()
            if "end-session" in tokens or "catch-up" in tokens:
                return parts[0], parts[1]
    first = git("log", branch, "--format=%H%x00%ct", "--diff-filter=A", "--reverse", "--", "okf.config",
                check=False).strip().split("\n")[0]
    if first and "\x00" in first:
        h, ct = first.split("\x00")
        return h, ct
    return None, ""


def cmd_debt() -> int:
    cfg = load_config()
    branch = cfg.get("branch", "main")
    print(f"== OKF debt ==  (okf-tooling {TOOLING_VERSION})")
    notes = sorted((ROOT / "inbox").glob("*.md")) if (ROOT / "inbox").exists() else []
    notes = [n for n in notes if n.name != "carried.md"]
    print(f"1. inbox notes: {len(notes)}" + "".join(f"\n   {rel(n)} ({note_age(rel(n))}d)" for n in notes))
    cp = ROOT / "inbox" / "carried.md"
    old = [i for i in (fold_carried(carried_rows(read_text(cp))) if cp.exists() else [])
           if (days_since(i["date"]) or 0) > 14]
    print(f"2. carried items open > 14 days: {len(old)}" + "".join(f"\n   {i['id']} {i['text']}" for i in old))
    drift, stale = [], []
    for p in concept_paths():
        d = Doc.load(p)
        if d.error:
            continue
        h = d.atb.get("verified_hash")
        if d.meta.get("type") in ("Decision", "Rule") and h and h != concept_hash(d.text):
            drift.append(p)
        sa = parse_time(d.meta.get("stale_after", "")) if d.meta.get("stale_after") else None
        if sa and sa < dt.datetime.now(dt.timezone.utc):
            stale.append(p)
    print(f"3. verified Decisions/Rules changed since: {len(drift)}" + "".join(f"\n   {p}" for p in drift))
    print(f"4. concepts past stale_after: {len(stale)}" + "".join(f"\n   {p}" for p in stale))
    base, ct = last_commit_b(branch)
    if base:
        log = git("log", f"{base}..{branch}", "--format=%s%x00%ae", check=False)
        uncovered = [l for l in log.split("\n") if l and not l.startswith("chore:")
                     and not l.split("\x00")[-1].endswith("[bot]@users.noreply.github.com")
                     and not l.startswith(("knowledge:", "inbox:"))]
        print(f"5. commits since the last close: {len(uncovered)}")
        days = int((time.time() - int(ct)) // 86400) if ct else "?"
        print(f"7. days since the last close: {days}")
    else:
        print("5. commits since the last close: n/a (okf.config not committed yet)")
        print("7. days since the last close: n/a")
    dirty = [l for l in git("status", "--porcelain").split("\n") if l.strip()]
    print(f"6. uncommitted changes: {len(dirty)}")
    runs = [r for r in open_runs() if not r.get("collected_by")]
    lines = []
    for r in runs:
        stale_w = ""
        t = parse_time(r.get("started", ""))
        if r["state"] == "waiting" and t and (dt.datetime.now(dt.timezone.utc) - t).total_seconds() > 72 * 3600:
            stale_w = " (stale)"
        lines.append(f"\n   {r['slug']} {r['state']}{stale_w}")
    print(f"8. open runs: {len(runs)}" + "".join(lines))
    unpushed = git("log", f"origin/{branch}..{branch}", "--format=%h %s", "--grep=^knowledge:", check=False).strip()
    print(f"9. commit B not pushed: {len(unpushed.splitlines()) if unpushed else 0}")
    print(f"10. setup_version: {cfg.get('setup_version') or 'n/a (setup-project not built)'}")
    return 0


def cmd_spot_check(args: list[str]) -> int:
    cfg = load_config()
    week = opt(args, "--week") or dt.date.today().strftime("%G-W%V")
    m = re.match(r"^(\d{4})-W(\d{2})$", week)
    if not m:
        raise Fail("--week must look like YYYY-Www")
    y, w = int(m.group(1)), int(m.group(2))
    start = dt.date.fromisocalendar(y, w, 1)
    end = start + dt.timedelta(days=7)
    out = git("log", cfg.get("branch", "main"), f"--since={start.isoformat()}", f"--until={end.isoformat()}",
              "--grep=^knowledge:", "--format=%x01%(trailers:key=Knowledge-Run,valueonly)", "--name-only", "--", ".okf/",
              check=False)
    cands = {}
    for chunk in out.split("\x01")[1:]:
        run_slug, _, files = chunk.partition("\n")
        for f in files.split("\n"):
            if f.endswith(".md") and Path(f).name not in ("index.md", "log.md") and (ROOT / f).exists():
                cands[f] = run_slug.strip()
    order = {"Comms": 0, "Person": 1}
    keyed = sorted(cands, key=lambda p: (order.get(Doc.load(p).meta.get("type"), 2), p))
    rng = random.Random(y * 100 + w)
    sample = keyed if len(keyed) <= 5 else sorted(rng.sample(keyed, 5), key=keyed.index)
    me = None
    try:
        r = subprocess.run([gh_bin(), "api", "user", "--jq", ".login"], capture_output=True, text=True)
        me = r.stdout.strip() or None
    except Fail:
        pass
    runs = {r["slug"]: r for r in all_runs()}
    print(f"Spot check {week}: {len(sample)} concepts")
    other = 0
    for p in sample:
        d = Doc.load(p)
        run = runs.get(cands[p], {})
        src = [s.get("resource") if isinstance(s, dict) else s for s in d.meta.get("sources", [])] if isinstance(d.meta.get("sources"), list) else []
        cov = d.atb.get("covers")
        note = ""
        if str(run.get("source", "")).startswith("paste:") and run.get("reviewer") and me and run["reviewer"] != me:
            note = "  source not available: reviewer machine"
            other += 1
        print(f"- {p}  sources: {src or '-'}  covers: {cov or '-'}{note}\n  leak: 0\n  miss: 0")
    if other:
        print(f"source not available (reviewer machine): {other}")
    return 0


# ----------------------------------------------------------------------------- migrate

def inventory_map() -> dict[str, str]:
    p = ROOT / "docs" / "okf-migration-inventory.md"
    out = {}
    if not p.exists():
        return out
    header = None
    for l in read_text(p).split("\n"):
        if not l.startswith("|") or re.match(r"^\|[\s:-]+\|", l):
            continue
        cells = [c.strip().strip("`") for c in l.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        row = dict(zip(header, cells))
        if row.get("old path") and row.get("new path"):
            out[row["old path"]] = row["new path"]
    return out


def relpath(target: str, start_file: str) -> str:
    return os.path.relpath(target, os.path.dirname(start_file) or ".").replace(os.sep, "/")


def cmd_migrate(args: list[str]) -> int:
    load_config()
    inv = inventory_map()
    back = {v: k for k, v in inv.items()}
    unresolved = 0
    for a in args:
        path = rel(a)
        if not path.startswith(".okf/"):
            raise Fail(f"{path}: migrate runs on files already moved into .okf/ (git mv first)")
        br = bundle_rel(path)
        t = "Client" if br == "client.md" else FOLDER_TYPE.get(br.split("/")[0])
        if not t:
            raise Fail(f"{path}: cannot tell the type from the folder")
        text = read_text(ROOT / path)
        fm, body, _ = split_doc(text)
        old: dict = {}
        if fm is not None:
            try:
                old = parse_yaml("\n".join(fm))
            except ParseError:
                for l in fm:
                    m = re.match(r"^\s*([A-Za-z_]+):\s*(.*)$", l)
                    if m and m.group(2):
                        old.setdefault(m.group(1), m.group(2).strip().strip('"\''))
        meta_nested = old.get("metadata") if isinstance(old.get("metadata"), dict) else {}
        title = old.get("title") or old.get("name") or meta_nested.get("name")
        if not title:
            h = re.search(r"^#\s+(.+)$", body, re.M)
            title = h.group(1).strip() if h else Path(path).stem.replace("-", " ")
        new = {"type": t, "title": title}
        desc = old.get("description") or meta_nested.get("description")
        if desc:
            new["description"] = desc
        new["status"] = "draft"
        new["generated"] = {"by": MIGRATION_ACTOR, "at": now_iso()}
        if STALE[t]:
            new["stale_after"] = (dt.datetime.now().astimezone() + dt.timedelta(days=STALE[t])).replace(microsecond=0).isoformat()
        for k in ("sources", "tags"):
            if isinstance(old.get(k), list):
                new[k] = old[k]
        if isinstance(old.get("atb"), dict):
            new["atb"] = {k: v for k, v in old["atb"].items() if k in ATB_ALL | ATB_KEYS[t]}
        old_path = back.get(path, path)

        def wiki(m):
            nonlocal unresolved
            name = m.group(1).split("|")[0].strip()
            hits = [n for o, n in inv.items() if Path(o).stem == name]
            if hits:
                return f"[{name}]({relpath(hits[0], path)})"
            print(f"unresolved wikilink [[{name}]] in {path}")
            unresolved += 1
            return m.group(0)

        def link(m):
            nonlocal unresolved
            target = m.group(2)
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                return m.group(0)
            tgt, frag = (target.split("#", 1) + [""])[:2]
            abs_old = os.path.normpath(os.path.join(os.path.dirname(old_path), tgt)).replace(os.sep, "/")
            new_tgt = inv.get(abs_old, abs_old)
            if not (ROOT / new_tgt).exists():
                print(f"unresolved link '{target}' in {path}")
                unresolved += 1
                return m.group(0)
            return f"[{m.group(1)}]({relpath(new_tgt, path)}{'#' + frag if frag else ''})"

        body = re.sub(r"\[\[([^\]]+)\]\]", wiki, body)
        body = re.sub(r"(?<!\!)\[([^\]]*)\]\(([^)\s]+)\)", link, body)
        out = "---\n" + "\n".join(emit(new)) + "\n---\n" + body.lstrip("\n")
        (ROOT / path).write_text(out if out.endswith("\n") else out + "\n", encoding="utf-8", newline="\n")
        print(f"migrated {path} as {t}")
    if unresolved:
        print(f"{unresolved} links did not resolve")
    return 0


# ----------------------------------------------------------------------------- paused, account-check

def cmd_paused(args: list[str]) -> int:
    if not args:
        raise Fail("usage: paused <skill>")
    check_paused(load_config(), args[0])
    print(f"{args[0]}: not paused")
    return 0


def cmd_account_check(args: list[str]) -> int:
    cfg = load_config()
    alias = opt(args, "--alias", "?")
    comms = cfg.get("comms") if isinstance(cfg.get("comms"), dict) else {}
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        raise Fail("account-check expects the profile JSON on stdin")

    def find(o):
        if isinstance(o, dict):
            if isinstance(o.get("emailAddress"), str):
                return o["emailAddress"]
            for v in o.values():
                x = find(v)
                if x:
                    return x
        if isinstance(o, list):
            for v in o:
                x = find(v)
                if x:
                    return x
        return None
    addr = (find(data) or "").strip().lower()
    if "@" not in addr:
        raise Refuse(f"{alias}: no emailAddress in the profile")
    domain = addr.split("@", 1)[1]
    digest = hashlib.sha256(addr.encode("utf-8")).hexdigest()
    allowed = [str(x).lower() for x in (comms.get("expect_account_sha256") or [])]
    if digest not in allowed or domain != str(comms.get("expect_domain", "")).lower():
        raise Refuse(f"{alias}: connected mailbox is on {domain}, not an expected account")
    print(f"{alias}: account ok ({domain})")
    return 0


# ----------------------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["--report"]:
            kind = argv[1] if len(argv) > 1 else ""
            if kind == "debt":
                return cmd_debt()
            if kind == "spot-check":
                return cmd_spot_check(argv[2:])
            raise Fail("--report debt | spot-check")
        if argv[:1] == ["--closest"]:
            return cmd_closest(argv[1:])
        if argv[:1] in (["--version"], ["-V"]):
            print(f"okf-tooling {TOOLING_VERSION}")
            return 0
        if argv[:1] in (["-h"], ["--help"]):
            print(__doc__)
            return 0
        cmds = {"screen": cmd_screen, "stamp": cmd_stamp, "index": cmd_index, "log": cmd_log,
                "run": cmd_run, "carried": cmd_carried, "migrate": cmd_migrate, "paused": cmd_paused,
                "account-check": cmd_account_check}
        if argv and argv[0] in cmds:
            if argv[0] != "run" and not (ROOT / "okf.config").exists():
                print("no okf.config: skipped")
                return 0
            return cmds[argv[0]](argv[1:])
        return cmd_check(argv)
    except Refuse as e:
        print(str(e), file=sys.stderr)
        return 2
    except (Fail, ParseError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
