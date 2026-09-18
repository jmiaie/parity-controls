# parity

**Write-boundary integrity for financial data and AI pipelines.** Four controls, each one
required to prove itself against a fault it must catch — because a control that has never
been observed to fail is not a control.

A field-name typo read with a default silently collapsed **2.67M rows** of dimensional data on a
live pipeline (stored count 4,744,661, and 7,418,574 once repaired). No exception, no log line,
no failed run. The position book was wrong, and every dashboard was green. Case study: [`docs/INCIDENT-0047.md`](docs/INCIDENT-0047.md).

## Run it

```bash
python3 test_parity.py   # the fault matrix: every control must fire on its fault, stay silent when healthy
python3 demo.py          # the money: 97 rows vanish and the book is off by 22.7%
```

No dependencies. Python 3.10+. Four files, all short enough to read in one sitting.

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

## First real run (390 real rows, 44 columns, in-house leads pipeline)

```
canonical_hash (freeze digest): 0e14d492cb2b0795fd79d0f2583da41724f438cf4bf525962753d6398c85aeab
classified: {'ok': 19, 'UNPOPULATED': 19, 'DEGENERATE': 6}   -> 25 of 44 columns warn
```

The split is the point. A cardinality rule alone calls all 25 of those a violation, and 19
of them are just columns nothing ever wrote — on a healthy file (measured: 18 of 44 columns
on the first pass, 25 with a stricter N floor). Noisy warnings are how real ones get ignored,
so `share_anomaly` names the two defects separately and the operator only investigates 6.

The run also surfaced a real business finding: `owner_name`, `owner_mail_address` and 8 other
enrichment columns are **100% empty** in that file — either a stale artifact or a stage that
never wrote. And a freeze digest for the file, so next run can prove whether it moved.

## The four controls, in the order they earn their place

| # | control | catches | cost |
|---|---|---|---|
| 1 | `offered_present_parity` | collapse, rename, truncation, duplication, count-preserving substitution, a write that died before its INSERT | one compare — or one set compare |
| 2 | `cross_field` | a column forced to a default while its sibling still holds the truth | one pass |
| 3 | `share_anomaly` | a declared multi-valued column gone degenerate, **and** an unpopulated column (different messages) | one pass |
| 4 | `canonical_hash` | "the data did not move" — around any repair or rebuild | one pass |

1 and 2 are arithmetic. 3 is a heuristic and it says so, including its measured blind spot on the
function itself: in the incident the dominant value sat at share `0.999947` — one value's worth of
margin under a `0.999` trigger — and the post-fix maximum for the same family is `0.521829`.
Calibrate that threshold from the mechanism (what fraction of rows can legitimately share a value),
never from the incident that motivated it.

## Known blind spots

Named on the controls themselves, so a reader meets them here rather than in production:

- `offered` must be computed from the **raw** payload, before any field-name mapping. Derive it
  with the writer's own mapper and the defect is baked into both sides — the bug erases its own
  evidence and the comparison passes trivially.
- Counted `offered` must be **distinct keys, never raw rows**. A page that repeats a key is healthy —
  the writer dedupes it — but it makes rows outnumber keys, so the naive form alarms on good data.
  Measured before it was assumed: 8,411 rows over 3 wallets carried 0 repeated keys, so the wrong form
  passes today and waits for the first paging change to start crying wolf. The key-collection form
  cannot make this mistake.
- A row excluded from a check is a row the check cannot fail on. A "partial" or short-fetch batch
  gets asserted anyway, with the known shortfall expected as the delta.
- Key-set comparison catches one substitution, not two compensating replacements. Hash the
  canonical form when that matters.
- `share_anomaly` is a heuristic whose threshold must come from the mechanism. It is WARN-only for
  that reason: it returns a message and never raises.

## Rejected on purpose

`rows vs COUNT(DISTINCT key)` as a collapse detector. Where the natural key is the primary
key, `INSERT OR REPLACE` erases the violation at write time, so the two counts are equal
**by construction** and the check cannot disagree with itself. In the fault matrix it is
silent on collapse, silent on rename, silent on truncation, and fires only on the unkeyed
duplicate — the one case a keyed table cannot produce. That negative result is executable:
`test_parity.py` section 2.

