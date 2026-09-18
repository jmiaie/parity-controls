#!/usr/bin/env python3
"""pytest-collectable form of the parity fault matrix.

WHY THIS FILE EXISTS. `test_parity.py` is a SCRIPT: it calls `sys.exit()` at module scope and
defines zero `def test_*` functions, so `pytest` collects NOTHING from this repo and any
coverage tool reports zero. This file re-expresses the library's assertions as collectable
tests - the four controls against the fault matrix, the two behaviours added in this session
that had no runner-level test, and four pieces of public surface that were never exercised by
a test at all.

This file deliberately does NOT import `test_parity`: importing it would run its `sys.exit()`
during collection and take the whole session down with it.

Run:        cd /tmp/parity-work && python3 -m pytest tests/test_parity_pytest.py -q
No pytest:  python3 tests/test_parity_pytest.py   (direct invocation, same assertions)
"""
from __future__ import annotations

import os
import sys

# conftest.py puts the repo root on sys.path under pytest; a direct `python3 tests/...` run
# does not, because sys.path[0] is then `tests/`. Same root, whichever way the file is run.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from faults import (COLLAPSE, DUPLICATE, HEALTHY, RENAME, SHORT_WRITE, SUBSTITUTE, TRUNCATE,
                    load, present_keys, source_rows, substitute_key)
from parity import (ParityViolation, canonical_hash, cross_field, offered_present_parity,
                    share_anomaly, verify_canonical)

try:
    import pytest
except ImportError:  # bare container: keep the direct-invocation path below honest
    class _RaisesContext:
        def __init__(self, expected):
            self.expected = expected

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                raise AssertionError(f"DID NOT RAISE {self.expected.__name__}")
            return issubclass(exc_type, self.expected)

    class _PytestShim:
        """Just enough of `pytest.raises` for the `__main__` block at the bottom."""

        @staticmethod
        def raises(expected, *args, **kwargs):
            return _RaisesContext(expected)

    pytest = _PytestShim()  # type: ignore[assignment]


ROWS = source_rows()                       # 248 rows, both outcomes present
KEY = "(wallet,slug,outcome_index)"
LABEL = {0: ("Yes", "Up", "Over"), 1: ("No", "Down", "Under")}  # same fixture as test_parity.py


def _fires(fn) -> bool:
    """True when the control raised. The shape every assertion below is written against."""
    try:
        fn()
    except ParityViolation:
        return True
    return False


def _present_keys(fault):
    """The key set a verify pass would SELECT back, per fault.

    `present_keys()` models the WRITE. It does not model the page drop (TRUNCATE), so the
    truncated table's keys are read off the loaded rows instead. SUBSTITUTE is the
    count-preserving swap injected by `faults.substitute_key()`.
    """
    if fault == SUBSTITUTE:
        return substitute_key(present_keys(ROWS))
    if fault == TRUNCATE:
        return [(r["wallet"], r["slug"], r["outcome_index"]) for r in load(ROWS, fault).rows]
    return present_keys(ROWS, fault)


# --------------------------------------------------------------------------- #
# A. THE FOUR CONTROLS - fire on their fault, silent when healthy
# --------------------------------------------------------------------------- #

def test_write_boundary_key_set_form_fires_on_each_fault_and_is_silent_when_healthy():
    offered = present_keys(ROWS)
    for fault, want in ((HEALTHY, False), (COLLAPSE, True), (RENAME, True),
                        (TRUNCATE, True), (SHORT_WRITE, True)):
        present = _present_keys(fault)
        fired = _fires(lambda: offered_present_parity(offered, present, key=KEY))
        assert fired is want, f"{fault}: key-set parity fired={fired} want={want}"


def test_write_boundary_count_form_fires_only_on_the_blind_duplicate():
    # `distinct_keys` vs `present`: equal by construction on a keyed table EXCEPT when the
    # write has no key and the batch lands twice, which is what this form exists to see.
    for fault, want in ((HEALTHY, False), (DUPLICATE, True)):
        loaded = load(ROWS, fault)
        fired = _fires(lambda: offered_present_parity(loaded.distinct_keys, loaded.present,
                                                      where="rows vs distinct-key"))
        assert fired is want, f"{fault}: count form fired={fired} want={want}"


