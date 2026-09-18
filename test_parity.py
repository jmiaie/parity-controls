#!/usr/bin/env python3
"""The gate. Exit 0 only if every control fired on its fault, stayed silent on healthy
data, and the rejected check is still rejected.

Run: python3 test_parity.py     (stdlib only, no pytest, no fixtures)
"""
from __future__ import annotations

import hashlib
import random
import sys
from decimal import Decimal

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
# A forged row has to carry its own `name=` prefix to be a forgery: `"x\ny"` only lands an
# embedded newline and never matches the two-line form, which is why the first draft of this
# check passed on the unfixed module (found by the third review, 2026-09-18, and now caught
# mechanically by tools/audit_tests.py).
check("a value cannot impersonate a second row",
      canonical_hash([{"a": "x"}, {"a": "y"}]) != canonical_hash([{"a": "x\na=y"}]), True)
check("a column NAME cannot impersonate a second column",
      canonical_hash([{"a=\x1fb": "1"}]) != canonical_hash([{"a": "", "b": "1"}]), True)
check("ceiling pin (not a regression test): the clean-data digest does not move",
      canonical_hash([{"x": 1}])[:12], "1f206b11c23e")

print("\n1d. misuse is named, not a mystery message")


def raises_typeerror_with(thunk, *markers) -> bool:
    """Asserting only the exception TYPE cannot see this fix: the unfixed module raised a
    TypeError too, so the check passed with the defect present. Assert the message instead.

    Every marker must be present. One marker is not enough where the raw error shares a word
    with the named one: "unhashable" is in CPython's own message, so asserting it alone still
    passed on the unfixed module (third review again, caught by tools/audit_tests.py).
    """
    try:
        thunk()
    except TypeError as e:
        return all(m in str(e) for m in markers)
    except Exception:
        return False
    return False


check("counts mixed with a collection: named TypeError",
      raises_typeerror_with(lambda: offered_present_parity(5, [1, 2]), "must be BOTH counts"), want=True)
check("unhashable keys: named TypeError, cause kept in the message",
      raises_typeerror_with(lambda: offered_present_parity([{"k": 1}], [{"k": 1}]),
                            "BOTH collections", "unhashable"), want=True)
check("a bool is not a count (`True == 1` used to pass as one)",
      raises_typeerror_with(lambda: offered_present_parity(True, 1), "must be BOTH counts"), want=True)
