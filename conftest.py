"""Make the library importable when pytest runs from the repo root.

The library is a single flat module (`parity.py`), not an installed package in a bare
checkout, so the repo root has to be on sys.path before any test imports `parity`.
pytest inserts the directory containing the nearest conftest.py, which is this one.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
