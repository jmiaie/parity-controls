"""parity - write-boundary integrity for financial data pipelines.

Four controls, in the order they are worth adopting:

  1. offered_present_parity   the write boundary. Fires on collapse, rename, truncate, duplicate.
  2. cross_field              two columns that describe the same fact must agree.
  3. share_anomaly            near-constant value in a declared multi-valued column (WARN only).
  4. canonical_hash           makes "the data did not move" a checkable claim, not a sentence.

Rules this library holds itself to:

  * A control that has never been observed to fail is not a control. Every function here
    ships with a fault in faults.py that makes it fire, and test_parity.py fails if any
    control goes quiet.
  * Silent when healthy; when it fires it names the mechanism. An alert that lists
    possibilities gets muted, and a muted alert is worse than no alert.
  * Blind spots are documented on the function, not discovered later by a customer.

Rejected on purpose: rows vs COUNT(DISTINCT key) as a collapse detector. Where the
natural key is the primary key, INSERT OR REPLACE erases the violation at write time,
so the two counts are equal BY CONSTRUCTION and the check cannot disagree with itself.
That is proven, not asserted - see test_key_parity_cannot_see_collapse in test_parity.py.
"""
from __future__ import annotations

import collections
import hashlib

__all__ = [
    "ParityViolation",
    "offered_present_parity",
    "cross_field",
    "share_anomaly",
    "canonical_hash",
    "verify_canonical",
]


class ParityViolation(AssertionError):
    """Raised when a control fires. An AssertionError so plain tooling treats it as failure."""


def offered_present_parity(offered: int, present: int, *, where: str = "write boundary",
                           key: str | None = None) -> bool:
    """The write boundary. Fires on field collapse, field rename, truncation AND duplication.

    offered = rows the source handed you. present = rows the table holds afterwards.
    The two numbers come from different places, which is exactly why this check can
    disagree with itself and a key-count check cannot. It costs one integer comparison,
    so there is no batch too small to run it on.
    """
    if offered != present:
        raise ParityViolation(
            f"{where}: offered={offered} present={present} delta={present - offered:+d}"
            + (f" key={key}" if key else "")
            + ". A keyed write that collides silently looks exactly like a successful one."
        )
    return True


def cross_field(pairs, mapping, *, name: str = "cross-field", sample: int = 3) -> bool:
    """Two columns that must agree. `pairs` = iterable of (a, b); b must be in mapping[a].

    This is the mechanism-level detector for the collapse family: when a field-name drift
    forces a column to a default, the other column describing the same fact still carries
    the truth, so the disagreement is arithmetic rather than statistical - no threshold,
    no N floor, no documented domain to guess at.
    """
    bad = [(a, b) for a, b in pairs if b not in mapping.get(a, ())]
    if bad:
        raise ParityViolation(
            f"{name}: {len(bad)} rows contradict their declared domain; e.g. {bad[:sample]}"
        )
    return True


def share_anomaly(values, *, name: str, multi_valued: bool = True, min_n: int = 1000,
                  max_share: float = 0.999) -> str | None:
    """WARN-only: returns a message, never raises. Two different defects, two messages.

    MEASURED BLIND SPOT, documented rather than discovered later: a real orphan family
    sat at max-share 0.9911 and slipped under a 0.999 trigger. Calibrate this threshold
    from the mechanism - what fraction of rows can legitimately share a value - never
    from the incident that motivated it.

    An all-empty column is reported as UNPOPULATED, not DEGENERATE: an empty string is
    one value, so a cardinality rule would call 12 legitimately-empty columns violations
    on a healthy file (measured: 18 of 44 columns on a real lead table). Different defect,
    different message, different fix.
    """
    n = len(values)
    if n < min_n:
        return None
    top, count = collections.Counter(values).most_common(1)[0]
    share = count / n
    if top == "" or top is None:
        return (f"{name}: UNPOPULATED - {share:.4f} of {n} rows are empty. Nothing wrote this "
                f"column; that is a pipeline fault, not a distribution.")
    if multi_valued and share >= max_share:
        return (f"{name}: DEGENERATE - one value ({top!r}) is {share:.6f} of {n} rows. "
                f"Two candidate causes: a narrow batch slice, or a field-name drift forcing a "
                f"default. Check the source field spelling before the data.")
    return None


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6f}"  # kill repr drift: 0.1 + 0.2 must not change the hash
    return str(v)


def canonical_hash(rows, columns=None) -> str:
    """sha256 over a row set: order-independent and float-stable.

    This is how "the data did not move" stops being a claim and becomes a check. Hash the
    canonical form, store the digest, re-hash around any repair or rebuild. Rows are
    sorted, columns are sorted, floats are quantised.
    """
    cols = None if columns is None else sorted(columns)
    lines = []
    for r in rows:
        use = cols if cols is not None else sorted(r.keys())
        lines.append("\x1f".join(f"{c}={_cell(r.get(c))}" for c in use))
    lines.sort()
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def verify_canonical(rows, expected: str, *, what: str = "dataset", columns=None) -> bool:
    """Re-hash and compare. A hash you never re-check is decoration."""
    got = canonical_hash(rows, columns)
    if got != expected:
        raise ParityViolation(f"{what}: canonical hash moved {expected[:16]} -> {got[:16]}")
    return True