check("ceiling pin (not a regression test): both sides empty is SILENT (documented blind spot, the caller owns it)",
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
check("a VALUE carrying '=' cannot impersonate a column either",
      canonical_hash([{"a": "b=c"}]) != canonical_hash([{"a=b": "c"}]), want=True)

print("\n1f. non-finite floats are tagged, not silently spelled like a string")

check("float nan vs the string 'nan'", canonical_hash([{"x": float("nan")}]) != canonical_hash([{"x": "nan"}]), want=True)
check("float inf vs the string 'inf'", canonical_hash([{"x": float("inf")}]) != canonical_hash([{"x": "inf"}]), want=True)
check("not a regression test: nan is still order- and run-stable", canonical_hash([{"x": float("nan")}]) == canonical_hash([{"x": float("nan")}]), want=True)

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

print("\n1j. the third review: shapes that were neither stable nor unambiguous")

check("a dict cell is refused by name, not hashed as its own repr",
      raises_typeerror_with(lambda: canonical_hash([{"x": {"k": 1}}]), "scalar cells"), want=True)
check("a list cell is refused too",
      raises_typeerror_with(lambda: canonical_hash([{"x": [1, 2]}]), "scalar cells"), want=True)
check("a set cell is refused: its text, and so its digest, varies with PYTHONHASHSEED",
      raises_typeerror_with(lambda: canonical_hash([{"x": {"a", "b"}}]), "scalar cells"), want=True)
check("a bytes cell is refused (b'\x1f' hashed like the string \"b'\\\\x1f'\")",
      raises_typeerror_with(lambda: canonical_hash([{"x": b"\x1f"}]), "scalar cells"), want=True)
check("a non-str column NAME is refused, so {1: 'x'} cannot hash as {'1': 'x'}",
      raises_typeerror_with(lambda: canonical_hash([{1: "x"}]), "must be str"), want=True)
check("a None column NAME is refused",
      raises_typeerror_with(lambda: canonical_hash([{None: "x"}]), "must be str"), want=True)
check("mixed key types give the named error, not a raw sort TypeError",
      raises_typeerror_with(lambda: canonical_hash([{1: "a", "b": 2}]), "must be str"), want=True)
check("columns=[1, 'b'] is the same named error",
      raises_typeerror_with(lambda: canonical_hash([{"x": 1}], columns=[1, "b"]), "must be str"), want=True)
check("the str shape the live pipeline uses is untouched",
      canonical_hash([{"a": "1", "b": "x"}], columns=["a", "b"]) ==
      canonical_hash([{"b": "x", "a": "1"}], columns=["b", "a"]), want=True)

print("\n1k. ceilings the third review named, pinned as ceilings rather than left as surprises")

check("ceiling pin (not a regression test): -0.0 and 0.0 are the same number and hash alike",
      canonical_hash([{"x": -0.0}]) == canonical_hash([{"x": 0.0}]), want=True)
check("ceiling pin (not a regression test): Decimal is hashed by exact text, so Decimal('1.0') and int 1 disagree",
      canonical_hash([{"x": Decimal("1.0")}]) != canonical_hash([{"x": 1}]), want=True)
check("ceiling pin (not a regression test): float/str separation is zero-padding, not a type tag (1.5 == '1.500000')",
      canonical_hash([{"x": 1.5}]) == canonical_hash([{"x": "1.500000"}]), want=True)
check("ceiling pin (not a regression test): '1', 1 and 1.0 agree, and that is as far as it generalises",
      canonical_hash([{"x": 1}]) == canonical_hash([{"x": 1.0}]) == canonical_hash([{"x": "1"}]), want=True)

print("\n1i. injectivity, over random input rather than the cases above")

# A bounded, seeded fuzz. The alphabet deliberately excludes the README's designed equivalences (a
# value and its own text spelling; 1e-7 and 2e-7 both print 0.000000; an integral float prints as
# an integer) - a fuzzer that does not separate "as designed" from "collision" reports noise, and
# the first pass of this one did exactly that: 34 hits, every one a documented ceiling.
# What it cannot do is prove completeness: the alphabet is mine, so this bounds the class the test
# can see. The README says "no collision found over 2000 random rows", not "injective, proved".
_FUZZ_KEYS = ["a", "b", "c", "a=x", "a=b", "a\x1f", "a\\", "a\x00", "a\n", "a\r", "=", "x=y"]
_FUZZ_VALS = ["x", "y", "x=y", "nan", "inf", "-inf", "\x1f", "\n", "\r", "\\", "\x00",
              1.5, -1.5, 3.25, float("nan"), float("inf"), float("-inf"), None, True, 7]
_r = random.Random(20260918)


def _rand_row(n=None):
    return {_r.choice(_FUZZ_KEYS): _r.choice(_FUZZ_VALS) for _ in range(n or _r.randint(1, 4))}


_pool, _seen = [], set()
while len(_pool) < 2000:
    _d = _rand_row()
    _k = tuple(sorted((a, repr(b)) for a, b in _d.items()))
    if _k in _seen:
        continue
    _seen.add(_k)
    _pool.append(_d)

_byhash = {}
for _d in _pool:
    _byhash.setdefault(canonical_hash([_d]), _d)
check("2000 random distinct rows -> 2000 distinct digests, no collision", len(_byhash), want=2000)

_stuck = 0
for _d in _pool:
    _k = _r.choice(list(_d))
    _cands = [v for v in _FUZZ_VALS if repr(v) != repr(_d[_k])]
    if _cands and canonical_hash([_d]) == canonical_hash([{**_d, _k: _r.choice(_cands)}]):
        _stuck += 1
check("2000 single-cell changes, none of them invisible", _stuck, want=0)

_same = 0
for _d in _pool[:1000]:
    _fresh = next(k for k in _FUZZ_KEYS if k not in _d)
    if canonical_hash([_d]) == canonical_hash([{**_d, _fresh: _r.choice(_FUZZ_VALS)}]):
        _same += 1
check("1000 rows with a key added, none hashing like the original", _same, want=0)

check("the designed equivalences still hold (so the exclusion above is not a lie)",
      (canonical_hash([{"a": 1e-7}]) == canonical_hash([{"a": 2e-7}]),
       canonical_hash([{"a": None}]) == canonical_hash([{"a": ""}]),
       canonical_hash([{"a": 1}]) == canonical_hash([{"a": 1.0}])) == (True, True, True), want=True)

print("\n9. a row that carries no columns is refused, not folded into the empty digest")
_bare = "<no refusal>"
try:
    canonical_hash([{}])
except ParityViolation as exc:
    _bare = str(exc)
check("column-less row refused, naming the mechanism",
      ("no columns" in _bare, "empty digest" in _bare), want=(True, True))
check("an explicit empty column set over real rows is refused too",
      fires(lambda: canonical_hash([{"a": 1}], columns=[])), want=True)
check("not a regression test - an empty ROW SET stays legitimate (guard is not refuse-everything)",
      canonical_hash([]), want=hashlib.sha256(b"").hexdigest())

print(f"\n{'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
