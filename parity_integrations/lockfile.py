"""Freeze and verify: canonical digests for the CSV files under a path, stored in a lockfile.

    parity-controls freeze data/ --lock parity.lock.json     # record what the files hold
    parity-controls verify data/ --lock parity.lock.json     # refuse if anything moved

(or `python -m parity_integrations.lockfile ...` from a checkout, with no install).

This is `canonical_hash` + `verify_canonical` + `offered_present_parity` applied to files at
rest, which is the flow `action.yml` runs in CI. Stdlib only, like the core.

What `verify` refuses, each by name:

  * a file in the lockfile that is no longer under the path, or a new file that is not in the
    lockfile - `offered_present_parity` over the two file sets, so a rename reads as one file
    missing and one file unwanted, never as "same count, all good";
  * a file whose canonical digest moved - row order and column order do not move it (that is
    `canonical_hash`'s contract), a changed cell, an added row or a dropped row does;
  * a ragged row (more or fewer cells than the header) or a duplicated header name, at freeze
    AND at verify time. `csv.DictReader` silently collapses a duplicated header into one key
    and files extra cells under a `None` key, which is the field-name collapse this library
    exists to name, one layer down.

Blind spots, named here rather than discovered later:

  * Cells are hashed as TEXT, as the file stores them: `1.0` and `1.00` are different files.
    That is deliberate - this checks the durable artifact, not a typed reading of it.
  * A file is read whole into memory to hash it (`canonical_hash` sorts its lines). Fine for
    seeds, books and fixtures; not yet for multi-GB extracts. See docs/ROADMAP.md (Later).
  * The lockfile is only as trustworthy as the place it is stored. A writer who can rewrite
    both the data and the lockfile in one commit passes `verify`; review the lockfile diff.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from parity import ParityViolation, canonical_hash, offered_present_parity

LOCK_VERSION = 1
DEFAULT_PATTERN = "*.csv"


def read_csv_rows(path: Path) -> tuple[list[str], list[dict]]:
    """Header and rows of one CSV file, refusing the two shapes DictReader would collapse."""
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return [], []
        dupes = sorted({c for c in header if header.count(c) > 1})
        if dupes:
            raise ParityViolation(
                f"{path}: duplicated header {dupes}. A dict-based reader keeps one of them and "
                f"drops the other column's values without a word - a field-name collapse."
            )
        rows = []
        for line_no, cells in enumerate(reader, start=2):
            if not cells:
                continue  # csv.reader yields [] for a blank line; DictReader skips it too
            if len(cells) != len(header):
                raise ParityViolation(
                    f"{path}:{line_no}: ragged row - {len(cells)} cells under a {len(header)}-"
                    f"column header. Extra cells would land under no column, missing ones "
                    f"would read as empty; neither is the data that was written."
                )
            rows.append(dict(zip(header, cells)))
    return header, rows


def digest_file(path: Path) -> dict:
    """Lockfile entry for one file: digest, row count and header (the last two for humans)."""
    header, rows = read_csv_rows(path)
    return {"digest": canonical_hash(rows, columns=header), "rows": len(rows), "columns": header}


def _files(root: Path, pattern: str) -> dict[str, Path]:
    """Relative POSIX path -> file. A single file is its own set of one."""
    if root.is_file():
        return {root.name: root}
    if not root.is_dir():
        raise FileNotFoundError(f"{root}: no such file or directory")
    return {p.relative_to(root).as_posix(): p for p in sorted(root.rglob(pattern)) if p.is_file()}


def freeze(root: str | os.PathLike, pattern: str = DEFAULT_PATTERN) -> dict:
    """Digest every file matching `pattern` under `root`. Returns the lockfile document."""
    files = _files(Path(root), pattern)
    if not files:
        # An empty lock would make every later `verify` pass on an empty directory - the
        # "dead fetcher offered nothing" blind spot, frozen into a file. Refuse it here.
        raise ParityViolation(f"{root}: no files match {pattern!r}; refusing to freeze an empty set")
    return {
        "version": LOCK_VERSION,
        "pattern": pattern,
        "files": {rel: digest_file(p) for rel, p in files.items()},
    }


def verify(root: str | os.PathLike, lock: dict) -> bool:
    """Re-digest and compare against `lock`. Raises ParityViolation naming EVERY difference."""
    if lock.get("version") != LOCK_VERSION:
        raise ValueError(f"lockfile version {lock.get('version')!r}; this reader knows {LOCK_VERSION}")
    pattern = lock.get("pattern", DEFAULT_PATTERN)
    files = _files(Path(root), pattern)
    locked = lock.get("files", {})
    problems = []
    try:
        offered_present_parity(set(locked), set(files), where=f"{root} file set")
    except ParityViolation as e:
        problems.append(str(e))
    for rel in sorted(set(locked) & set(files)):
        try:
            got = digest_file(files[rel])["digest"]
        except ParityViolation as e:
            problems.append(str(e))
            continue
        want = locked[rel]["digest"]
        if got != want:
            problems.append(f"{rel}: canonical hash moved {want[:16]} -> {got[:16]}")
    if problems:
        raise ParityViolation(f"{len(problems)} problem(s):\n  " + "\n  ".join(problems))
    return True


def main(argv: list[str] | None = None) -> int:
    """CLI. Exit 0 = verified/frozen, 1 = a control refused, 2 = usage error (argparse's code)."""
    ap = argparse.ArgumentParser(prog="parity-controls", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, text in (("freeze", "write the lockfile"), ("verify", "refuse if anything moved")):
        p = sub.add_parser(name, help=text)
        p.add_argument("path", help="a CSV file, or a directory searched recursively")
        p.add_argument("--lock", default="parity.lock.json", help="lockfile (default: %(default)s)")
        if name == "freeze":
            p.add_argument("--pattern", default=DEFAULT_PATTERN,
                           help="glob under a directory (default: %(default)s)")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "freeze":
            doc = freeze(args.path, args.pattern)
            Path(args.lock).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8")
            print(f"FROZEN {len(doc['files'])} file(s) -> {args.lock}")
        else:
            lock = json.loads(Path(args.lock).read_text(encoding="utf-8"))
            verify(args.path, lock)
            print(f"VERIFIED {len(lock['files'])} file(s) against {args.lock}")
    except ParityViolation as e:
        print(f"PARITY VIOLATION: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
