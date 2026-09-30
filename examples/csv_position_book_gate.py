#!/usr/bin/env python3
"""Financial-pipeline adapter example: a CSV position-book write gate.

    python3 examples/csv_position_book_gate.py

Beyond the toy blotter in ``quickstart.py`` and the dollar demo in ``demo.py``, this is the
shape a desk would actually wire: rows arrive from a source, a loader writes a CSV position
book, and **nothing lands on disk** unless the write boundary stays armed.

Stdlib only (``csv``, ``tempfile``). No database, no network, no host-absolute paths.

Two passes:

1. **Healthy** — offered keys land, side agrees with position, freeze digest is stored and
   re-checked.
2. **Collapsed** — a field-name drift forces ``side`` to its default; the gate refuses and
   the previous night's book is byte-identical afterwards.

A boundary that cannot refuse is not armed. The refusal is the product.
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parity import (  # noqa: E402
    ParityViolation,
    canonical_hash,
    cross_field,
    offered_present_parity,
    share_anomaly,
    verify_canonical,
)

# --------------------------------------------------------------------------------------
# Source blotter: what the upstream system offered. Keys are trade_id; side and position
# are one fact spelled two ways — the pair a field-name drift cannot hide behind a default.
# --------------------------------------------------------------------------------------
SOURCE_ROWS = [
    {"trade_id": "P-2401", "symbol": "AAPL", "side": "buy", "position": "long", "qty": 100, "px": 190.25},
    {"trade_id": "P-2402", "symbol": "MSFT", "side": "sell", "position": "short", "qty": 50, "px": 420.10},
    {"trade_id": "P-2403", "symbol": "NVDA", "side": "buy", "position": "long", "qty": 25, "px": 880.00},
    {"trade_id": "P-2404", "symbol": "AAPL", "side": "sell", "position": "short", "qty": 40, "px": 191.00},
    {"trade_id": "P-2405", "symbol": "SPY", "side": "buy", "position": "long", "qty": 200, "px": 512.35},
    {"trade_id": "P-2406", "symbol": "QQQ", "side": "sell", "position": "short", "qty": 75, "px": 448.20},
]

SIDE_DOMAIN = {"buy": ("long",), "sell": ("short",)}
COLUMNS = ["trade_id", "symbol", "side", "position", "qty", "px"]


def book_notional(rows: list[dict]) -> float:
    """Gross notional the desk would mark — used only to price a refused write."""
    return sum(float(r["qty"]) * float(r["px"]) for r in rows)


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def as_csv_cells(rows: list[dict]) -> list[dict]:
    """What ``csv.DictWriter`` will actually persist: every cell as text.

    Digests must cover the durable artifact. Hashing typed in-memory rows and then
    re-checking the CSV re-read is a false alarm waiting to happen (``100`` vs ``"100"``).
    """
    return [{c: "" if r.get(c) is None else str(r.get(c)) for c in COLUMNS} for r in rows]


def gate_write(offered: list[dict], present: list[dict], *, where: str) -> str:
    """Arm the four controls at the CSV write boundary. Returns the freeze digest.

    Raising controls abort before the caller is allowed to replace the on-disk book.
    ``share_anomaly`` is WARN-only and prints; it never blocks the write by itself.
    The digest is over CSV-shaped cells so a re-read of the file can verify it.
    """
    offered_keys = {r["trade_id"] for r in offered}
    present_keys = {r["trade_id"] for r in present}
    offered_present_parity(offered_keys, present_keys, where=where, key="trade_id")

    pairs = [(r["side"], r["position"]) for r in present]
    cross_field(pairs, SIDE_DOMAIN, name="side<->position")

    warn = share_anomaly([r["side"] for r in present], name="side", min_n=len(present))
    if warn:
        print(f"  WARN  {warn}")

    durable = as_csv_cells(present)
    digest = canonical_hash(durable, columns=COLUMNS)
    verify_canonical(durable, digest, what=where, columns=COLUMNS)
    return digest


def run_pass(label: str, offered: list[dict], present: list[dict], book_path: Path,
             previous_bytes: bytes | None) -> bytes | None:
    """Attempt a gated write. On refusal, leave the previous book untouched."""
    print()
    print(f"=== {label} ===")
    print(f"  offered={len(offered)}  present={len(present)}  "
          f"notional_present={book_notional(present):,.2f}")
    try:
        digest = gate_write(offered, present, where=f"position book:{book_path.name}")
    except ParityViolation as exc:
        print(f"  GATE REFUSED  {exc}")
        if previous_bytes is not None and book_path.exists():
            after = book_path.read_bytes()
            print(f"  previous book untouched: {after == previous_bytes}")
        return previous_bytes

    write_csv(book_path, present)
    stored = book_path.read_bytes()
    # Re-read and re-verify: a digest that is only computed once is decoration.
    reread = read_csv(book_path)
    verify_canonical(reread, digest, what=f"re-read {book_path.name}", columns=COLUMNS)
    print(f"  GATE OK  digest={digest[:16]}  rows_on_disk={len(reread)}")
    return stored


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="parity-posbook-") as tmp:
        book = Path(tmp) / "position_book.csv"

        # Night 0 seed: a prior good book, so a refusal has something to protect.
        seed = list(SOURCE_ROWS)
        write_csv(book, seed)
        previous = book.read_bytes()
        print(f"seeded prior book at {book} ({len(seed)} rows, "
              f"notional={book_notional(seed):,.2f})")

        # Pass 1 — healthy: present matches offered.
        previous = run_pass("healthy load", SOURCE_ROWS, list(SOURCE_ROWS), book, previous)

        # Pass 2 — collapse: reader used the wrong field name; every side becomes the
        # default "buy" while position still carries the truth. Counts still match.
        collapsed = [dict(r, side="buy") for r in SOURCE_ROWS]
        previous = run_pass("field-name drift (side forced to default)", SOURCE_ROWS,
                            collapsed, book, previous)

        # Pass 3 — one key never landed (true collapse of offered vs present).
        missing = [r for r in SOURCE_ROWS if r["trade_id"] != "P-2404"]
        run_pass("one trade_id never landed", SOURCE_ROWS, missing, book, previous)

    print()
    print("Done. Raising controls refused the broken writes; the healthy write stored a")
    print("freeze digest and re-checked it on re-read. Next: wire this pattern at your")
    print("own CSV/parquet boundary, or see adapters/surplus-gate-nightly.sh for a live")
    print("nightly wrapper shape.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
