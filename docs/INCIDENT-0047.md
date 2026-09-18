# INCIDENT-0047 — a field-name typo collapsed 2.6M rows and nothing failed

**Status:** closed · **Detected by:** a reconciliation between stored counts, not by monitoring
· **Silent for the entire window** · **Date:** 2026-09-18 · **Numbers:** as measured on the
pipeline host by the data workstream, then corrected by one independent review pass (§Corrections).

## Summary

A backfill read `outcomeIndex` from a camelCase API as `outcome_index` and fell back to a
default of `0`. `.get(key, default)` does not raise, so every row received `0`. The table's
primary key was `(wallet, slug, outcome_index)`, so the default erased a key dimension: every
market where a wallet held **both** outcomes collapsed to a single row, and the second row
overwrote the first.

No exception. No log line. No failed run. The load reported success.

**Scale:** the stored row count went from **4,744,661** to **7,418,574** once repaired — a
**+2,673,913 (+56.4%)** change to a dataset the pipeline had been reporting as healthy. Of the
4,744,661 stored rows, only **249** carried `outcome_index = 1`; the current live count is
**3,871,226**. Provenance, stated because it matters: the `249` and the pre-fix total are
**received from the original commit message and not re-measured** — the earliest backup predates
the table's creation, so no pre-fix copy exists to count. An earlier figure of 3,813,395 differs
from the live 3,871,226 by 57,831, consistent with a read taken mid-rebuild (the repair ran in
per-wallet sequence over roughly one hour).

## How it was found

Not by a monitor. Two defects were in flight wearing one symptom, and they were found
**separately, about 15.5 hours apart**:

- **Defect A — labeling** (closed 15:49): a derived figure counted "predictions" as settled *and*
  open, while its consumer could only use settled.
- **Defect B — data** (16:15): the collapse itself. It surfaced when the stored counts would not
  reconcile against canonical — **4,744,661 stored vs 4,972,980 canonical**.

The useful habit is not "assume two defects". It is **ask which number is wrong before fixing
anything** — and expect the second defect to arrive after you have declared victory.

## Why the obvious check would not have caught it

`rows vs COUNT(DISTINCT key)` looks like a collapse detector. It is not, wherever the natural key
is the primary key: `INSERT OR REPLACE` erases the violation at write time, so the row count and
the distinct-key count are the same number **by construction** — and here they were: 4,744,661 and
7,418,574 are both stored *row* counts. The check cannot disagree with itself.

This was not asserted, it was run — fabricated faults against both candidate checks. **Scope:**
the reviewer's fabricated set was collapse / rename / duplicate; **truncate and the two later
faults are local additions to this repo's matrix**, not the reviewer's measurements.

| fabricated fault | rows vs distinct-key | offered vs present (write boundary) |
|---|---|---|
| HEALTHY (control) | silent | silent |
| **COLLAPSE** (`oi` → constant 0) | **silent** | **FIRED** |
| **RENAME** (field absent → default 0) | **silent** | **FIRED** |
| DUPLICATE (unkeyed copy) | FIRED (inflation) | FIRED |
| TRUNCATE (a page never lands) | **silent** | FIRED |
| SUBSTITUTE (count-preserving key swap) | **silent** | FIRED — key-set form only |
| SHORT_WRITE (died before INSERT) | **silent** | FIRED — if armed on the failure path |

The mirror fires only on inflation — the one case a keyed table cannot produce — and stays silent
on the exact collapse that cost 2.67M rows.

## A second family, found while verifying

A cross-field check — `outcome_index` must agree with its own `outcome` label — surfaced **65,825
violating rows: 1.0900% of the 6,038,923 rows in the six canonical binary-label groups** (0.887%
of all rows; the denominator is named on purpose). All one direction (`oi=0` carrying the second
label; the mirror count was zero), isolated to **2 of 721** wallets, and confirmed against the API
on a **12/12 sample** — which verifies the mechanism, not all 65,825 rows.

