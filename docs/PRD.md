# PRD: parity-controls as a product

**Status:** draft for the owner, 2026-10-20. **Scope:** the open-source package (PyPI, CI action,
dbt / Great Expectations adapters) and a paid "write-boundary audit" service built on it.

Grounding rule for this document: every statement about what the software does is checked
against the code in this repo at the commit that adds this file. Anything else is labelled
**[ASSUMPTION]** or **[HYPOTHESIS]**. There are no customers, users, download counts or revenue
yet, and this document does not imply otherwise.

## 1. Problem

A pipeline can lose or corrupt data at the moment it writes, and still report success. The
repo's own case study (`docs/INCIDENT-0047.md`) is one instance, measured on the maintainer's
pipeline: a field-name typo read with a default collapsed ~2.67M rows of dimensional data
(stored 4,744,661, 7,418,574 once repaired) with no exception, no log line and no failed run.

The common checks do not see this class of fault. The repo proves one of them cannot:
`rows vs COUNT(DISTINCT key)` is equal *by construction* under `INSERT OR REPLACE`
(`test_key_parity_cannot_see_collapse` in `test_parity.py`).

## 2. What exists today (from the code)

| Piece | Where | State |
|---|---|---|
| `offered_present_parity` - key-set comparison at the write boundary | `parity.py` | built, fault-tested |
| `cross_field` - two columns that describe one fact must agree | `parity.py` | built, fault-tested; string-domain substring bug fixed in this change |
| `share_anomaly` - near-constant value in a multi-valued column (WARN only) | `parity.py` | built, heuristic by design |
| `canonical_hash` / `verify_canonical` - order-independent, float-stable digest | `parity.py` | built, adversarially reviewed four times (README) |
| Fault injectors + fault matrix | `faults.py`, `test_parity.py` | every raising control is shown to fire |
| Mutation-style audit of the tests | `tools/audit_tests.py` | built |
| CSV write-gate example | `examples/csv_position_book_gate.py` | built |
| Freeze/verify lockfile CLI (`parity-controls`) | `parity_integrations/lockfile.py` | **new**, tested |
| GitHub Action | `action.yml` | **new**, exercised in CI incl. a required refusal |
| dbt adapter | `parity_integrations/dbt.py` | **skeleton**: seed freeze/verify works; relation parity is a stub |
| Great Expectations adapter | `parity_integrations/great_expectations.py` | **skeleton**: GX-shaped result dicts work; registration is a stub |
| Packaging | `pyproject.toml` | installable wheel; distribution renamed `parity-controls`; **not published** |

Performance, as the README quotes it (one core, `bench.py`, 2026-09-18): 1,000,000 rows - set
parity 0.16s, `canonical_hash` 6.17s, peak RSS 737 MB (upper bound, includes building the list).

## 3. Target users

**[ASSUMPTION]** - inferred from what the controls do and the README's "Where this is meant to be
used"; none of these segments has been interviewed.

1. **Data / analytics engineers at fintechs and asset managers** running dbt or Python ETL into a
   warehouse, where a silent row loss is a wrong balance or mark, not a missing chart.
