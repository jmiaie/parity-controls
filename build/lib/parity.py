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
import math

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


def offered_present_parity(offered, present, *, where: str = "write boundary",
                           key: str | None = None, sample: int = 3) -> bool:
    """The write boundary. Fires on collapse, rename, truncation, duplication, substitution.

    Prefer the KEY COLLECTIONS. It then compares key SETS, which is the only form that
    catches a count-preserving substitution - N rows in, N rows land, one key swapped on
    the way. Equal counts are not equal content.

    If you pass COUNTS they must be counts of DISTINCT KEYS, never of raw rows. A page that
    repeats a key is not a defect - the writer dedupes it - but it makes raw rows outnumber
    distinct keys, so a rows-vs-keys comparison fires on healthy data. A control that cries
    wolf gets muted, and a muted control is worse than no control. This was measured before
    it was assumed: 8,411 rows across 3 wallets carried 0 repeated keys, so the wrong form
    would have passed every test here and waited for the first paging change to alarm.

    One comparison, so there is no batch too small to run it on.

    CALL THIS WHEN THE WRITE FAILS, NOT ONLY WHEN IT SUCCEEDS. A worker that dies between
    its DELETE and its INSERT leaves offered=N, present=0, and a check wired only to the
    success path reports nothing at all:

        try: write(batch)
        finally: offered_present_parity(offered_keys, present_keys())

    Four blind spots, named here rather than discovered by a customer:

      * `offered` must come from the RAW payload, before any field-name mapping. Derive it
        with the same mapper that the writer uses and the defect is baked into both sides,
        so the comparison passes trivially - the bug erases its own evidence.
      * Counts must be DISTINCT KEYS, not raw rows (see above). The set form cannot make
        this mistake; the integer form can, and does it silently.
      * Excluding rows from the check deletes the check for exactly the rows that failed.
        A partial or short-fetch batch still gets asserted, with the known delta expected.
      * Set comparison catches a substitution but not two compensating substitutions.
        Hash the canonical form (see canonical_hash) when that matters.
      * EMPTY PASSES. offered=0, present=0 passes, and `[]` vs `[]` passes, so this control
        cannot tell "nothing was offered" from "a dead fetcher offered nothing". It is not
        made to raise on empty because a legitimately quiet night would then alarm, which is
        how a control gets muted; the caller owns that distinction. The live adapter makes it
        explicitly, per source, at the parse boundary.
    """
    if isinstance(offered, int) and isinstance(present, int):
        if offered != present:
            raise ParityViolation(
                f"{where}: offered={offered} present={present} delta={present - offered:+d}"
                + (f" key={key}" if key else "")
                + ". A keyed write that collides silently looks exactly like a successful one."
            )
        return True

    if isinstance(offered, (str, bytes)) or isinstance(present, (str, bytes)):
        # MEASURED: `O("abc", "cba")` returned True. A string iterates into characters, so
        # a single key passed on each side is compared as two character sets - a pass when
        # it must refuse. Named, not guessed: pass `{key}` or `[key]`.
        raise TypeError(
            f"{where}: a string is a sequence of characters, not a collection of keys; pass a "
            f"set or list of keys (got {type(offered).__name__} and {type(present).__name__})"
        )

    try:
        o, p = set(offered), set(present)
    except TypeError as e:
        # Caller misuse, not a data defect, so it stays a TypeError - but the default
        # message ("'int' object is not iterable") sends the reader to the wrong place.
        raise TypeError(
            f"{where}: offered/present must be BOTH counts or BOTH collections of hashable "
            f"keys; got {type(offered).__name__} and {type(present).__name__} ({e})"
        ) from e
    if o != p:
        missing, extra = sorted(o - p, key=repr), sorted(p - o, key=repr)
        raise ParityViolation(
            f"{where}: offered={len(o)} present={len(p)} keys"
            + (f" key={key}" if key else "")
            + f"; {len(missing)} never landed {missing[:sample]}, "
            f"{len(extra)} arrived unwanted {extra[:sample]}. Equal counts with a different "
            f"key set is a substitution, not a load."
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

    MEASURED BLIND SPOT, documented rather than discovered later: in the incident the
    dominant value sat at share 0.999947 - one value's worth of margin under a 0.999
    trigger - and the post-fix maximum for the same family is 0.521829. Calibrate this
    threshold from the mechanism - what fraction of rows can legitimately share a value -
    never from the incident that motivated it. (An earlier draft of this docstring quoted
    0.9911; the reviewer who owns the measurement has none that yields it, so it is gone.)

    An all-empty column is reported as UNPOPULATED, not DEGENERATE: an empty string is
    one value, so a cardinality rule would call 12 legitimately-empty columns violations
    on a healthy file (measured: 18 of 44 columns on a real lead table). Different defect,
    different message, different fix.
    """
    values = list(values)  # any iterable; a generator has no len() and took the caller down
    n = len(values)
    if n == 0 or n < min_n:  # n == 0 with min_n == 0 must not reach most_common()[0]
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


def _esc(s: str) -> str:
    """A value must not be able to impersonate structure.

    MEASURED: without this, `{"a": "x", "b": "y"}` and `{"a": "x\x1fb=y"}` produced the same
    digest, and a value carrying a newline can merge two rows into one line. Escaping is
    identity on clean data, so digests taken before this change still reproduce.

    NUL is escaped too, which costs nothing on real data and buys a reserved space: after
    `_esc`, no text can contain a raw NUL, so `_cell` can tag a non-finite float with one and
    no input can forge that tag. The column name needs a second escape (`_key`) because `=`
    is the other half of the row encoding - without it `{"a=x": 1}` and `{"a": "x=1"}` hashed
    alike, which is this same defect one layer in.
    """
    return (s.replace("\\", "\\\\").replace("\x00", "\\x00").replace("\x1f", "\\x1f")
             .replace("\n", "\\n").replace("\r", "\\r"))


def _key(s: str) -> str:
    """Column names may not carry the `=` either - the first raw `=` in a row is the delimiter."""

    return _esc(s).replace("=", "\\=")


def _cell(v) -> str:
    if v is None:
        s = ""
    elif isinstance(v, float):
        # An integral float prints without its decimal tail so that int 1 and float 1.0
        # agree. A column that comes back 1.0 instead of 1 is a type change, not a move,
        # and a digest that calls it a move gets muted.
        if not math.isfinite(v):
            # MEASURED: `f"{nan:.6f}"` is the string "nan", so float nan and the string "nan"
            # in one column hashed alike - two datasets, one digest. Tagged with a raw NUL
            # instead of raising: refusing here would give every live pipeline a new way to
            # go red, and a control that cries wolf gets muted.
            return "\x00" + ("nan" if v != v else ("+inf" if v > 0 else "-inf"))
        s = str(int(v)) if v.is_integer() else f"{v:.6f}"  # kill repr drift: 0.1+0.2 == 0.3
    else:
        s = str(v)
    return _esc(s)


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
        lines.append("\x1f".join(f"{_key(str(c))}={_cell(r.get(c))}" for c in use))
    lines.sort()
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def verify_canonical(rows, expected: str, *, what: str = "dataset", columns=None) -> bool:
    """Re-hash and compare. A hash you never re-check is decoration."""
    got = canonical_hash(rows, columns)
    if got != expected:
        raise ParityViolation(f"{what}: canonical hash moved {expected[:16]} -> {got[:16]}")
    return True
