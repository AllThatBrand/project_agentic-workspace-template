#!/usr/bin/env python3
# okf-tooling: 0.1.0
"""Compare a golden-test run file with its expected output (design item 33, spec 10.1).

Usage: python tests/okf/golden.py <Gn> <run-file>

Expected files: ~/okf-fixtures/expected/Gn.yaml, except G6 at tests/okf/fixtures/expected/G6.yaml.
Compares what a script can check (paths, types, refusal categories, flag kinds, states) and prints a
manual checklist for judgment items. Model wording is never compared. Exit 0 pass, 2 mismatch, 1 error.
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("okf_check", HERE.parents[1] / "scripts" / "okf-check.py")
okf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(okf)


def expected_path(test: str) -> Path:
    if test == "G6":
        return HERE / "fixtures" / "expected" / "G6.yaml"
    return Path.home() / "okf-fixtures" / "expected" / f"{test}.yaml"


def bundle_rel(path: str) -> str:
    return path[len(".okf/"):] if path.startswith(".okf/") else path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1
    test, run_file = argv
    exp_file = expected_path(test)
    if not exp_file.exists():
        print(f"error: no expected file {exp_file}")
        return 1
    exp = okf.parse_yaml(okf.read_text(exp_file))
    run = json.loads(Path(run_file).read_text(encoding="utf-8"))
    problems = []

    accepted = {bundle_rel(a["path"]) for a in run.get("review", {}).get("accepted", [])}
    accepted |= {bundle_rel(p) for p in run.get("paths", {})}
    want = {i["path"]: i.get("type") for i in exp.get("review_items", []) if isinstance(i, dict)}
    for path in sorted(set(want) - accepted):
        problems.append(f"missing review item: {path}")
    for path in sorted(accepted - set(want)):
        problems.append(f"unexpected review item: {path}")
    for path, typ in want.items():
        cand = Path.cwd() / ".okf" / path
        if cand.exists():
            got = okf.Doc(path, okf.read_text(cand)).meta.get("type")
            if typ and got != typ:
                problems.append(f"{path}: type {got}, expected {typ}")

    got_ref = sorted(r["category"] for r in run.get("refusals", []))
    want_ref = sorted(exp.get("refusals", []))
    for cat in sorted(set(want_ref) - set(got_ref)):
        problems.append(f"missing refusal category: {cat}")
    for cat in sorted(set(got_ref) - set(want_ref)):
        problems.append(f"unexpected refusal category: {cat}")

    got_flags = sorted({f["kind"] for f in run.get("flags", [])})
    want_flags = sorted(exp.get("flag_kinds", []))
    if got_flags != want_flags:
        problems.append(f"flag kinds {got_flags}, expected {want_flags}")

    states = exp.get("states", [])
    if states and run.get("state") not in states:
        problems.append(f"state {run.get('state')}, expected one of {states}")

    items = len(want)
    print(f"{test}: {items} review items, {len(got_ref)} refusals, flags {got_flags}, state {run.get('state')}")
    for p in problems:
        print(f"  MISMATCH {p}")
    print("Manual checklist (sign in the test log):")
    for c in exp.get("carried", []):
        print(f"  [ ] carried item present: {c}")
    for t in exp.get("traps", []):
        if isinstance(t, dict):
            print(f"  [ ] {t.get('trap')} — {t.get('control')}: {t.get('check')}")
    print("  [ ] review screen matched spec 4.5; no model wording judged here")
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
