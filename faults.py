"""Fault injection. A control is not installed until a fault has made it fire.

Eight scenarios - seven faults and one healthy shape that breaks a naive check:

  HEALTHY     nothing is wrong            -> every control must stay SILENT
  COLLAPSE    the reader used the wrong field name (snake_case) on a camelCase API,
              so the default 0 lands in a column that should be binary and the key
              tuple loses a dimension
  RENAME      the field is gone entirely, so even the camelCase fallback misses
  DUPLICATE   the write has no key and the batch lands twice - the mirror of collapse
  TRUNCATE    a page never lands
  SUBSTITUTE  N rows in, N rows land, one key swapped on the way (count-preserving)
  SHORT_WRITE the worker died between its DELETE and its INSERT: offered N, present 0
  REPEAT_KEY  a page repeats a key. NOT A FAULT - the writer dedupes and the table is
              right - but it breaks a boundary check that counts raw rows. See
              repeat_key_page().

HEALTHY gets skipped in real reviews, and a control that is silent on a fault AND
never exercised on healthy data has not been tested - it has merely never spoken.
SUBSTITUTE, SHORT_WRITE and REPEAT_KEY exist because a reviewer named them as gaps;
the count-only write-boundary form passed the first two and false-fired on the third.
"""
from __future__ import annotations

import random
from collections import namedtuple

HEALTHY, COLLAPSE, RENAME, DUPLICATE, TRUNCATE, SUBSTITUTE, SHORT_WRITE, REPEAT_KEY = (
    "HEALTHY", "COLLAPSE", "RENAME", "DUPLICATE", "TRUNCATE", "SUBSTITUTE", "SHORT_WRITE",
    "REPEAT_KEY")

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
    if fault == SHORT_WRITE:
        return Loaded([], 0, 0)  # died between the DELETE and the INSERT: nothing is there
    base = rows[: len(rows) // 2] if fault == TRUNCATE else list(rows)
    table = keyed_write(base, HEALTHY if fault == DUPLICATE else fault)
    if fault == DUPLICATE:
        present = len(base) * 2  # a write with no key lands the batch twice
        return Loaded(list(table.values()) * 2, present, len(table))
    return Loaded(list(table.values()), len(table), len(table))


PRICE = {0: 0.62, 1: 0.38}  # a mark per outcome index: this is where a collapse costs money


def present_keys(rows, fault=HEALTHY):
    """The key set the table ends up holding - what a verify pass would SELECT back."""
    if fault == SHORT_WRITE:
        return []  # died between the DELETE and the INSERT: everything in flight is gone
    return list(keyed_write(rows, fault).keys())


def substitute_key(keys):
    """Count-preserving corruption: one distinct key dropped, one stranger added.

    The counts agree, the loader reports success, and a row is wrong. Only a key-SET
    comparison sees it - the count-only write boundary passed this fault.
    """
    return list(keys[:-1]) + [("0x" + "de" * 20, "market-ghost", 0)]


def repeat_key_page(rows, extra: int = 2):
    """A page that repeats a key - normal for an API paging on a non-unique sort.

    Nothing is wrong here: the writer dedupes and the table is correct. But the page has
    more ROWS than the table has DISTINCT KEYS, so a boundary check comparing raw rows
    against present rows fires on healthy data. Named by a reviewer who built it and then
    measured the assumption instead of resting on it (8,411 rows, 3 wallets, 0 repeats -
    so the wrong form passes today and waits for the first paging change to alarm).
    """
    return list(rows) + list(rows[:extra])


def nav(rows) -> float:
    """Position value of a row set. Both sides of a market are not worth the same."""
    return round(sum(r["stake"] * PRICE[r["outcome_index"]] for r in rows), 2)
