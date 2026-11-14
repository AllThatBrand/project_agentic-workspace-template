# okf-tooling: 0.1.0
"""Unit tests for scripts/okf-check.py (plan item 31).

Each test that touches git builds a temporary repo whose `origin` is a local bare repo at
`.../test/test.git`, and puts a fake `gh` first on PATH. okf-check.py reads no test-only
environment variables; only the fake reads FAKE_GH_*.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parents[1] / "scripts" / "okf-check.py"
spec = importlib.util.spec_from_file_location("okf_check", SCRIPT)
okf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(okf)

CONFIG = textwrap.dedent("""\
    okf_config: 1
    branch: main
    tracker: {kind: jira, key: TST}
    topics: [deploy, commits]
    frozen: [legacy/]
    reports: [legacy/reports/]
    refuse:
      commercial: moco
      contact-detail: contacts
      credential: password-manager
    comms:
      adapters: [paste]
      expect_domain: example.org
      expect_account_sha256: [SHA]
    screen:
      allow_names: [Jane Doe]
    reviewers: [tester]
    paused: []
    setup_version: null
    """)

GOOD = {
    ".okf/decisions/2026-01-02-use-okf.md": """---
type: Decision
title: Use OKF
description: We adopt the bundle.
status: draft
generated: {by: "agent:test/model", at: 2026-01-02T10:00:00+00:00}
---
We use OKF.
""",
    ".okf/rules/commits.md": """---
type: Rule
title: Commits
status: draft
generated: {by: "agent:test/model", at: 2026-01-02T10:00:00+00:00}
atb:
  topic: commits
---
Commit to main.
""",
    ".okf/systems/site.md": """---
