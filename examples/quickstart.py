#!/usr/bin/env python3
"""parity in one run: the four controls, healthy case and broken case, side by side.

    python3 examples/quickstart.py

The dataset is small on purpose. Eight trade rows and four columns, so every line below
can be read against the data rather than trusted. Nothing here is a third-party import
and nothing here needs a database: the controls take lists and dicts.

Each control is shown twice where that is meaningful - once on data that is fine, so you
can see it stay SILENT, and once on the same data after a fault, so you can see it name
the mechanism. A control you have only ever seen pass is not a control.
"""
from __future__ import annotations

import os
import sys

# Works two ways: `python3 examples/quickstart.py` from the repo root, and `python3 -c
# "import examples.quickstart"` style imports from elsewhere. The repo is a flat layout,
# so the library lives one directory above this file.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parity import (  # noqa: E402  (import order is the point of the sys.path line above)
    ParityViolation,
    canonical_hash,
    cross_field,
    offered_present_parity,
    share_anomaly,
    verify_canonical,
)

# --------------------------------------------------------------------------------------
# The dataset: a day's trade blotter, as the source system hands it over.
# Four columns that describe two facts - which way the trade went, and what it is worth.
# `side` and `position` are the pair this library exists for: two columns, one fact, so a
# field-name drift cannot hide behind a default.
# --------------------------------------------------------------------------------------
SOURCE = [
    {"trade_id": "T-1001", "side": "buy", "position": "long", "notional": 12500.50},
    {"trade_id": "T-1002", "side": "sell", "position": "short", "notional": 8300.00},
    {"trade_id": "T-1003", "side": "buy", "position": "long", "notional": 4400.25},
    {"trade_id": "T-1004", "side": "sell", "position": "short", "notional": 15900.75},
    {"trade_id": "T-1005", "side": "buy", "position": "long", "notional": 2100.00},
    {"trade_id": "T-1006", "side": "sell", "position": "short", "notional": 7650.40},
    {"trade_id": "T-1007", "side": "buy", "position": "long", "notional": 30125.10},
    {"trade_id": "T-1008", "side": "sell", "position": "short", "notional": 980.05},
]

# What `side` is allowed to mean. This is a domain, not a threshold: buy is long, sell is
# short, and there is no third case to argue about.
SIDE_DOMAIN = {"buy": ("long",), "sell": ("short",)}

CHECKS_RUN = 0
CHECKS_FIRED = 0


def report(label, fn):
    """Run one control and print what it said, instead of a traceback.

    The library raises `ParityViolation` (an `AssertionError`) when a control fires. In
    production you want that exception - it is what stops a bad write. In a tour you want
    to keep going, so it is caught here and named.
    """
    global CHECKS_RUN, CHECKS_FIRED
    CHECKS_RUN += 1
    try:
        fn()
    except ParityViolation as exc:
        CHECKS_FIRED += 1
        print(f"    FIRED   {label}")
        print(f"            {exc}")
        return True
    print(f"    silent  {label}")
    return False


def rule(title):
    print()
    print(title)
    print("-" * len(title))


# --------------------------------------------------------------------------------------
# 1. offered_present_parity - the write boundary.
#    Pass KEY COLLECTIONS, not counts. The set form catches a count-preserving
#    substitution; the integer form cannot, and it false-fires on healthy data whenever a
#    page repeats a key.
# --------------------------------------------------------------------------------------
rule("1. offered_present_parity - did what we offered actually land?")

offered_keys = {row["trade_id"] for row in SOURCE}
present_keys = set(offered_keys)  # a healthy load: every offered key is in the table

report(
    "healthy load, key sets agree",
    lambda: offered_present_parity(offered_keys, present_keys, where="blotter write"),
)

# The fault: T-1004 does not appear in the table after the write. Same row count family,
# no exception during the load, and the desk would have carried eight trades when it holds
# seven. Only the key set disagrees.
collapsed_keys = present_keys - {"T-1004"}
report(
    "one key never landed",
    lambda: offered_present_parity(offered_keys, collapsed_keys, where="blotter write",
                                   key="trade_id"),
)