Mechanism, scoped: the **batch** rebuild (`batch_rebuild.py:116`) runs `DELETE ... WHERE wallet=?`
*before* its `INSERT OR REPLACE`, so wherever the mapped key disagrees with the stale row the
corrected row lands *beside* it instead of over it. The **parallel** writer does not share this —
`backfill_parallel.py:127-129` deletes inside the per-wallet loop after page 1 succeeds, so it
self-corrects and contributes no orphans. One of two writer paths, then: a write-time collision
repaired as duplication.

The post-fix maximum single-value share for that family is **0.521829** (exact). The pre-fix
dominant-value share was **0.999947** (= 1 − 249/4,744,661) — one value's worth of margin under a
`0.999` statistical trigger. The shape is the lesson: a column pinned near-constant is a symptom
worth investigating, and a threshold calibrated on the incident that motivated it would have
missed it. A figure of `0.9911` appeared in early drafts of this write-up and is **withdrawn** —
the reviewer who owns the measurement has no measurement that yields it.

## What changed

1. **Write-boundary assertion** — rows offered by the source must equal rows present after the
   write, asserted at the boundary rather than in a report; **as key SETS, not counts**, and
   **armed on the failure path** as well as the success path. The last two were fixed only after
   review, because the first version of this control failed both (see Corrections).
2. **A raising accessor** at the API boundary. `.get(key, default)` on an API field is a
   silent-failure construct; the fix is `need(d, k)`, not a better default.
3. **Cross-field consistency** as the collapse-family detector.
4. **A retraction that still stands.** The original commit message claimed the change made the
   defect impossible to reintroduce. It did not, and it still has not: both current writers
   resolve the field as `outcome_index`, then `outcomeIndex`, then `or 0`. An API that drops
   *both* spellings — or sends an explicit `null` — still writes `0` silently. That is now **two**
   silent paths where there was one (a missing key via the `.get` default, an explicit null via
   `or 0`). Current state, plainly: **accepts either spelling; still defaults to 0 if neither is
   present.**
5. **Fault injection as the entry condition** for any new control. An assertion that has never
   been observed to fail is registered, not working.

## Corrections (independent review, same day)

An external review of this document returned seven numbered corrections and four blind spots in
the write-boundary control. All seven are applied above:

1. Post-fix count restated from 3,813,395 to the live **3,871,226**, with the likely cause of the
   gap (a mid-rebuild read) named rather than hidden.
2. The +56.4% restated as a **stored-count delta**, not a "corrected distinct-key total" — the two
   are equal here, which is exactly the tautology described above.
3. **Truncate re-attributed**: the reviewer's fabricated set covered collapse / rename / duplicate.
4. The 1.09% **denominator named** (the six canonical binary-label groups, not all rows), and
   "API-confirmed 12/12" restated as a sample.
5. `0.9911` **withdrawn**, replaced with the reviewer's pre-fix `0.999947` and post-fix `0.521829`.
6. Writer scope narrowed to the **batch** path, with the parallel path's self-correction stated.
7. **Discovery framing corrected**: the two defects were found about 15.5 hours apart, not
   simultaneously. "Two defects, one symptom" is the lesson; "discovered as two" was not what
   happened.

Two of the four blind spots were **real defects in this repo's own control**, not prose errors: the
count-only form passed a count-preserving substitution, and nothing armed the check when the write
failed. Both are now fixed and covered by fabricated faults (`SUBSTITUTE`, `SHORT_WRITE`) that fail
if the fix is reverted.

## Provenance

Found, measured and repaired by the data-platform workstream of a four-agent engineering team (one
agent maintaining the pipeline, one verifying, one on infrastructure, one on data integrity), with
an independent review pass over this write-up. Numbers are as measured on the pipeline host; pre-fix
figures are received from the original commit message and labelled as such throughout. No
credentials, keys, or account identifiers appear in this document.
