# Tests (tooling only)

`tests/` belongs to the OKF tooling in this template. It is **not copied** into client repos:
pilots copy `scripts/okf-check.py`, `scripts/okf_validate.py`, the skills and
`.github/workflows/okf.yml` only.

## Unit tests

```bash
python -m unittest discover -s tests/okf -t .
```

Python 3.11 or later, standard library only. Each test builds a temporary git repo with a local
bare `origin` (`…/test/test.git`) and a fake `gh` first on `PATH` (`gh.cmd` on Windows), so no
network or GitHub login is needed. CI runs the same command on ubuntu and windows (job `unit` in
`.github/workflows/okf.yml`).

Lint locally (not a CI dependency): `python -m pyflakes scripts/okf-check.py tests/okf`.

## Golden tests (phase 0)

G1-G10 (spec §10) run by hand in the throwaway `okf-sandbox` repo, never in this template or a
client repo. Real kcm fixtures live outside git in `~/okf-fixtures/`; the synthetic G6 email and its
expected output live here in `tests/okf/fixtures/`.

After a run, compare its run file with the expected output:

```bash
python tests/okf/golden.py G6 "$(git rev-parse --git-common-dir)/okf/run-<slug>.json"
```

Exit 0 means every scripted check matched; the printed checklist covers judgment items, which
are signed in the test log.
