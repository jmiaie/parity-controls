"""Fault injection. A control is not installed until a fault has made it fire.

Five scenarios, and the first one is the one that matters:

  HEALTHY     nothing is wrong            -> every control must stay SILENT
  COLLAPSE    the reader used the wrong field name (snake_case) on a camelCase API,
              so the default 0 lands in a column that should be binary and the key
              tuple loses a dimension
  RENAME      the field is gone entirely, so even the camelCase fallback misses
  DUPLICATE   the write has no key and the batch lands twice - the mirror of collapse
  TRUNCATE    a page never lands

HEALTHY gets skipped in real reviews, and a control that is silent on a fault AND
never exercised on healthy data has not been tested - it has merely never spoken.
"""
from __future__ import annotations

import random
from collections import namedtuple

HEALTHY, COLLAPSE, RENAME, DUPLICATE, TRUNCATE = (
    "HEALTHY", "COLLAPSE", "RENAME", "DUPLICATE", "TRUNCATE")

Loaded = namedtuple("Loaded", "rows present distinct_keys")


def source_rows(n_wallets: int = 40, n_slugs: int = 6, seed: int = 7):
    """Rows exactly as a camelCase API returns them, with BOTH outcomes present.

    The twin rows are the point: any wallet that holds both sides of a market is the
    row that disappears when a key dimension collapses.
    """
    rnd = random.Random(seed)
    rows = []
    for w in range(n_wallets):
        wallet = "0x%040x" % w
        for s in range(rnd.randint(2, n_slugs)):
            slug = f"market-{w}-{s}"
            stake = round(rnd.uniform(5, 500), 2)
            for label, idx in (("Yes", 0), ("No", 1)):
                if rnd.random() < 0.75:
                    rows.append({"wallet": wallet, "slug": slug, "outcomeIndex": idx,
                                 "outcome": label, "stake": stake})
    return rows


def read_index(row, fault):
    """What the reader extracts. The production defect lived on these two lines."""
    if fault == COLLAPSE:
        return {"outcome_index": row.get("outcome_index", 0)}  # snake_case on a camelCase API
    if fault == RENAME:
        return {"outcome_index": row.get("outcomeIdx", 0)}     # gone entirely
    return {"outcome_index": row["outcomeIndex"]}


def keyed_write(rows, fault=HEALTHY):
    """INSERT OR REPLACE keyed on (wallet, slug, outcome_index)."""
    table = {}
    for r in rows:
        extra = read_index(r, fault)
        oi = extra.get("outcome_index", 0)  # <- an absent field becomes 0, silently
        table[(r["wallet"], r["slug"], oi)] = {**r, **extra, "outcome_index": oi}
    return table


def load(rows, fault=HEALTHY) -> Loaded:
    """Load a batch and report what a loader would report: rows, present, distinct keys."""
    base = rows[: len(rows) // 2] if fault == TRUNCATE else list(rows)
    table = keyed_write(base, HEALTHY if fault == DUPLICATE else fault)
    if fault == DUPLICATE:
        present = len(base) * 2  # a write with no key lands the batch twice
        return Loaded(list(table.values()) * 2, present, len(table))
    return Loaded(list(table.values()), len(table), len(table))


PRICE = {0: 0.62, 1: 0.38}  # a mark per outcome index: this is where a collapse costs money


def nav(rows) -> float:
    """Position value of a row set. Both sides of a market are not worth the same."""
    return round(sum(r["stake"] * PRICE[r["outcome_index"]] for r in rows), 2)
