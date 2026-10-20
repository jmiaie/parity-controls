"""Great Expectations adapter - SKELETON. Extra: pip install 'parity-controls[great-expectations]'.

Interface (see docs/ROADMAP.md, "Next", for what is built and what is not):

  expect_offered_present_parity(offered, present, ...) -> result dict   WORKS without GX
  expect_cross_field(pairs, mapping, ...) -> result dict                WORKS without GX
  expect_canonical_hash(rows, expected, ...) -> result dict             WORKS without GX
  register_expectations()                                               needs GX; NOT IMPLEMENTED

The `expect_*` functions run the parity control and return a plain dict shaped like a GX
validation result - `{"success": bool, "expectation_type": str, "result": {...}}` - so a
pipeline that already routes GX-style results (to a data doc, a Slack action, a gate) can
route these the same way. They are NOT GX `Expectation` subclasses and do not appear in a GX
suite; that is what `register_expectations` is for, and it is a stub until the roadmap item
lands. It raises, it never returns a fake pass.

A ParityViolation becomes `success: False` with the control's own message, which names the
mechanism. A TypeError (caller misuse, e.g. a string passed as a key set) is NOT turned into a
failed expectation: misuse is not a data defect, and reporting it as one sends the reader to
the data instead of the call site.
"""
from __future__ import annotations

from parity import ParityViolation, canonical_hash, cross_field, offered_present_parity
from parity_integrations import require

ROADMAP = "docs/ROADMAP.md, Next: 'Great Expectations adapter - register_expectations'"


def _result(expectation_type: str, thunk, **observed) -> dict:
    try:
        thunk()
    except ParityViolation as e:
        return {"success": False, "expectation_type": expectation_type,
                "result": {"message": str(e), **observed}}
    return {"success": True, "expectation_type": expectation_type,
            "result": {"message": None, **observed}}


def expect_offered_present_parity(offered, present, *, where: str = "write boundary",
                                  key: str | None = None) -> dict:
    return _result("expect_offered_present_parity",
                   lambda: offered_present_parity(offered, present, where=where, key=key))


def expect_cross_field(pairs, mapping, *, name: str = "cross-field") -> dict:
    pairs = list(pairs)  # a generator would be consumed before the count below
    return _result("expect_cross_field", lambda: cross_field(pairs, mapping, name=name),
                   element_count=len(pairs))


def expect_canonical_hash(rows, expected: str, *, columns=None, what: str = "dataset") -> dict:
    rows = list(rows)
    got = canonical_hash(rows, columns)

    def check():
        if got != expected:
            raise ParityViolation(f"{what}: canonical hash moved {expected[:16]} -> {got[:16]}")

    return _result("expect_canonical_hash", check, observed_value=got, element_count=len(rows))


def register_expectations():
    """Register the controls as GX custom Expectations. NOT BUILT.

    Raises MissingDependency without great_expectations; with it, NotImplementedError until
    the roadmap item lands.
    """
    require("great_expectations", "great-expectations")
    raise NotImplementedError(
        f"register_expectations is a skeleton: it would expose the parity controls as GX "
        f"custom Expectations. Tracked in {ROADMAP}."
    )
