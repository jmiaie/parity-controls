# Contributing

`parity` is a one-person portfolio/research project: one maintainer, no contributors yet.
Read this as a description of how the repo actually works, not as the process of a large
open-source project it is not trying to be.

## Ground rules

- **Python 3.10+** and **no third-party dependencies** — runtime or test. The library
  imports only `collections`, `hashlib` and `math`. A pull request that adds a runtime
  dependency will be rejected: zero dependencies is a claim the README makes and the
  packaging enforces (`dependencies = []` in `pyproject.toml`).
- **The core checks are plain scripts**, not a test framework: `test_parity.py` and `demo.py`
  run with no install. `tests/` is collected by `pytest` (the `dev` extra), which CI also runs;
  the adapter tests there skip when dbt / Great Expectations are not installed.
- **Integrations stay outside the core.** `parity_integrations/` holds the lockfile CLI and the
  dbt / Great Expectations adapters. They may use optional extras, imported lazily, and must
  raise `MissingDependency` naming the extra; `import parity` must never import them.
- **A control that has never been observed to fail is not a control.** This is the project's
  core discipline and the bar every change is held to (see *Adding a control*).
- **A document that overclaims is the failure this repo exists to name.** If your change
  alters behaviour covered by a *Known blind spots* entry in `README.md`, or by a caveat in a
  function docstring, update that text in the same change.

## Run the checks

All of these run from a checkout with no install required (`pip install -e .` is optional
and only exercises the packaging):

| command | what it proves |
|---|---|
| `python3 test_parity.py` | The fault matrix: every control fires on the fault it must catch and stays silent on healthy data, plus the executable negative result — `rows vs COUNT(DISTINCT key)` cannot see a collapse. |
| `python3 demo.py` | The failure in dollars: 97 rows vanish silently and the position book is off by 22.7%. |
| `python3 bench.py` | The load numbers the README quotes — 100,000 rows by default, `python3 bench.py 1000000` for the million-row run — so they can be argued with rather than trusted. |
| `python3 tests/test_alarm_offline.py` | The alarm, not just the check: an injected collapse is refused at the real write boundary, by a refusal that names the mechanism. |

Run them all before pushing. `tests/test_alarm_offline.py` stages the adapter into a scratch
tree and drives real processes, so it is the slow one; the others are seconds.

## Adding a control

A control is not complete until it can be seen failing:

1. Add it to `parity.py`, with a docstring that states its **blind spots** — on the
   function, not in a separate document.
2. Add a fault to `faults.py` that this control must catch.
3. Wire that fault into the matrix in `test_parity.py`, and confirm the matrix **fails**
   when the control is disabled: a control that never goes red on its own fault is
   decoration.
4. Keep it **silent when healthy**, and make it **name the mechanism** when it fires. An
   alert that lists possibilities gets muted, and a muted control is worse than no control.
5. If you also found a defect in an existing control, reproduce it **before** the fix and
   pin it with a test after, the way the adversarial-probe findings in `README.md` are
   pinned. Bring the reproduction, not an argument about the fix.

Keep the honest statuses honest: `share_anomaly` is a heuristic and WARN-only for that
reason, and its threshold must be calibrated from the mechanism — what fraction of rows can
legitimately share a value — never from the incident that motivated it.

## Style

- **stdlib only**, as above.
- **Type hints on public functions.** The module uses `from __future__ import annotations`,
  so `str | None` is fine on 3.10.
- Docstrings carry the *why* and the *limits*; brief is good, vague is not, and a caveat
  belongs next to the code it constrains. The house style prefers a measured claim with its
  measurement quoted ("8,411 rows over 3 wallets carried 0 repeated keys") to a confident
  claim without one.
- Keep diffs small and purposeful. This repo is short on purpose — it is meant to be
  readable in one sitting, which is a property a large change can break.

## CI is live

`.github/workflows/ci.yml` runs on every push and pull request on this public repo: the fault
matrix and the demo as plain scripts, then `pytest` over `tests/` after installing the package
with its dev extra, on Python 3.10 and 3.12; and a second job that runs `action.yml` against
`tests/fixtures/books` and requires it to **refuse** a mutated file.

History: the private sibling line parked the same workflow (`ci.yml.disabled`) when its Actions
minutes ran out, on the principle that **a check that fails on every commit trains its owner to
ignore red**. That principle still holds here: if CI goes red for a reason that is not the code,
fix or park it explicitly rather than leaving it red. Run `make check` and `make pytest` locally
before pushing either way.

## Reporting, licensing, review

- **Security problems: privately**, via GitHub's Security tab — see `SECURITY.md`. Never a
  public issue.
- **Conduct**: see `CODE_OF_CONDUCT.md`.
- **Licensing**: contributions are accepted under the MIT license in `LICENSE` (copyright
  Micap AI LLC), the terms the project already ships under. There is no CLA.
- **Review**: one maintainer, best effort. Expect a considered answer rather than a fast
  one, and expect the answer to be about the artifact.
