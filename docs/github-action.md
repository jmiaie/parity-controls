# GitHub Action: freeze and verify CSV digests

`action.yml` at the repo root is a composite action. It runs
`python3 -m parity_integrations.lockfile` straight from the action's own checkout: no `pip
install`, no third-party dependency, the runner's `python3` (3.10+).

## What it checks

`freeze` writes a lockfile with one entry per CSV file under `path`: the `canonical_hash`
digest of its rows (cells as text, row order and column order ignored), plus the row count and
header for a human reading the diff.

`verify` re-digests and **refuses** the job (exit 1, `result=violation`) when:

- a locked file is missing, or a new file appears (compared as key sets with
  `offered_present_parity`, so a rename names both the file that never landed and the one that
  arrived unwanted);
- a file's digest moved (a changed cell, an added or dropped row);
- a file has a duplicated header name or a ragged row - the shapes `csv.DictReader` collapses
  silently.

It names **every** problem in one run, not the first.

## Usage

Verify committed data against a committed lockfile:

```yaml
jobs:
  data-integrity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: jmiaie/parity-controls@<commit-sha>   # pin a SHA; no release tag exists yet
        with:
          path: data/seeds
          lockfile: data/parity.lock.json
```

Create or refresh the lockfile locally, and commit it **in its own reviewed change**:

```bash
pip install git+https://github.com/jmiaie/parity-controls
parity-controls freeze data/seeds --lock data/parity.lock.json
```

### Inputs

| input | default | meaning |
|---|---|---|
| `mode` | `verify` | `verify` or `freeze` |
| `path` | (required) | a CSV file, or a directory searched recursively |
| `lockfile` | `parity.lock.json` | lockfile path, relative to the workspace |
| `pattern` | `*.csv` | glob under a directory; `freeze` only (`verify` reads it from the lockfile) |
| `python` | `python3` | interpreter; run `actions/setup-python` first if the runner's is older than 3.10 |
| `fail-on-violation` | `true` | `false` reports a violation in `result` without failing the step |

### Outputs

| output | values |
|---|---|
| `result` | `frozen`, `verified`, `violation` (unset on a usage error, exit 2) |

GitHub does not set a composite action's outputs when the action fails, so with the default
`fail-on-violation: true` a failed run's `result` is empty; set it to `false` to branch on it.

## Blind spots

- **A lockfile rewritten in the same commit as the data passes.** The action proves the data
  matches the lockfile, not that the lockfile is right. Require review on lockfile changes
  (CODEOWNERS is the cheap way).
- **Cells are text.** `1.0` and `1.00` are different files. This checks the durable artifact.
- **Whole-file in memory.** Fine for seeds, reference data and fixtures; not yet sized for
  multi-GB extracts (docs/ROADMAP.md, Later).
- **CSV only, UTF-8 only** today.

## Proof it refuses

`.github/workflows/ci.yml`, job `action`, runs this action on `tests/fixtures/books`: freeze,
verify, mutate one cell, then requires verify to fail the step by default and to report
`result=violation` with `fail-on-violation: false`.
