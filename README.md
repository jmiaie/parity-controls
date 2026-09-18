# parity

**Write-boundary integrity for financial data and AI pipelines.** Four controls, each one
required to prove itself against a fault it must catch — because a control that has never
been observed to fail is not a control.

A field-name typo read with a default silently collapsed **2,673,913 rows** of dimensional
data on a live pipeline. No exception, no log line, no failed run. The position book was
wrong, and every dashboard was green. Case study: [`docs/INCIDENT-0047.md`](docs/INCIDENT-0047.md).

## Run it

```bash
python3 test_parity.py   # the fault matrix: every control must fire on its fault, stay silent when healthy
python3 demo.py          # the money: 97 rows vanish and the book is off by 22.7%
```

No dependencies. Python 3.10+. 356 lines total.

## What the demo prints

```
batch from the source API:         248 rows
rows the table holds, healthy:     248
rows the table holds, collapsed:   151   <- 97 rows gone, silently

position value, correct            30,128.74
position value, collapsed          23,292.69
error carried to the book          -6,836.05   (-22.7%)

  write-boundary parity: FIRED - offered=248 present=151 delta=-97
  rows vs distinct-key  : silent  <- a control that cannot see this is decoration
  cross-field index<->label: FIRED - 123 rows contradict their declared domain
```

## The four controls, in the order they earn their place

| # | control | catches | cost |
|---|---|---|---|
| 1 | `offered_present_parity` | field collapse, field rename, truncation, duplication | one integer compare |
| 2 | `cross_field` | a column forced to a default while its sibling still holds the truth | one pass |
| 3 | `share_anomaly` | a declared multi-valued column gone degenerate, **and** an unpopulated column (different messages) | one pass |
| 4 | `canonical_hash` | "the data did not move" — around any repair or rebuild | one pass |

1 and 2 are arithmetic. 3 is a heuristic and it says so, including its measured blind spot
on the function itself: a real orphan family sat at max-share `0.9911` and slipped under a
`0.999` trigger. Calibrate that threshold from the mechanism — what fraction of rows can
legitimately share a value — never from the incident that motivated it.

## Rejected on purpose

`rows vs COUNT(DISTINCT key)` as a collapse detector. Where the natural key is the primary
key, `INSERT OR REPLACE` erases the violation at write time, so the two counts are equal
**by construction** and the check cannot disagree with itself. In the fault matrix it is
silent on collapse, silent on rename, silent on truncation, and fires only on the unkeyed
duplicate — the one case a keyed table cannot produce. That negative result is executable:
`test_parity.py` section 2.

## What is proven, and what is not

**Proven** (reproduce both commands): the fault matrix passes 22/22 — every control fires on
collapse, rename, truncation and duplication, and the healthy control leaves all of them
silent; the demo's 22.7% book error; order-independence and float-stability of the hash.

**Not proven:** any load beyond a few hundred rows in one process; no concurrency claim; no
adapter to a real warehouse; no production deployment yet. This is a v0.1 seed of the idea,
not something to point at production tonight.

## Where this is meant to be used

- **Quant:** position and NAV integrity, point-in-time correctness, and reconciliation —
  "offered vs present" is the ledger-versus-book reconciliation pattern with a cheaper
  implementation. A silent dimensional collapse is a wrong mark, not a missing row.
- **Entrepreneurial finance:** audit evidence. A control report you can hand to an
  accountant or an investor is worth more than a green dashboard, because it shows which
  checks fired and when. Unit economics belong next to correctness: see the roadmap.
- **AI pipelines:** LLM extraction is the new silent-corruption surface — model output
  written to a keyed table with a field name that drifted is the same failure with a
  stochastic author.

## Roadmap

- **v0.2 — adapters.** SQLite and CSV/SQL parser so `offered_present_parity` runs at a real
  load boundary; a checkpoint sidecar that persists canonical digests. *Done = the gate runs
  on a real pipeline nightly and its digest is published in the run log.*
- **v0.3 — `parity scan <table>`.** All four controls over any CSV/SQLite, JSON report. The
  honest version of a "data quality score": counts, samples, and named mechanisms.
- **v0.4 — cost module.** Fold the measured LLM capacity/cost model in (`cost/measure.py`),
  so an AI-heavy pipeline reports dollars per thousand rows beside its integrity report.
  *Done = a single command that says what a pipeline costs and whether its writes are sound.*
- **v0.5 — generalize `faults.py`.** Collapse, rename, truncate, duplicate, reorder, type
  drift — so CI can prove *any* new control, not just these four.
- **v1.0 — one real deployment.** Wire the gate into the live surplus-funds pipeline and run
  it nightly for 30 nights. *Done = "30 nights, N real defects caught, zero silent writes",
  with the reports to prove it.*

## Layout

```
parity.py         four controls, stdlib only
faults.py         fault injectors + the toy position book that prices a collapse
test_parity.py    the gate: fault matrix + the rejected-check negative result
demo.py           the same failure in dollars
docs/             the incident this came from
```
