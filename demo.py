#!/usr/bin/env python3
"""Why this exists, in one run: a silent field-name drift costs money and nobody sees it.

    python3 demo.py

The scenario is the real one: a camelCase API, a reader that used the snake_case name
with a default, and a table keyed on a tuple that just lost a dimension. No exception,
no log line, no failed run - and a position book carried at the wrong mark.
"""
from __future__ import annotations

from faults import COLLAPSE, HEALTHY, load, nav, source_rows
from parity import ParityViolation, canonical_hash, cross_field, offered_present_parity, share_anomaly

LABEL = {0: ("Yes", "Up", "Over"), 1: ("No", "Down", "Under")}

rows = source_rows()
good, bad = load(rows, HEALTHY), load(rows, COLLAPSE)
truth, lying = nav(good.rows), nav(bad.rows)

print(f"batch from the source API:      {len(rows):>6} rows")
print(f"rows the table holds, healthy:  {good.present:>6}")
print(f"rows the table holds, collapsed:{bad.present:>6}   <- {len(rows) - bad.present} rows gone, silently")
print()
print(f"position value, correct         {truth:>12,.2f}")
print(f"position value, collapsed       {lying:>12,.2f}")
print(f"error carried to the book       {lying - truth:>+12,.2f}"
      f"   ({(lying - truth) / truth:+.1%})")
print()

print("what the checks say, on the SAME broken load:")
for name, fn in (
    ("write-boundary parity", lambda: offered_present_parity(len(rows), bad.present)),
    ("rows vs distinct-key  ", lambda: offered_present_parity(bad.distinct_keys, bad.present,
                                                              where="rows vs distinct-key")),
    ("cross-field index<->label", lambda: cross_field([(r["outcome_index"], r["outcome"])
                                                       for r in bad.rows], LABEL)),
):
    try:
        fn()
        print(f"  {name}: silent  <- a control that cannot see this is decoration")
    except ParityViolation as e:
        print(f"  {name}: FIRED - {str(e)[:96]}")
print(f"  share anomaly       : {share_anomaly([r['outcome_index'] for r in bad.rows], name='outcome_index', min_n=100)}")
print()
print(f"canonical hash, correct / collapsed: {canonical_hash(good.rows)[:16]} / {canonical_hash(bad.rows)[:16]}")
print()
print("The two silent lines above are why the checks are ordered the way they are: the")
print("statistical one is a heuristic with a measured blind spot, the write-boundary and")
print("cross-field ones are arithmetic. Run test_parity.py to see the fault matrix that")
print("holds each of them to account.")
