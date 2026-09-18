#!/usr/bin/env python3
"""The gate. Exit 0 only if every control fired on its fault, stayed silent on healthy
data, and the rejected check is still rejected.

Run: python3 test_parity.py     (stdlib only, no pytest, no fixtures)
"""
from __future__ import annotations

import sys

from faults import (COLLAPSE, DUPLICATE, HEALTHY, RENAME, SHORT_WRITE, TRUNCATE, load,
                    present_keys, repeat_key_page, source_rows, substitute_key)
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


def raises_typeerror(fn) -> bool:
    """Caller misuse must be named as misuse, never as a data defect."""
    try:
        fn()
    except TypeError:
        return True
    except ParityViolation:
        return False
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

print("\n1c. rows vs KEYS - a repeated key in the page false-fires the naive form")
# Not a fault: the writer dedupes and the table is correct. But the page carries more rows
# than the table has distinct keys, so a boundary check counting RAW ROWS alarms on healthy
# data - the failure mode that gets a control muted. Named by review, not found by me.
PAGE = repeat_key_page(ROWS)
PK = present_keys(PAGE)
check("the page really does repeat a key", len(PAGE) > len(present_keys(ROWS)), True)
check("count-only form on RAW ROWS: FIRES on healthy data  <- false alarm",
      fires(lambda: offered_present_parity(len(PAGE), len(PK))), True)
check("count-only form on DISTINCT KEYS: silent",
      fires(lambda: offered_present_parity(len(PK), len(PK))), False)
check("key-set form: silent (there is no defect to find)",
      fires(lambda: offered_present_parity(PK, PK)), False)

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

print("\n5b. canonical hash - the forms that must NOT collide")
# Found by adversarial probe, 2026-09-18, not by reading the code: sorted columns joined with
# a separator is only injective if a VALUE cannot contain the separator. It could.
check("int 1 and float 1.0 agree (a type change is not a move)",
      canonical_hash([{"x": 1}]) == canonical_hash([{"x": 1.0}]), True)
check("a value cannot impersonate a second column",
      canonical_hash([{"a": "x", "b": "y"}]) != canonical_hash([{"a": "x\x1fb=y"}]), True)
check("a value cannot impersonate a second row",
      canonical_hash([{"a": "x"}, {"a": "y"}]) != canonical_hash([{"a": "x\ny"}]), True)
check("a column NAME cannot impersonate either",
      canonical_hash([{"a\x1fb": 1}]) != canonical_hash([{"a": 1, "b": 1}]), True)
check("pinned fixture: the clean-data digest is unchanged by the escaping",
      canonical_hash([{"x": 1}])[:12], "1f206b11c23e")

print("\n1d. misuse is named, not a mystery message")
check("counts mixed with a collection: TypeError",
      raises_typeerror(lambda: offered_present_parity(5, [1, 2])), True)
check("unhashable keys: TypeError",
      raises_typeerror(lambda: offered_present_parity([{"k": 1}], [{"k": 1}])), True)
check("both sides empty: SILENT (documented blind spot, the caller owns it)",
      fires(lambda: offered_present_parity([], [])), False)


# ---------------------------------------------------------------------------
# 1e-1i. The second audit, run by an independent agent that only executed code.
# Five counterexamples, all reproduced before the fix and pinned after it.
# ---------------------------------------------------------------------------
print("\n1e. row encoding: nothing may impersonate structure")

check("column name carrying '=' cannot impersonate a value",
      canonical_hash([{"a=x": 1}]) != canonical_hash([{"a": "x=1"}]), want=True)
check("column name carrying '=' cannot impersonate a second column",
      canonical_hash([{"a=b": "c"}]) != canonical_hash([{"a": "b=c"}]), want=True)
check("a VALUE carrying '=' still cannot impersonate a column",
      canonical_hash([{"a": "x", "b": "y"}]) != canonical_hash([{"a": "x=y"}]), want=True)

print("\n1f. non-finite floats are tagged, not silently spelled like a string")

check("float nan vs the string 'nan'", canonical_hash([{"x": float("nan")}]) != canonical_hash([{"x": "nan"}]), want=True)
check("float inf vs the string 'inf'", canonical_hash([{"x": float("inf")}]) != canonical_hash([{"x": "inf"}]), want=True)
check("nan is still order- and run-stable", canonical_hash([{"x": float("nan")}]) == canonical_hash([{"x": float("nan")}]), want=True)

print("\n1g. a string is a sequence of characters, not a collection of keys")

try:
    offered_present_parity("abc", "cba")
    check("one key per side passed as a string is refused, not silently passed", got=False, want=True)
except TypeError:
    check("one key per side passed as a string is refused, not silently passed", got=True, want=True)

print("\n1h. WARN-only means it does not raise")

check("empty column with min_n=0 returns nothing", share_anomaly([], name="col", min_n=0), want=None)
check("a generator is accepted (no len() on the caller's side)",
      share_anomaly((v for v in range(1200)), name="col"), want=None)

print(f"\n{'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