type: System
title: Site
status: draft
generated: {by: "agent:test/model", at: 2026-01-02T10:00:00+00:00}
stale_after: 2099-01-01T00:00:00+00:00
---
See [the rule](../rules/commits.md).
""",
}


def run_git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


class Repo:
    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="okf-test-"))
        self.root = self.tmp / "work"
        self.root.mkdir()
        remote = self.tmp / "remote" / "test" / "test.git"
        remote.mkdir(parents=True)
        run_git(remote, "init", "-q", "--bare", "-b", "main")
        run_git(self.root, "init", "-q", "-b", "main")
        run_git(self.root, "config", "user.email", "t@example.invalid")
        run_git(self.root, "config", "user.name", "Test")
        run_git(self.root, "config", "commit.gpgsign", "false")
        run_git(self.root, "remote", "add", "origin", str(remote))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        fake = self.bin / "gh.py"
        fake.write_text(textwrap.dedent("""\
            import os, sys
            a = sys.argv[1:]
            if a[:2] == ["api", "user"]:
                if os.environ.get("FAKE_GH_LOGIN", "tester") == "-":  # "-" = logged out (Windows drops empty vars)
                    sys.exit(1)
                print(os.environ.get("FAKE_GH_LOGIN", "tester")); sys.exit(0)
            if a and a[0] == "api" and "/collaborators/" in a[1]:
                sys.exit(0 if os.environ.get("FAKE_GH_COLLAB", "1") == "1" else 1)
            sys.exit(1)
            """))
        if os.name == "nt":
            (self.bin / "gh.cmd").write_text(f'@"{sys.executable}" "%~dp0gh.py" %*\r\n')
        else:
            sh = self.bin / "gh"
            sh.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/gh.py" "$@"\n')
            sh.chmod(sh.stat().st_mode | stat.S_IEXEC)

    def write(self, path, text):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, msg="c", *paths):
        run_git(self.root, "add", "-A", *(["--"] + list(paths) if paths else []))
        run_git(self.root, "commit", "-q", "-m", msg, "--allow-empty")

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.old_cwd = os.getcwd()
        self.old_root = okf.ROOT
        self.old_path = os.environ.get("PATH", "")
        self.old_home = os.environ.get("HOME")
        os.chdir(self.repo.root)
        okf.ROOT = self.repo.root
        os.environ["PATH"] = str(self.repo.bin) + os.pathsep + self.old_path
        os.environ["HOME"] = str(self.repo.tmp)
        os.environ.pop("CI", None)

    def tearDown(self):
        os.chdir(self.old_cwd)
        okf.ROOT = self.old_root
        os.environ["PATH"] = self.old_path
        if self.old_home is not None:
            os.environ["HOME"] = self.old_home
        for k in ("FAKE_GH_LOGIN", "FAKE_GH_COLLAB"):
            os.environ.pop(k, None)
        self.repo.cleanup()

    def okf(self, *args, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        old_stdin = sys.stdin
        if stdin is not None:
            sys.stdin = io.StringIO(stdin)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = okf.main(list(args))
        finally:
            sys.stdin = old_stdin
        return code, out.getvalue() + err.getvalue()

    def bundle(self, extra=None, config=CONFIG):
        self.repo.write("okf.config", config)
        self.repo.write(".gitattributes", "* text=auto eol=lf\n.okf/** text eol=lf\ninbox/** text eol=lf\n")
        for p, t in {**GOOD, **(extra or {})}.items():
            self.repo.write(p, t)

    def rules(self, out):
        return {line.split()[1] if not line.startswith("FAIL (") else line.split()[2]
                for line in out.splitlines() if line.startswith(("warn ", "FAIL"))}


# --------------------------------------------------------------------------- parser and writer

class ParserTests(unittest.TestCase):
    def test_accepts_subset(self):
        m = okf.parse_yaml(textwrap.dedent("""\
            type: Comms
            title: "Quoted \\"x\\""
            tags: [a, b]
            generated: {by: human:alex, at: 2026-11-12T16:40:00+01:00}
            verified:
              - {by: human:alex, at: 2026-11-12T16:40:00+01:00}
            atb:
              covers: {source: paste:x, count: 3}
              projects:
                - kcm
            """))
        self.assertEqual(m["title"], 'Quoted "x"')
        self.assertEqual(m["generated"]["by"], "human:alex")
        self.assertEqual(m["atb"]["covers"]["count"], "3")
        self.assertEqual(m["atb"]["projects"], ["kcm"])
        self.assertEqual(okf.parse_yaml("x: {trap: CC'd party, n: 'a, b'}")["x"], {"trap": "CC'd party", "n": "a, b"})

    def test_rejections(self):
        bad = ["a: 1 # c", "# c\na: 1", "a: &x 1", "a: |\n  x", "a:\n\tb: 1", "a:\n  b:\n    c:\n      d: 1",
               "l:\n  - a: 1", 'a: "x\\n"', "a: 1\na: 2", "---\na: 1"]
        for text in bad:
            with self.assertRaises(okf.ParseError, msg=text):
                okf.parse_yaml(text)

    def test_writer_keeps_other_lines(self):
        text = "---\ntype: Rule\ntitle:   spaced  \nstatus: draft\natb:\n  topic: commits\n---\nbody\n"
        d = okf.Doc("x.md", text)
        d.set_top("status", "stable")
        d.set_atb("verified_hash", "sha256:abc")
        d.append_verified("human:t", "2026-01-01T00:00:00+00:00")
        out = d.render()
        self.assertIn("title:   spaced  \n", out)
        self.assertIn("status: stable\n", out)
        self.assertIn("  topic: commits\n  verified_hash: sha256:abc\n", out)
        self.assertIn("verified:\n  - {by: human:t, at: 2026-01-01T00:00:00+00:00}", out)
        self.assertTrue(out.endswith("---\nbody\n"))
        okf.parse_yaml("\n".join(okf.split_doc(out)[0]))

    def test_hash_stable_across_encodings(self):
        base = "---\ntype: Rule\ntitle: Café\nstatus: draft\n---\n\nBody line  \n\n"
        h = okf.concept_hash(base)
        self.assertEqual(h, okf.concept_hash("\ufeff" + base.replace("\n", "\r\n")))
        import unicodedata
        self.assertEqual(h, okf.concept_hash(unicodedata.normalize("NFD", base)))
        stamped = base.replace("status: draft", "status: stable\nverified:\n  - {by: human:a, at: 2026-01-01}")
        self.assertEqual(h, okf.concept_hash(stamped))
        self.assertNotEqual(h, okf.concept_hash(base.replace("Body", "Changed")))


# --------------------------------------------------------------------------- regex pack

class RegexTests(unittest.TestCase):
    def kinds(self, line):
        return {k for k, _, _ in okf.scan_line(line)}

    def test_true_and_false(self):
        cases = [
            ("write to a.b@example.org", "email", True), ("no address here", "email", False),
            ("call +41 79 123 45 67", "phone", True), ("call 079 123 45 67", "phone", True),
            ("on 2026-11-12 we met", "phone", False), ("ticket 123456789012", "phone", False),
            ("cost CHF 15'000", "money", True), ("about 15k CHF", "money", True),
            ("15k steps walked", "money", False),
            ("retainer of 20 hours", "hours", True), ("took 20 hours", "hours", False),
            ("arn:aws:iam::123456789012:role/x", "aws-arn", True),
            ("aws account 123456789012", "aws-account", True), ("order 123456789012 shipped", "aws-account", False),
            ("key AKIAABCDEFGHIJKLMNOP", "aws-key", True), ("AKIA short", "aws-key", False),
            ("secret wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "aws-secret", True),
            ("token ghp_abcdefghijklmnopqrstuvwxyz", "token", True), ("ghp_short", "token", False),
            ("eyJhbGciOi.eyJzdWIiOi.SflKxwRJ", "jwt", True), ("eyJ alone", "jwt", False),
            ("-----BEGIN RSA PRIVATE KEY-----", "private-key", True), ("BEGIN KEY", "private-key", False),
            ("postgres://user:pass@host/db", "connection-string", True), ("https://host/db", "connection-string", False),
            ("CH93 0076 2011 6238 5295 7", "iban", True), ("CH93", "iban", False),
        ]
        for line, kind, expected in cases:
            self.assertEqual(kind in self.kinds(line), expected, f"{kind}: {line}")


# --------------------------------------------------------------------------- CLI behaviour

class CliTests(Base):
    def test_no_config_skips(self):
        code, out = self.okf()
        self.assertEqual(code, 0)
        self.assertIn("no okf.config: skipped", out)

    def test_clean_bundle(self):
        self.bundle()
        self.repo.commit("init")
        code, out = self.okf()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.rules(out), set(), out)

    def test_paused(self):
        self.bundle(config=CONFIG.replace("paused: []", 'paused:\n  - {skill: log-comms, reason: "leak found", since: 2026-11-20}'))
        code, out = self.okf("paused", "log-comms")
        self.assertEqual(code, 2)
        self.assertIn("paused: log-comms since 2026-11-20: leak found", out)
        self.assertEqual(self.okf("paused", "end-session")[0], 0)
        self.assertEqual(self.okf("run", "start", "--mode", "log-comms", "--slug", "2026-01-02-x")[0], 2)

    def test_account_check(self):
        import hashlib
        self.bundle(config=CONFIG.replace("SHA", hashlib.sha256(b"me@example.org").hexdigest()))
        code, out = self.okf("account-check", "--alias", "d", stdin='{"data": {"emailAddress": "Me@Example.org"}}')
        self.assertEqual(code, 0, out)
        code, out = self.okf("account-check", "--alias", "d", stdin='{"emailAddress": "other@example.org"}')
        self.assertEqual(code, 2)
        self.assertNotIn("other@", out)

    def test_screen_pre_on_g6(self):
        self.bundle(); self.repo.commit("init")
        code, out = self.okf("run", "start", "--mode", "log-comms", "--slug", "2026-11-10-g6")
        scratch = Path(out.split("scratch: ")[1].split()[0])
        shutil.copy(HERE / "fixtures" / "G6-trap-email.txt", scratch / "source.txt")
        self.assertEqual(self.okf("screen", "--pre", "--run", "2026-11-10-g6")[0], 0)
        stripped = (scratch / "source.txt").read_text()
        self.assertNotIn("surgery", stripped)
        deny = json.loads(okf.run_path("2026-11-10-g6").read_text())["denylist"]
        self.assertIn("Otto Brenner", deny)
        self.assertIn("+41 00 000 00 00", deny)
        self.assertTrue(any(d.startswith("otto.brenner@") for d in deny))
        self.okf("run", "abandon", "2026-11-10-g6")

    def test_screen_post_without_run(self):
        self.bundle()
        self.repo.write("inbox/quick-2026-01-02-x.md", "call +41 79 123 45 67\n")
        self.assertEqual(self.okf("screen", "--post", "inbox/quick-2026-01-02-x.md")[0], 2)
        self.repo.write("inbox/quick-2026-01-02-y.md", "fix the footer\n")
        self.assertEqual(self.okf("screen", "--post", "inbox/quick-2026-01-02-y.md")[0], 0)


class RunTests(Base):
    def start(self, slug="2026-01-02-test", mode="end-session"):
        code, out = self.okf("run", "start", "--mode", mode, "--slug", slug)
        self.assertEqual(code, 0, out)
        return out.split("slug: ")[1].split()[0]

    def test_transitions(self):
        self.bundle(); self.repo.commit("init")
        s = self.start()
        self.assertEqual(self.okf("run", "set", s, "--state", "checked")[0], 2)
        for st in ("screened", "inbox-committed", "drafted", "checked"):
            self.assertEqual(self.okf("run", "set", s, "--state", st)[0], 0, st)
        self.assertEqual(self.okf("run", "set", s, "--state", "stamped")[0], 2)

    def test_slug_clash_and_format(self):
        self.bundle(); self.repo.commit("init")
        self.assertEqual(self.start(), "2026-01-02-test")
        self.assertEqual(self.start(), "2026-01-02-test-2")
        self.assertEqual(self.okf("run", "start", "--mode", "end-session", "--slug", "Bad Slug")[0], 1)

    def test_path_ownership(self):
        self.bundle(); self.repo.commit("init")
        a, b = self.start("2026-01-02-a"), self.start("2026-01-02-b")
        self.assertEqual(self.okf("run", "add-path", a, ".okf/rules/commits.md")[0], 0)
        code, out = self.okf("run", "add-path", b, ".okf/rules/commits.md")
        self.assertEqual(code, 2)
        self.assertIn(a, out)
        self.assertEqual(self.okf("run", "move-path", a, ".okf/rules/commits.md", "--to", b)[0], 0)
        self.assertEqual(self.okf("run", "add-path", b, ".okf/rules/commits.md")[0], 0)

    def test_abandon_restores_unchanged_only(self):
        self.bundle(); self.repo.commit("init")
        s = self.start()
        self.repo.write(".okf/findings/2026-01-02-new.md", "x\n")
        self.repo.write(".okf/rules/commits.md", GOOD[".okf/rules/commits.md"] + "edit\n")
        self.repo.write(".okf/systems/site.md", GOOD[".okf/systems/site.md"] + "edit\n")
        self.okf("run", "add-path", s, ".okf/findings/2026-01-02-new.md", ".okf/rules/commits.md", ".okf/systems/site.md")
        self.repo.write(".okf/systems/site.md", GOOD[".okf/systems/site.md"] + "edit again\n")
        self.assertEqual(self.okf("run", "abandon", s)[0], 0)
        self.assertFalse((self.repo.root / ".okf/findings/2026-01-02-new.md").exists())
        self.assertEqual((self.repo.root / ".okf/rules/commits.md").read_text(), GOOD[".okf/rules/commits.md"])
        self.assertIn("edit again", (self.repo.root / ".okf/systems/site.md").read_text())

    def review_ready(self, slug, paths):
        for st in ("screened", "inbox-committed", "drafted"):
            self.okf("run", "set", slug, "--state", st)
        self.okf("run", "add-path", slug, *paths)
        self.okf("run", "set", slug, "--state", "checked")
        code, out = self.okf("run", "review", slug)
        self.assertEqual(code, 0, out)

    def test_stamp_refuses_changed_blob(self):
        self.bundle(); self.repo.commit("init")
        s = self.start()
        self.review_ready(s, [".okf/rules/commits.md"])
        self.repo.write(".okf/rules/commits.md", GOOD[".okf/rules/commits.md"] + "late edit\n")
        code, out = self.okf("stamp", "--run", s)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(okf.run_path(s).read_text())["state"], "checked")

    def test_stamp_gh_failure_then_resume(self):
        self.bundle(); self.repo.commit("init")
        s = self.start()
        self.review_ready(s, [".okf/rules/commits.md"])
        os.environ["FAKE_GH_LOGIN"] = "-"
        self.assertEqual(self.okf("stamp", "--run", s)[0], 1)
        self.assertEqual(json.loads(okf.run_path(s).read_text())["failed"]["step"], 6)
        del os.environ["FAKE_GH_LOGIN"]
        self.repo.write(f"inbox/{s}.md", "note\n")
        self.repo.commit("inbox", f"inbox/{s}.md")
        code, out = self.okf("run", "resume", s)
        self.assertEqual(code, 0, out)
        r = json.loads(okf.run_path(s).read_text())
        self.assertEqual(r["state"], "done")
        text = (self.repo.root / ".okf/rules/commits.md").read_text()
        self.assertIn("status: stable", text)
        self.assertIn("human:tester", text)
        msg = run_git(self.repo.root, "log", "-1", "--format=%B")
        self.assertIn(f"Knowledge-Run: {s}", msg)
        self.assertIn("Knowledge-Promoted: 1", msg)
        self.assertFalse((self.repo.root / f"inbox/{s}.md").exists())
        code, out = self.okf()
        self.assertNotIn("C8", out)

    def test_migration_review_supersession(self):
        old = GOOD[".okf/decisions/2026-01-02-use-okf.md"].replace(
            '"agent:test/model"', okf.MIGRATION_ACTOR)
        new = old.replace("Use OKF", "OKF v2").replace("We use OKF.", "We use OKF v2.").replace(
            "status: draft", "status: draft\natb:\n  supersedes: 2026-01-02-use-okf.md")
        self.bundle({".okf/decisions/2026-01-03-okf-v2.md": new, ".okf/decisions/2026-01-02-use-okf.md": old})
        self.repo.commit("init")
        code, out = self.okf("run", "start", "--mode", "migration-review", "--folder", "decisions",
                             "--slug", "2026-01-04-migration-decisions")
        self.assertEqual(code, 0, out)
        s = "2026-01-04-migration-decisions"
        self.assertEqual(json.loads(okf.run_path(s).read_text())["state"], "drafted")
        self.okf("run", "set", s, "--state", "checked")
        self.okf("run", "review", s)
        self.assertEqual(self.okf("stamp", "--run", s)[0], 0)
        old_text = (self.repo.root / ".okf/decisions/2026-01-02-use-okf.md").read_text()
        self.assertIn("status: deprecated", old_text)
        self.assertIn("superseded_by: 2026-01-03-okf-v2.md", old_text)
        self.assertNotIn("stable", old_text)
        self.assertIn("status: stable", (self.repo.root / ".okf/decisions/2026-01-03-okf-v2.md").read_text())
        self.okf("carried", "--run", s); self.okf("index", "--run", s)
        self.assertEqual(self.okf("run", "commit", s)[0], 0)
        msg = run_git(self.repo.root, "log", "-1", "--format=%B")
        self.assertIn("Knowledge-Mode: migration", msg)
        self.assertNotIn("Knowledge-Inbox", msg)
        code, out = self.okf()
        self.assertNotIn("C6", out, out)


class CarriedTests(Base):
    def test_ids_unique_and_idempotent(self):
        self.bundle(); self.repo.commit("init")
        with okf.Lock():
            a = okf.append_carried([{"event": "open", "text": "one"}, {"event": "open", "text": "two"}], "2026-01-02-a")
            again = okf.append_carried([{"event": "open", "text": "one"}], "2026-01-02-a")
            b = okf.append_carried([{"event": "open", "text": "three"}, {"event": "close", "id": "C-0001", "text": "done"}], "2026-01-02-b")
        self.assertEqual([e["id"] for e in a], ["C-0001", "C-0002"])
        self.assertEqual(b[0]["id"], "C-0003")
        rows = okf.carried_rows((self.repo.root / "inbox/carried.md").read_text())
        self.assertEqual(len(rows), 4)
        self.assertEqual([i["id"] for i in okf.fold_carried(rows)], ["C-0002", "C-0003"])
        self.assertTrue(again)

    def test_seed_shapes(self):
        self.bundle(); self.repo.commit("init")
        self.repo.write("kcm.md", "| Date | Project | Title | Content | Status |\n|---|---|---|---|---|\n"
                        "| 2026-01-01 | kcm | Fix footer | still open | On Hold — vendor |\n"
                        "| 2026-01-01 | kcm | Old | still open | Done |\n"
                        "| 2026-01-02 | kcm | New thing | x | Open |\n")
        self.repo.write("tb.md", "| Date | Source | Request | Resolution | Status |\n|---|---|---|---|---|\n"
                        "| 2026-01-03 | mail | Send logo | - | needs-follow-up |\n")
        self.assertEqual(self.okf("carried", "--seed", "kcm.md", "--run", "2026-01-05-migration")[0], 0)
        self.assertEqual(self.okf("carried", "--seed", "tb.md", "--run", "2026-01-05-migration-b")[0], 0)
        rows = okf.carried_rows((self.repo.root / "inbox/carried.md").read_text())
        self.assertEqual([r[3] for r in rows], ["Fix footer", "New thing", "Send logo"])
        self.repo.write("bad.md", "| Date | Title |\n|---|---|\n| 2026-01-01 | x |\n")
        self.assertEqual(self.okf("carried", "--seed", "bad.md", "--run", "2026-01-05-migration-c")[0], 1)
        self.repo.write("leak.md", "| Date | Title | Status |\n|---|---|---|\n| 2026-01-01 | mail a@b.org | Open |\n")
        self.assertEqual(self.okf("carried", "--seed", "leak.md", "--run", "2026-01-05-migration-d")[0], 2)


class DebtTests(Base):
    def test_baseline_after_cutover(self):
        self.repo.write("README.md", "x\n"); self.repo.commit("before")
        self.bundle(); self.repo.commit("okf cut-over")
        for i in range(3):
            self.repo.write(f"f{i}.txt", str(i)); self.repo.commit(f"work {i}")
        self.repo.write("g.txt", "x"); self.repo.commit("chore: noise")
        code, out = self.okf("--report", "debt")
        self.assertEqual(code, 0, out)
        self.assertIn("== OKF debt ==", out)
        self.assertIn("5. commits since the last close: 3", out)


class LogAndMigrateTests(Base):
    def test_migrate_maps_fields(self):
        self.bundle()
        self.repo.write("docs/okf-migration-inventory.md",
                        "| old path | outcome | new path |\n|---|---|---|\n"
                        "| memory/reference_site.md | migrated | .okf/systems/site-ref.md |\n"
                        "| memory/feedback_x.md | migrated | .okf/rules/deploy.md |\n")
        self.repo.write(".okf/systems/site-ref.md", "---\nname: Site ref\ndescription: d\ntype: reference\n---\nSee [[feedback_x]].\n")
        self.repo.write(".okf/rules/deploy.md", "---\nname: Deploy\nmetadata:\n  type: feedback\n---\nx\n")
        self.assertEqual(self.okf("migrate", ".okf/systems/site-ref.md", ".okf/rules/deploy.md")[0], 0)
        d = okf.Doc.load(".okf/systems/site-ref.md")
        self.assertEqual((d.meta["type"], d.meta["title"], d.meta["status"]), ("System", "Site ref", "draft"))
        self.assertIn("stale_after", d.meta)
        self.assertEqual(d.meta["generated"]["by"], okf.MIGRATION_ACTOR)
        self.assertIn("[feedback_x](../rules/deploy.md)", d.body)
        r = okf.Doc.load(".okf/rules/deploy.md")
        self.assertNotIn("stale_after", r.meta)
        self.assertNotIn("metadata", r.meta)

    def test_log(self):
        self.bundle(); self.repo.commit("init")
        self.repo.write(".okf/findings/2026-01-05-x.md", "---\ntype: Finding\ntitle: X found\nstatus: draft\n---\nx\n")
        run_git(self.repo.root, "add", "-A")
        run_git(self.repo.root, "commit", "-q", "-m", "knowledge: 2026-01-05-x\n\nKnowledge-Run: 2026-01-05-x")
        self.assertEqual(self.okf("log")[0], 0)
        log = (self.repo.root / ".okf/log.md").read_text()
        self.assertIn("* **Creation**: [X found](findings/2026-01-05-x.md) (knowledge: 2026-01-05-x)", log)


class RuleTests(Base):
    """One rejected input per rule; test_clean_bundle in CliTests is the accepted input for all."""

    def assertRule(self, rule, extra=None, setup=None, expect_code=0):
        self.bundle(extra)
        if setup:
            setup()
        code, out = self.okf()
        self.assertIn(rule, self.rules(out), out)
        self.assertEqual(code, expect_code, out)

    FM = '---\ntype: {t}\ntitle: T\nstatus: draft\ngenerated: {{by: "agent:x/y", at: 2026-01-02T10:00:00+00:00}}\n{extra}---\n{body}\n'

    def c(self, t="System", extra="stale_after: 2099-01-01T00:00:00+00:00\n", body="x"):
        return self.FM.format(t=t, extra=extra, body=body)

    def test_c1(self): self.assertRule("C1", {".okf/systems/a.md": self.c(t="reference")})
    def test_c2(self): self.assertRule("C2", {".okf/systems/a.md": self.c(extra="stale_after: 2099-01-01\nfoo: bar\n")})
    def test_c3(self): self.assertRule("C3", {".okf/systems/a.md": self.c(extra="stale_after: 2099-01-01\natb:\n  topic: x\n")})
    def test_c4(self): self.assertRule("C4", {".okf/systems/a.md": self.c(body="[x](/abs.md) [y](missing.md)")})
    def test_c5(self): self.assertRule("C5", {".okf/systems/Bad_Name.md": self.c()})
    def test_c5_topic(self): self.assertRule("C5", {".okf/rules/unknown.md": self.c(t="Rule", extra="")})

    def test_c6(self):
        def setup():
            self.repo.commit("init")
            self.repo.write(".okf/systems/new.md", self.c().replace("status: draft", "status: stable"))
        self.assertRule("C6", setup=setup)

    def test_c7_c8(self):
        stable = GOOD[".okf/rules/commits.md"].replace("status: draft", "status: stable").replace(
            "  topic: commits", "  topic: commits\n  verified_hash: sha256:0")
        self.assertRule("C7", {".okf/rules/commits.md": stable})
        self.assertIn("C8", self.rules(self.okf()[1]))

    def test_c9(self): self.assertRule("C9", {".okf/systems/a.md": self.c(body="mail me at a.b@example.org")})

    def test_c10(self):
        self.assertRule("C10", setup=lambda: self.repo.write("legacy/new.md", "x"))

    def test_c10_reports_exempt(self):
        self.bundle(); self.repo.write("legacy/reports/r.md", "x")
        self.assertNotIn("C10", self.rules(self.okf()[1]))

    def test_c11(self):
        os.environ["CI"] = "1"
        try:
            self.bundle(); self.repo.commit("init")
            run_git(self.repo.root, "push", "-q", "origin", "main")
            self.repo.write("inbox/2026-01-02-n.md", "note\n")
            self.repo.commit("inbox: n")
            run_git(self.repo.root, "rm", "-q", "inbox/2026-01-02-n.md")
            run_git(self.repo.root, "commit", "-q", "-m", "knowledge: n")
            self.assertNotIn("C11", self.rules(self.okf()[1]))  # added by an earlier commit: accepted
        finally:
            os.environ.pop("CI", None)

    def test_c11_rejects(self):
        self.bundle(); self.repo.commit("init")
        self.repo.write("inbox/2026-01-02-x.md", "staged, never committed\n")
        run_git(self.repo.root, "add", "inbox/2026-01-02-x.md")
        (self.repo.root / "inbox/2026-01-02-x.md").unlink()
        self.assertIn("C11", self.rules(self.okf()[1]))

    def test_c12(self):
        def setup():
            with okf.Lock():
                okf.append_carried([{"event": "open", "text": "a"}, {"event": "open", "text": "b"}], "2026-01-02-a")
            self.repo.commit("init")
            p = self.repo.root / "inbox/carried.md"
            lines = p.read_text().splitlines()
            p.write_text("\n".join(lines[:2] + [lines[3], lines[2]]) + "\n")
        self.assertRule("C12", setup=setup)

    def comms(self, first, last, src="paste:x", body="x"):
        extra = f"atb:\n  direction: in\n  channel: email\n  covers: {{source: {src}, first_at: {first}, last_at: {last}, count: 1}}\n"
        return self.FM.format(t="Comms", extra=extra, body=body)

    def test_c13(self):
        self.assertRule("C13", {".okf/comms/2026-01-01-a.md": self.comms("2026-01-01T00:00:00+00:00", "2026-01-03T00:00:00+00:00"),
                                ".okf/comms/2026-01-02-b.md": self.comms("2026-01-02T00:00:00+00:00", "2026-01-04T00:00:00+00:00")})

    def test_c14(self): self.assertRule("C14", {".okf/comms/2026-01-01-a.md": self.c(t="Comms", extra="")})

    def test_c15(self):
        dep = GOOD[".okf/decisions/2026-01-02-use-okf.md"].replace("status: draft", "status: deprecated")
        self.assertRule("C15", {".okf/decisions/2026-01-02-use-okf.md": dep})

    def test_c16(self): self.assertRule("C16", {"inbox/2020-01-01-old.md": "old note\n"})

    def hook(self, script, timeout=True):
        h = {"type": "command", "command": "bash scripts/hook.sh"}
        if timeout:
            h["timeout"] = 15
        self.repo.write(".claude/settings.json", json.dumps({"hooks": {"SessionStart": [{"matcher": "", "hooks": [h]}]}}))
        self.repo.write("scripts/hook.sh", script)

    def test_c17_accepts_allowed_hook(self):
        self.bundle()
        self.hook("#!/bin/bash\nprintf 'Do not run git pull\\n'\n"
                  "if py -3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then\n"
                  "  py -3 scripts/okf-check.py --report debt || echo 'debt report unavailable: run start-session'\n"
                  "elif python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then\n"
                  "  python3 scripts/okf-check.py --report debt || echo 'debt report unavailable: run start-session'\n"
                  "fi\ngit status --short\n")
        code, out = self.okf()
        self.assertNotIn("C17", self.rules(out), out)
        self.assertEqual(code, 0)

    def test_c17_rejects(self):
        for script, timeout in (("git pull --rebase\n", True), ("python scripts/okf-check.py run resume x\n", True),
                                ('PY=python3\n"$PY" scripts/okf-check.py --report debt\n', True), ("echo hi\n", False)):
            with self.subTest(script=script):
                self.bundle(); self.hook(script, timeout)
                code, out = self.okf()
                self.assertIn("C17", self.rules(out), out)
                self.assertEqual(code, 1)

    def test_c17b(self):
        cfg = CONFIG + "symlinks: forbidden\n"
        self.bundle(config=cfg)
        self.repo.write("CLAUDE.md", "# Agent entry\n\n@AGENTS.md\n")
        self.repo.write(".cursor/rules/okf-core.mdc", '---\ndescription: "OKF agent entry pointer"\nalwaysApply: true\n---\n@AGENTS.md\n')
        code, out = self.okf()
        self.assertNotIn("C17b", self.rules(out), out)
        self.repo.write(".cursorrules", "x")
        self.repo.write("GEMINI.md", "@./.agent/CONTEXT.md\n")
        code, out = self.okf()
        self.assertIn("C17b", self.rules(out))
        self.assertEqual(code, 1)

    def test_c18(self):
        self.bundle(); self.repo.write(".gitattributes", "* text=auto\n")
        self.assertIn("C18", self.rules(self.okf()[1]))

    def test_c19(self):
        self.bundle(); self.repo.write("legacy/reports/w.md", "---\nto: a@example.org\n---\nbody\n")
        self.assertIn("C19", self.rules(self.okf()[1]))

    def test_c20(self):
        stable = GOOD[".okf/decisions/2026-01-02-use-okf.md"].replace("status: draft", "status: stable")
        def setup():
            self.repo.commit("init")
            self.repo.write(".okf/decisions/2026-01-02-use-okf.md", stable.replace("We use OKF.", "We changed it."))
        self.assertRule("C20", {".okf/decisions/2026-01-02-use-okf.md": stable}, setup=setup)

    def test_c21(self):
        person = self.FM.format(t="Person", extra="stale_after: 2099-01-01\natb:\n  role: dev\n", body="x")
        self.bundle({".okf/people/jane-doe.md": person}); self.repo.commit("init")
        code, out = self.okf("run", "start", "--mode", "log-comms", "--slug", "2026-01-02-mail")
        self.repo.write(".okf/people/jane-doe.md", person.replace("title: T", "title: Changed"))
        self.okf("run", "add-path", "2026-01-02-mail", ".okf/people/jane-doe.md")
        code, out = self.okf("--run", "2026-01-02-mail")
        self.assertIn("C21", self.rules(out), out)

    def test_c22(self): self.assertRule("C22", {".okf/systems/a.md": self.c(extra="")})

    def test_c23(self):
        quote = '"' + " ".join(["word"] * 30) + '"'
        self.assertRule("C23", {".okf/comms/2026-01-01-a.md": self.comms("2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00", body=quote)})

    def test_c24(self):
        self.bundle(config=CONFIG.replace("key: TST", "key: <KEY>"))
        self.assertIn("C24", self.rules(self.okf()[1]))


if __name__ == "__main__":
    unittest.main()