def test_blind_duplicate_is_invisible_to_the_key_set_form_by_construction():
    # The keyed writer DEDUPES, so 496 rows in the table are 248 keys and the key SET is
    # unchanged. The set form is not blind here - there is nothing in a key set to see. The
    # count form above is the detector; this test records why the set form stays silent.
    offered = present_keys(ROWS)
    assert set(present_keys(ROWS, DUPLICATE)) == set(offered)
    assert _fires(lambda: offered_present_parity(offered, present_keys(ROWS, DUPLICATE))) is False
    duplicated = load(ROWS, DUPLICATE)
    assert duplicated.present == 2 * duplicated.distinct_keys


def test_substitution_is_count_preserving_so_only_the_key_set_form_sees_it():
    keys = present_keys(ROWS)
    swapped = substitute_key(keys)
    assert len(swapped) == len(keys)          # N rows in, N rows land
    assert _fires(lambda: offered_present_parity(len(keys), len(swapped))) is False
    with pytest.raises(ParityViolation):
        offered_present_parity(keys, swapped)
    assert offered_present_parity(keys, present_keys(ROWS)) is True


def test_cross_field_is_silent_when_healthy_and_fires_on_collapse_and_rename():
    for fault, want in ((HEALTHY, False), (COLLAPSE, True), (RENAME, True)):
        loaded = load(ROWS, fault)
        pairs = [(r["outcome_index"], r["outcome"]) for r in loaded.rows]
        fired = _fires(lambda: cross_field(pairs, LABEL, name="outcome_index<->outcome"))
        assert fired is want, f"{fault}: cross-field fired={fired} want={want}"


def test_share_anomaly_reports_degenerate_on_the_collapsed_index_and_none_when_healthy():
    msg = share_anomaly([r["outcome_index"] for r in load(ROWS, COLLAPSE).rows],
                        name="outcome_index", min_n=100)
    assert msg is not None and "DEGENERATE" in msg
    assert share_anomaly([r["outcome_index"] for r in load(ROWS, HEALTHY).rows],
                         name="outcome_index", min_n=100) is None


def test_canonical_hash_is_order_independent_moves_on_collapse_and_ignores_float_drift():
    healthy = canonical_hash(load(ROWS, HEALTHY).rows)
    reversed_healthy = canonical_hash(list(reversed(load(ROWS, HEALTHY).rows)))
    collapsed = canonical_hash(load(ROWS, COLLAPSE).rows)
    assert healthy == reversed_healthy
    assert healthy != collapsed
    assert canonical_hash([{"x": 0.1 + 0.2}]) == canonical_hash([{"x": 0.3}])


# --------------------------------------------------------------------------- #
# B. THE BEHAVIOUR ADDED IN THIS SESSION - every control ships with a test
# --------------------------------------------------------------------------- #

def test_absent_column_does_not_hash_like_a_null_or_empty_one():
    # The bug this fixes: `r.get(c)` made a column that was never carried identical to one
    # carried empty, on the very write path this library exists to protect.
    missing = canonical_hash([{"a": 1}], columns=["a", "b"])
    assert missing != canonical_hash([{"a": 1, "b": None}], columns=["a", "b"])
    assert missing != canonical_hash([{"a": 1, "b": ""}], columns=["a", "b"])
    # None and "" are still one cell: a type or default change, not a move.
    assert (canonical_hash([{"a": 1, "b": None}], columns=["a", "b"])
            == canonical_hash([{"a": 1, "b": ""}], columns=["a", "b"]))
    # The sentinel is NUL-tagged and `_esc` escapes NUL in every real value, so no input can
    # forge an absent column.
    assert missing != canonical_hash([{"a": 1, "b": "\x00absent"}], columns=["a", "b"])


def test_without_columns_each_row_still_uses_its_own_keys():
    # columns=None is the pre-existing path: every key in the row renders, a key the row
    # never carried stays unrendered, and the existing equivalences are unchanged.
    assert canonical_hash([{"a": 1}]) == canonical_hash([{"a": 1}], columns=None)
    assert canonical_hash([{"a": None}], columns=None) == canonical_hash([{"a": ""}], columns=None)
    assert (canonical_hash([{"a": 1}], columns=None)
            != canonical_hash([{"a": 1, "b": None}], columns=None))
    # A row carrying both keys digests the same whether or not `columns=` restates them.
    assert (canonical_hash([{"a": 1, "b": None}], columns=["a", "b"])
            == canonical_hash([{"a": 1, "b": None}]))