## What is proven, and what is not

**Proven** (reproduce both commands): the fault matrix passes 31/31 — every control fires on
collapse, rename, truncation, duplication, a count-preserving substitution, and a write that died
before its INSERT, while the healthy control leaves all of them silent; the demo's 22.7% book error;
order-independence and float-stability of the hash. Note where the faults came from, because it is
the point: collapse, rename and duplicate were found by an outside reviewer, and **three** faults are
here because review exposed real defects in this control — the count-only form passed a substitution,
passed a dead write, and **false-fired on healthy data** when a page repeated a key.

**Not proven:** load beyond a couple of thousand rows per run in one process; no concurrency
claim (the live adapter is single-writer and says so in the code); no warehouse adapter; one
live nightly job on one host, and its record is nights old, not 30. This is a v0.2 seed of the
idea, not something to point at production.

## Where this is armed (not just intended)

`jmiaie/claude`, branch `feat/madera-pdf-source`, `ca_surplus_funds.py` — the live CA
surplus-funds pipeline. `write_csv_gated()` replaced the bare CSV write on 2026-09-18:

- **Before writing:** a source that handed us rows and produced zero leads aborts the run. Not a
  filter — a renamed column or a dead parser, which erases a whole county's listing while the run
  still reports success. That is INCIDENT-0047's shape, and it is the reason this boundary was
  worth arming first.
- **After writing:** the rows go to a scratch path, come back **off disk**, and their key set is
  compared with what was offered; only then does `os.replace()` put them at the real path. A
  violation therefore cannot overwrite the previous night's data, and the bad file is kept as
  evidence.
- **Missing dependency = no write.** If `parity` is not importable the run refuses, loudly.
  A corrupt lead list is worse than a missing one, and the nightly digest is how those two stop
  looking identical from the outside.
- **The adapter's own fault matrix, 14/14** (`tests/test_write_gate.py`, in the repo it guards):
  refuses a silent collapse, a count-preserving substitution, a partial write, and its own absent
  dependency — and leaves the prior file byte-identical in each of those cases.

Nightly at 05:00 via `/srv/pipeline/scripts/surplus-gate-nightly.sh`. stdout is one line — lead count,
per-stage drop counts, counties produced/offered, and the freeze digest — delivered whether or not
it is interesting, because a silent night must not look like a night the check never ran.

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

- **v0.2 — adapters. DONE 2026-09-18.** The gate runs at a real load boundary, nightly, on a live
  pipeline, and its digest lands in the run log. See *Where this is armed* above.
- **v0.3–v0.5 — cut on purpose.** (`parity scan <table>`, the cost module, generalized fault
  injection.) Not wrong, just not the bottleneck. More controls do not produce the missing
  evidence, and the missing evidence is **a real defect caught in the wild**. Notes kept, nothing
  built — a control nobody has needed yet is a liability with a maintenance cost.
- **v1.0 — one real deployment, 30 nights.** Clock started 2026-09-18. *Done = "30 nights, N real
  defects caught, zero silent writes", with the reports to prove it.* Night 1 of 30, and the
  reports are the per-night JSON the gate drops beside the leads file.
- **v1.1 — prove the ALARM, not just the check.** Every control here is proven to *raise*; nothing
  proves the alert reaches a human. Inject one synthetic bad row into a shadow table nightly, assert
  the alert actually arrives, then remove it. Until that exists, a silenced notifier and a healthy
  pipeline look identical from the inside — which is the failure mode that opened this whole project.
  *Opened by review: "neither of us has a control that was built to fail."*

## Layout

```
parity.py         four controls, stdlib only
faults.py         fault injectors + the toy position book that prices a collapse
test_parity.py    the gate: fault matrix + the rejected-check negative result
demo.py           the same failure in dollars
docs/             the incident this came from
```

## License and visibility

Private, deliberately. The thing this repo is missing is not a feature — it is a defect caught in
the wild, and until that exists the honest state is "unproven in production". MIT as soon as it has
one, so the first outside reader can check the claim instead of taking it. Cost of the whole thing
today: zero dependencies, zero cloud, one nightly run on a host that was already up.
