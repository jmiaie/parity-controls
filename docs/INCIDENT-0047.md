# INCIDENT-0047 — a field-name typo collapsed 2.6M rows and nothing failed

**Status:** closed · **Detected by:** discrepancy between two derived numbers, not by monitoring
· **Time to detect:** days · **Silent for the entire window** · **Date:** 2026-09-18

## Summary

A backfill read `outcomeIndex` from a camelCase API as `outcome_index` and fell back to a
default of `0`. `.get(key, default)` does not raise, so every row received `0`. The table's
primary key was `(wallet, slug, outcome_index)`, so the default erased a key dimension: every
market where a wallet held **both** outcomes collapsed to a single row, and the second row
overwrote the first.

No exception. No log line. No failed run. The load reported success.

**Scale:** of 4,744,661 rows, only **249** carried `outcome_index = 1`. After the fix:
**3,813,395**. The corrected load moved the total to **7,418,574** distinct keys — a
**+56.4%** change to the dataset that the pipeline had been reporting as healthy.

## How it was found

Not by a monitor. The trigger was a **labeling** discrepancy: one derived figure counted
"predictions" as settled *and* open, while its consumer could only use settled. Two defects
were wearing one symptom — a labeling bug and a data bug — and fixing only the labeling one
would have left the data bug running silently. The useful habit: **ask which number is wrong
before fixing anything.**

## Why the obvious check would not have caught it

`rows vs COUNT(DISTINCT key)` looks like a collapse detector. It is not, wherever the natural
key is the primary key: `INSERT OR REPLACE` erases the violation at write time, so the row
count and the distinct-key count are the same number **by construction**. It cannot disagree
with itself.

This was not asserted, it was run — four fabricated faults against both candidate checks:

| fabricated fault | rows vs distinct-key | offered vs present (write boundary) |
|---|---|---|
| HEALTHY (control) | silent | silent |
| **COLLAPSE** (`oi` → constant 0) | **silent** | **FIRED** 240 → 180 |
| **RENAME** (field absent → default 0) | **silent** | **FIRED** 240 → 180 |
| DUPLICATE (unkeyed copy) | FIRED 280 → 240 | FIRED 240 → 280 |

The mirror fires only on inflation — the one case a keyed table cannot produce — and stays
silent on the exact collapse that destroyed 2.67M rows.

## A second family, found while verifying

A cross-field check — `outcome_index` must agree with its own `outcome` label — surfaced
**65,825 violating rows** (1.09% of 6,038,923). All one direction, isolated to 2 of 721
wallets, API-confirmed on a 12/12 sample. Mechanism: a rebuild used `INSERT OR REPLACE`
without first clearing rows the repaired key no longer matched, so the corrected row landed
*beside* the stale one. A write-time collision, repaired as duplication.

Its max-share was **0.9911** — under a `0.999` statistical trigger. The mechanism-level
check found it; the statistical one would have missed it. That is why the checks are ordered
the way they are in this repo.

## What changed

1. **Write-boundary assertion** — rows offered by the source must equal rows present after
   the write, asserted at the boundary, not in a report.
2. **A raising accessor** at the API boundary. `.get(key, default)` on an API field is a
   silent-failure construct; the fix is `need(d, k)`, not a better default.
3. **Cross-field consistency** as the collapse-family detector.
4. **A retraction.** The original commit message claimed a change made the defect
   impossible to reintroduce. It did not — the camelCase fallback preserved the silent-0
   path. Overstated guarantees are how the next silent zero gets waved through review.
5. **Fault injection as the entry condition** for any new control. An assertion that has
   never been observed to fail is registered, not working.

## Lessons

1. **A gate that has never failed is not evidence.** Exercise it with a fabricated fault or
   do not claim it.
2. **Root cause is the construct, not the symptom.** Ban `.get(k, default)` on API fields;
   do not add a downstream report that guesses at the damage afterwards.
3. **Two defects can wear one symptom.** Ask which number is wrong.
4. **The control that matters is the healthy one.** A check that is silent on a fault *and*
   silent on healthy data has not been tested — it has merely never spoken. A control that
   binds the resource and answers wrongly ("a plausible liar") beats one that is merely absent.
5. **Denominators or it did not happen.** The first written summary of this incident implied
   a pure redistribution at a constant total. The total had moved 56%. Measure the
   denominator before you quote the ratio.

## Provenance

Found, measured and repaired by the data-platform workstream of a four-agent engineering team
(one autonomous agent maintaining the pipeline, one verifying, one on infrastructure, one on
data integrity), with the verification discipline of a separate reviewer. Numbers are reported
as measured on the pipeline host; the pre-fix count of 249 is received from the original commit
message, not independently reproduced, and is labelled as such.