def test_share_anomaly_separates_unpopulated_from_mostly_empty_and_below_the_floor():
    unpopulated = share_anomaly([""] * 1000, name="enriched_at", min_n=100)
    assert unpopulated is not None and "UNPOPULATED" in unpopulated

    mostly = share_anomaly([""] * 600 + ["x"] * 400, name="enriched_at", min_n=100)
    assert mostly is not None and "MOSTLY EMPTY" in mostly
    assert "UNPOPULATED" not in mostly

    assert share_anomaly([""] * 50 + [f"v{i}" for i in range(950)],
                         name="enriched_at", min_n=100) is None


def test_share_anomaly_default_min_empty_share_is_pinned_at_one_half():
    # The default knob (min_empty_share=0.5): 60% empty is MOSTLY EMPTY...
    msg = share_anomaly([""] * 600 + ["x"] * 400, name="c", min_n=100)
    assert msg is not None and "MOSTLY EMPTY" in msg
    assert "UNPOPULATED" not in msg
    # ...exactly one half still is, one row under it is silent, and the knob moves the line.
    assert "MOSTLY EMPTY" in (share_anomaly([""] * 500 + [f"v{i}" for i in range(500)],
                                            name="c", min_n=100) or "")
    assert share_anomaly([""] * 499 + [f"v{i}" for i in range(501)],
                         name="c", min_n=100) is None
    assert share_anomaly([""] * 600 + ["x"] * 400, name="c", min_n=100,
                         min_empty_share=0.75) is None


def test_verify_canonical_returns_true_on_the_success_path():
    rows = load(ROWS, HEALTHY).rows
    assert verify_canonical(rows, canonical_hash(rows), what="positions") is True
    # The raising path the script matrix already covered, kept here so one runner sees both.
    with pytest.raises(ParityViolation):
        verify_canonical(rows, canonical_hash(load(ROWS, COLLAPSE).rows), what="positions")


# --------------------------------------------------------------------------- #
# C. PREVIOUSLY-UNTESTED PUBLIC SURFACE
# --------------------------------------------------------------------------- #

def test_share_anomaly_multi_valued_false_does_not_report_a_near_constant_column():
    assert share_anomaly(["x"] * 1000, name="chain", multi_valued=False, min_n=100) is None
    # Same column, declared multi-valued: the DEGENERATE rule still works.
    msg = share_anomaly(["x"] * 1000, name="chain", multi_valued=True, min_n=100)
    assert msg is not None and "DEGENERATE" in msg


def test_cross_field_on_a_key_absent_from_the_mapping_raises_pinned_as_is():
    # PINNED AS-IS (2026-09-18): a key that is not in the mapping is treated as a row that
    # contradicts its domain, so cross_field raises ParityViolation instead of skipping the
    # pair. This records the current behaviour; it does not endorse it.
    with pytest.raises(ParityViolation):
        cross_field([(0, "Yes")], {}, name="outcome_index<->outcome")
    # A key that IS declared, and agrees with its domain, stays silent.
    assert cross_field([(0, "Yes")], LABEL, name="outcome_index<->outcome") is True


def test_offered_present_parity_returns_true_when_the_key_sets_are_equal():
    assert offered_present_parity({1, 2, 3}, {3, 2, 1}) is True
    assert offered_present_parity(present_keys(ROWS), present_keys(ROWS)) is True


def test_parity_violation_is_an_assertion_error_subclass():
    assert issubclass(ParityViolation, AssertionError)
    # So plain tooling treats a fired control as a failure, not as an unhandled exception.
    with pytest.raises(AssertionError):
        raise ParityViolation("a fired control must read as a test failure")


# --------------------------------------------------------------------------- #
# Direct invocation, for a container with no pytest installed.
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    _cases = [(name, fn) for name, fn in list(globals().items())
              if name.startswith("test_") and callable(fn)]
    _failed = []
    for _name, _fn in _cases:
        try:
            _fn()
        except BaseException as exc:  # noqa: BLE001 - the summary is the deliverable here
            _failed.append(_name)
            print(f"  [FAIL] {_name}: {type(exc).__name__}: {exc}")
        else:
            print(f"  [PASS] {_name}")
    print(f"\n{len(_cases) - len(_failed)}/{len(_cases)} passed"
          + (f"; FAILURES: {', '.join(_failed)}" if _failed else " - ALL PASS"))
    sys.exit(1 if _failed else 0)
