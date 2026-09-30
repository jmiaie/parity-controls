# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `examples/csv_position_book_gate.py` — stdlib CSV position-book write gate (refuse drift / missing
  key; protect prior book; freeze-digest durable CSV-shaped cells).

### Fixed

- `pip install` failed at 0.3.0: `pyproject.toml` carried both `license = "MIT"` and the superseded
  classifier `License :: OSI Approved :: MIT License`, which `setuptools>=77` rejects as
  `InvalidConfigError`. Classifier removed.
- `canonical_hash` refused cells whose `str()` carries a memory address (`object()`, `memoryview`,
  …) — previously a false "canonical hash moved" alarm across processes. Pinned in `test_parity.py`
  section 1l.
- `tests/test_alarm_offline.py` defaults `PARITY_DIR` to this checkout (env still overrides).

### Changed

- README: CI callout matches reality (live on this public companion); fault-matrix count and
  `python3 demo.py` corrected; cross-link to private hardening line; layout includes the CSV example.
- `SECURITY.md` current line is **0.3.x**.
- `docs/INCIDENT-0047.md` / `share_anomaly` docstring: pre-fix share `0.999947` is **over** the
  `0.999` trigger, not under.


## [0.3.0] - 2026-09-18

### Added

- `share_anomaly` gained a `min_empty_share` threshold (default `0.5`) and a new
  `MOSTLY EMPTY` message, so a partially-empty column is no longer reported as
  `UNPOPULATED` ("nothing wrote this column"). That claim is only made when the modal
  value is empty at `max_share` or more; between the two thresholds the column is named
  as `MOSTLY EMPTY`, and below `min_empty_share` it stays silent.
- `py.typed` at the repo root (PEP 561 marker, empty by design) so a type checker treats
  the installed module as typed.
- `MANIFEST.in`, so the sdist ships the honesty-critical files — the marker, the licence,
  the docs, the demos, the fault injectors and the tests — rather than `parity.py` alone.
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`.
- `.editorconfig`, `.gitattributes`, and a `Makefile` for the common commands.
- `examples/quickstart.py`.
- `.github/ISSUE_TEMPLATE/` (bug report and feature request), `.github/PULL_REQUEST_TEMPLATE.md`,
  `.github/dependabot.yml`.

### Changed

- Version bumped to 0.3.0, kept in sync between `parity.py`'s `__version__` and the
  `pyproject.toml` `[project]` table.
- Docstring corrections. The blind-spots list on `offered_present_parity` actually contains
  **five** entries, not four, and the module claim that "every function ships with a fault"
  is now scoped to the RAISING controls, since `share_anomaly` is WARN-only by design and
  never raises.
- CI remains parked as `.github/workflows/ci.yml.disabled` pending Actions minutes on a
  private repo; the gate keeps running where the push happens instead.

### Fixed

- **Landed from the owner's third review of the same day (independent of this change):** a
  container-valued cell (`dict`/`list`/`set`/`bytes`) is refused by name instead of being hashed
  as its own `repr` — a set cell previously produced different digests across `PYTHONHASHSEED`
  values, and a digest that varies by process is not a record of the data. A non-`str` column name
  is refused for the same reason (`{1: "x"}` used to hash like `{"1": "x"}`), mixed key types
  no longer abort the hash inside `sorted()` with an interpreter error, `offered_present_parity`
  no longer treats a `bool` as a count (`True` vs `1` passed), and a row carrying no columns at all
  is refused so that it cannot digest to the empty-input digest.
- `canonical_hash` now renders a column ABSENT from a row as a distinct sentinel (new
  `_ABSENT` constant) instead of the same empty cell, so a missing column can no longer
  hash like an empty one. Previously `r.get(c)` made the two cases identical on the very
  write path this library exists to protect — the module failing its own
  `.get(key, default)` test. The sentinel is NUL-tagged and `_esc` guarantees no real value
  can contain a raw NUL, so it cannot be forged by input; with `columns=None` every column
  is present by construction and existing digests are unchanged.