print("    note: offered=0, present=0 passes on purpose. The write boundary cannot tell")
print("          'nothing was offered' from 'a dead fetcher offered nothing'; the caller")
print("          owns that distinction.")

# --------------------------------------------------------------------------------------
# 2. cross_field - two columns that describe the same fact must agree.
#    No threshold, no N floor: the disagreement is arithmetic.
# --------------------------------------------------------------------------------------
rule("2. cross_field - side and position describe one fact")

good_pairs = [(row["side"], row["position"]) for row in SOURCE]
report(
    "healthy blotter, side agrees with position",
    lambda: cross_field(good_pairs, SIDE_DOMAIN, name="side<->position"),
)

# The fault, and it is the real one: the reader looked up `side` under a name the API does
# not use, an absent field became the default "buy", and the position column - written
# from a different mapping - still carries the truth. Half the book now reads as long.
drifted_pairs = [("buy", row["position"]) for row in SOURCE]
report(
    "field-name drift forced side to its default",
    lambda: cross_field(drifted_pairs, SIDE_DOMAIN, name="side<->position"),
)

# --------------------------------------------------------------------------------------
# 3. share_anomaly - WARN only, it returns a message and never raises.
#    `min_n` is 1000 in production so a small batch cannot produce a warning; it is set to
#    the batch size here because this dataset is eight rows. Two different defects, two
#    different messages - a column gone degenerate, and a column nothing ever wrote.
# --------------------------------------------------------------------------------------
rule("3. share_anomaly - a declared multi-valued column, gone quiet")

healthy_sides = [row["side"] for row in SOURCE]
print(f"    healthy {len(set(healthy_sides))} distinct sides -> "
      f"{share_anomaly(healthy_sides, name='side', min_n=len(SOURCE))}")

# Degenerate: every row carries the same value, which is what a default does to a column.
degenerate = ["buy" for _ in SOURCE]
print(f"    collapsed -> {share_anomaly(degenerate, name='side', min_n=len(SOURCE))}")

# Unpopulated is a different defect with a different fix, so it gets a different message.
# An empty string is one value; calling that a cardinality violation would warn on every
# legitimately-empty column in a healthy file.
unwritten = ["" for _ in SOURCE]
print(f"    never written -> {share_anomaly(unwritten, name='settlement_ccy', min_n=len(SOURCE))}")

# --------------------------------------------------------------------------------------
# 4. canonical_hash - "the data did not move", as a check rather than a sentence.
#    Hash the canonical form, store the digest, re-hash around any repair.
# --------------------------------------------------------------------------------------
rule("4. canonical_hash - make a repair provable")

broken = [dict(row, side="buy") for row in SOURCE]   # the drifted load, as it was written
digest_broken = canonical_hash(broken)
repaired = [dict(row) for row in SOURCE]             # the repair: side restored from source
digest_repaired = canonical_hash(repaired)

print(f"    digest before repair: {digest_broken[:16]}")
print(f"    digest after  repair: {digest_repaired[:16]}")
print(f"    the digest moved: {digest_broken != digest_repaired}")

# Order-independent, so a repair is not required to reproduce the input's ordering - only
# its content. Reversing the rows must not move the digest.
print(f"    row order does not matter: "
      f"{canonical_hash(list(reversed(repaired))) == digest_repaired}")

# A hash you never re-check is decoration. The stored digest is re-checked against the
# table, and the stale digest is re-checked too - it must refuse, loudly.
report("verify_canonical against the repaired table",
       lambda: verify_canonical(repaired, digest_repaired, what="repaired blotter"))
report("verify_canonical against the stale pre-repair digest",
       lambda: verify_canonical(repaired, digest_broken, what="blotter"))

# --------------------------------------------------------------------------------------
rule("summary")
print(f"    {CHECKS_RUN} controls run, {CHECKS_FIRED} fired, "
      f"{CHECKS_RUN - CHECKS_FIRED} silent on the data they were given.")
print("    Every firing above named its mechanism; nothing listed possibilities.")
print("    Next: python3 test_parity.py (the fault matrix) and python3 demo.py (the money).")