2. **Quant / risk engineers** reconciling a position book or NAV against its source.
3. **Finance & audit stakeholders** (controllers, auditors, investors' diligence) who need
   evidence that a control exists and has been seen to fire.

## 4. Jobs to be done

- *When a pipeline writes a batch, I want it to refuse a write that lost, renamed or substituted
  keys, so a wrong book never lands as a green run.*
- *When someone refactors a model or reference data, I want CI to prove the data did not move
  (or show exactly which file did), so review is about intent, not trust.*
- *When an auditor asks "how do you know this load was complete?", I want to hand over a control
  that is shown failing on an injected fault, not a sentence.*

## 5. Goals and non-goals

**Goals (next 90 days, see `docs/ROADMAP.md`)**

- G1. `pip install parity-controls` works from PyPI, import name `parity` unchanged.
- G2. A team can add the GitHub Action and get a refusal on moved CSV data in under 10 minutes
  **[HYPOTHESIS: target, unmeasured]**.
- G3. dbt and Great Expectations users can run at least one parity control inside their existing
  tool without leaving it.
- G4. A packaged, priced write-boundary audit offering that the owner can sell and deliver.

**Non-goals**

- No hosted SaaS, dashboard or data storage. The core stays a library; evidence stays in the
  customer's repo and CI.
- No runtime dependency in the core (`dependencies = []` is a public claim; CONTRIBUTING enforces it).
- Not a general data-quality suite. Null checks, ranges, freshness belong to dbt tests / GX; this
  product covers the write boundary and "did the data move" only.
- No claim of production defects caught at a customer: there are none to cite (README says
  "unproven in production" beyond the maintainer's own pipeline).

## 6. User stories and acceptance criteria

**US1 - install.** As a Python user I install the package by its PyPI name.
- AC: `pip install parity-controls` then `import parity` succeeds on 3.10-3.12 with no other
  package installed. *Verified locally from a built wheel in a clean venv; PyPI upload pending.*
- AC: `import parity` imports nothing from `parity_integrations`, dbt or GX (pinned by
  `test_importing_parity_pulls_in_no_integration`).

**US2 - CI freeze/verify.** As a data engineer I gate a PR on committed CSV data not moving.
- AC: `verify` exits 1 and names each added/removed/renamed/changed file; exits 0 when only row or
  column order changed. (`tests/test_integrations.py`)
- AC: duplicated headers and ragged rows are refused by name, not collapsed.
- AC: the action's own CI job freezes, verifies, mutates a cell and requires `result=violation`.

**US3 - dbt.** As a dbt user I protect seeds today and model key sets later.
- AC (built): `freeze_seeds` / `verify_seeds` work with no dbt installed.
- AC (not built): `relation_key_parity(project, offered, present, key)` raises `ParityViolation`
  naming missing/unwanted keys across two relations. Today: `MissingDependency` without dbt,
  `NotImplementedError` with it.

**US4 - Great Expectations.** As a GX user I route parity results like GX results.
- AC (built): `expect_*` functions return `{"success", "expectation_type", "result"}`; a violation
  is `success: False` with the mechanism-naming message; caller misuse still raises `TypeError`.
- AC (not built): the controls register as GX custom Expectations usable in a suite.

**US5 - audit buyer.** As a head of data at a fintech I buy a fixed-scope audit of my write
boundaries and receive controls wired into my CI that are shown to fire. (Section 9.)

## 7. Requirements

**Functional**

- F1. Distribution `parity-controls`, import `parity`, console script `parity-controls`. *(done)*
- F2. Extras `[dbt]`, `[great-expectations]`, `[dev]`; adapters import lazily and raise
  `MissingDependency` naming the extra. *(done)*
- F3. Lockfile format v1: `{"version", "pattern", "files": {relpath: {digest, rows, columns}}}`;
  readers refuse unknown versions. *(done)*
- F4. Composite action with inputs `mode/path/lockfile/pattern/python`, output `result`. *(done)*
- F5. `relation_key_parity` for dbt; GX Expectation registration. *(roadmap: Next)*
- F6. Parquet input for the lockfile. *(roadmap: Later; would need an optional dependency)*

**Non-functional**

- N1. Core stays stdlib-only and readable in one sitting.
- N2. Every raising control has a fault that makes it fire, and CI fails if it goes quiet.
- N3. Stubs raise `NotImplementedError` pointing at the roadmap; nothing returns a fake pass.
- N4. Python 3.10+ (CI runs 3.10 and 3.12).
- N5. Lockfile verify is whole-file in memory today; documented as a blind spot.

## 8. Success metrics

No baselines exist; every target below is a **[HYPOTHESIS]** to be replaced by a measured number.

| Metric | Source | First target |
|---|---|---|
| PyPI downloads / month (excluding mirrors) | pypistats | set after 30 days of data |
| Public repos using `jmiaie/parity-controls` action | GitHub code search | 5 in 90 days **[HYPOTHESIS]** |
| Issues from people other than the maintainer | GitHub | any |
| Audit discovery calls | owner's CRM | 5 in 90 days **[HYPOTHESIS]** |
| Paid audits delivered | invoices | 1 in 90 days **[HYPOTHESIS]** |

## 9. Paid offering: write-boundary audit

**Positioning.** Open-source controls, paid installation-and-proof. The library is free; what is
sold is the work of finding a customer's write boundaries, wiring the controls in, and **showing
each one fail on an injected fault in their environment**, which is the evidence an auditor or
investor can use. This mirrors the repo's own discipline: "a control that has never been observed
to fail is not a control".

**Scope (per engagement)** - **[ASSUMPTION]** sized for one pipeline / one warehouse:

1. Inventory: list every place data is written (loads, merges, upserts, file drops) for the agreed
   pipeline(s), and the natural key at each.
2. Risk rank: which boundaries can lose or substitute keys silently (keyed upserts, defaulted field
   reads, filters spanning the check), using the blind-spot list from `parity.py` docstrings.
3. Wire: `offered_present_parity` at the top N boundaries, `cross_field` where two columns encode
   one fact, `canonical_hash` lockfiles on reference data / seeds, the action in CI.
4. Prove: inject a fault per control (pattern: `faults.py`, `tests/test_alarm_offline.py`) and
   record the refusal message and that the prior good data survived.
5. Hand over: runbook and a re-runnable fault test so the proof can be repeated.

**Deliverables**

- Write-boundary inventory and risk ranking (document).
- A PR to the customer's repo with the controls, lockfiles and CI workflow.
- A fault-injection evidence pack: per control, the fault, the refusal text, the timestamp.
- 30-day follow-up call **[ASSUMPTION]**.

**Out of scope:** remediation of defects found (quoted separately), warehouse migration, ongoing
monitoring/on-call, legal or SOX attestation (the evidence pack supports an auditor; it is not one).

**Pricing hypotheses** - all **[HYPOTHESIS]**, untested with any buyer; validate in discovery calls
before publishing any number:

| Package | What | Price hypothesis |
|---|---|---|
| Diagnostic | inventory + risk ranking only, ~2-3 days | USD 3k-5k fixed |
| Audit | full scope above, one pipeline, ~1-2 weeks | USD 12k-20k fixed |
| Retainer | quarterly re-proof + new boundaries | USD 1.5k-3k / month |

Hypotheses to test: (a) buyers pay fixed-fee for evidence rather than day-rate for engineering;
(b) the trigger is an upcoming audit, fundraise diligence or a recent silent-data incident;
(c) dbt-heavy teams are reachable via the dbt adapter and action users.

## 10. Risks

- **Credibility gap:** no third-party production use yet. Mitigation: lead with the reproducible
  fault matrix and incident write-up, not claims.
- **Name confusion:** distribution `parity-controls` vs import `parity` vs an unrelated PyPI
  project `parity`. Mitigation: install section states it; an import collision is possible if a
  user installs both.
- **Skeleton adapters read as features.** Mitigation: they raise `NotImplementedError`, and docs
  label them skeletons.
- **Lockfile trust:** data and lockfile changed in one commit pass verify. Mitigation: documented;
  recommend CODEOWNERS on lockfiles.
- **Single maintainer** for both the library and the service (CONTRIBUTING: one person, best effort).
- **Scale:** `canonical_hash` is in-memory; multi-GB files need streaming (Later).
- **Public/private split:** fixes land privately first (`docs/POSITIONING.md`); a public product
  needs a sync policy so PyPI releases are not behind.

## 11. Open questions for the owner

1. Publish to PyPI under `parity-controls` now, and as which version (0.3.0 or 0.4.0)?
2. Who owns the PyPI project (personal account vs Micap AI LLC org), and use Trusted Publishing?
3. Enable ruff in CI? It is in the dev extra but unconfigured, and the default rules flag 9 issues
   in existing files.
4. Tag a release (`v0.4.0`) so the action can be referenced by tag rather than SHA, and list it on
   the GitHub Marketplace?
5. Is the audit sold by Micap AI LLC, and are the pricing hypotheses in the right range for your
   market?
6. Should `cross_field` accept a bare string as a one-value domain instead of refusing it? This
   change refuses (consistent with `offered_present_parity`); accepting is friendlier but implicit.
7. Which private-line fixes need to sync before a first public release?
