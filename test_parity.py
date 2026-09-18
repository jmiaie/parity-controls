#!/usr/bin/env python3
"""The gate. Exit 0 only if every control fired on its fault, stayed silent on healthy
data, and the rejected check is still rejected.

Run: python3 test_parity.py     (stdlib only, no pytest, no fixtures)
"""
from __future__ import annotations

import sys

from faults import (COLLAPSE, DUPLICATE, HEALTHY, RENAME, SHORT_WRITE, TRUNCATE, load,
                    present_keys, source_rows, substitute_key)
from parity import (ParityViolation, canonical_hash, cross_field, offered_present_parity,
                    share_anomaly, verify_canonical)

FAILS: list[str] = []
LABEL = {0: ("Yes", "Up", "Over"), 1: ("No", "Down", "Under")}


def check(name: str, got, want) -> None:
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  got={got} want={want}")
    if not ok:
        FAILS.append(name)


def fires(fn) -> bool:
    try:
        fn()
    except ParityViolation:
        return True
    return False


ROWS = source_rows()
print(f"source rows: {len(ROWS)}\n")

print("1. write boundary - offered vs present")
for fault, want in ((HEALTHY, False), (COLLAPSE, True), (RENAME, True), (DUPLICATE, True),
                    (TRUNCATE, True), (SHORT_WRITE, True)):
    L = load(ROWS, fault)
    check(f"{fault}: parity fires",
          fires(lambda: offered_present_parity(len(ROWS), L.present, key="(wallet,slug,oi)")),
          want)

print("\n1b. key SETS - the count-only form was blind to a substitution")
# Found by review, not by me: N rows in, N rows land, one key swapped on the way. The
# count-only boundary says fine. This is the assertion that failed before the fix.
KEYS = present_keys(ROWS)
SUB = substitute_key(KEYS)
check("the counts really are equal (so counting cannot see it)",
      len(SUB) == len(KEYS), True)
check("count-only form: SILENT on a substitution  <- the bug",
      fires(lambda: offered_present_parity(len(KEYS), len(SUB))), False)
check("key-set form: FIRES", fires(lambda: offered_present_parity(KEYS, SUB)), True)
check("key-set form: silent when the keys match",
      fires(lambda: offered_present_parity(KEYS, present_keys(ROWS))), False)
check("key-set form: fires when the write died before the INSERT",
      fires(lambda: offered_present_parity(KEYS, present_keys(ROWS, SHORT_WRITE))), True)

print("\n2. the rejected check - rows vs COUNT(DISTINCT key)")
# A keyed table's row count and its distinct-key count are the same number by
# construction, so this check can only ever fire on the one case a PK'd table
# cannot produce: an unkeyed write. It is a mirror, not a detector.
for fault, want in ((HEALTHY, False), (COLLAPSE, False), (RENAME, False), (TRUNCATE, False),
                    (DUPLICATE, True)):
    L = load(ROWS, fault)

    def key_parity(L=L):
        return offered_present_parity(L.distinct_keys, L.present, where="rows vs distinct-key")

    check(f"{fault}: key-parity fires", fires(key_parity), want)

print("\n3. cross-field - index must agree with its label")
for fault, want in ((HEALTHY, False), (COLLAPSE, True), (RENAME, True)):
    L = load(ROWS, fault)
    pairs = [(r["outcome_index"], r["outcome"]) for r in L.rows]
    check(f"{fault}: cross-field fires",
          fires(lambda: cross_field(pairs, LABEL, name="outcome_index<->outcome")), want)

print("\n4. share anomaly - WARN only, and it must tell two defects apart")
L = load(ROWS, COLLAPSE)
msg = share_anomaly([r["outcome_index"] for r in L.rows], name="outcome_index", min_n=100)
check("COLLAPSE: DEGENERATE fires", bool(msg) and "DEGENERATE" in msg, True)
print(f"        message: {msg}")
check("HEALTHY: silent",
      share_anomaly([r["outcome_index"] for r in load(ROWS, HEALTHY).rows],
                    name="outcome_index", min_n=100), None)
check("all-empty column: UNPOPULATED, not DEGENERATE",
      "UNPOPULATED" in (share_anomaly([""] * 500, name="enriched_at", min_n=100) or ""), True)
check("below the N floor: silent", share_anomaly([0] * 50, name="x", min_n=100), None)

print("\n5. canonical hash - stable, and it moves when the data moves")
a = canonical_hash(load(ROWS, HEALTHY).rows)
b = canonical_hash(list(reversed(load(ROWS, HEALTHY).rows)))
c = canonical_hash(load(ROWS, COLLAPSE).rows)
check("order-independent", a == b, True)
check("collapse changes the digest", a != c, True)
check("float drift does not", canonical_hash([{"x": 0.1 + 0.2}]) == canonical_hash([{"x": 0.3}]),
      True)
check("verify_canonical fires on a moved digest",
      fires(lambda: verify_canonical(load(ROWS, HEALTHY).rows, c, what="positions")), True)

print(f"\n{'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
