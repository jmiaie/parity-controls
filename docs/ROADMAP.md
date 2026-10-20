# Roadmap

Companion to [`docs/PRD.md`](PRD.md). Current state of the repo: [`STATUS.md`](../STATUS.md);
public/private split: [`docs/POSITIONING.md`](POSITIONING.md). This file does not override either;
where they disagree, STATUS wins and this file should be corrected.

Phases are Now (0-30 days), Next (30-60), Later (60-90+). An item is done when its exit criteria
are met **and** CI shows the relevant control refusing on an injected fault.

## Now (0-30 days)

| Item | Deliverable | Exit criteria | Depends on |
|---|---|---|---|
| Distribution rename | `name = "parity-controls"` | wheel builds; clean-venv `import parity` works *(done in this branch)* | - |
| CI consistent with reality | `ci.yml`, Makefile, dependabot, CONTRIBUTING say "live"; pytest runs `tests/` | CI green on 3.10 and 3.12 *(this branch)* | - |
| `cross_field` string-domain fix | `TypeError` on `str`/`bytes` domain | regression test fails on the old module *(done; verified)* | - |
| Freeze/verify CLI | `parity_integrations/lockfile.py`, `parity-controls` script | tests for move/rename/ragged/dup-header *(done)* | - |
| GitHub Action | `action.yml`, `docs/github-action.md` | CI job requires a refusal on a mutated fixture *(this branch)* | - |
| Adapter skeletons | `parity_integrations/dbt.py`, `great_expectations.py`, extras | missing-dependency path tested; stubs raise `NotImplementedError` *(done)* | - |
| PyPI publish | 0.4.0 on PyPI | `pip install parity-controls` from PyPI in a clean venv | owner: PyPI account, version (PRD Q1-Q2) |
| Release tag | `v0.4.0` | action usable as `@v0.4.0` | PyPI publish |

## Next (30-60 days)

| Item | Deliverable | Exit criteria | Depends on |
|---|---|---|---|
| dbt adapter - relation_key_parity | query distinct keys of two relations through `dbtRunner`, compare with `offered_present_parity` | test against a DuckDB-backed dbt project in CI (extra job installing `[dbt]` + `dbt-duckdb`) shows a refusal on a dropped key | dbt API choice; CI time |
| Great Expectations adapter - register_expectations | GX custom Expectations wrapping the controls | a GX suite with the expectation fails on an injected fault in CI | GX 1.x API review |
| Audit offering v1 | one-page service sheet, SOW template, evidence-pack template from PRD section 9 | owner approves scope and pricing range | PRD Q5 |
| Discovery | 5 conversations with target users | pricing hypotheses kept/changed with notes | service sheet |
| ruff | `[tool.ruff]` config and CI step | CI green with ruff | PRD Q3 |

## Later (60-90+ days)

| Item | Deliverable | Exit criteria | Depends on |
|---|---|---|---|
| Streaming lockfile digests | hash large files without loading all rows | 1M-row CSV verify under a stated memory bound, measured by `bench.py` | design: digest must stay order-independent |
| Parquet input | optional `[parquet]` extra | same tests as CSV | dependency choice |
| Action job summary | markdown table of files/digests in `$GITHUB_STEP_SUMMARY` | visible in CI | - |
| First paid audit | delivered evidence pack | invoice + customer permission to cite (or not) | discovery |
| Public/private sync policy | documented in POSITIONING | releases not behind the private line | owner |
