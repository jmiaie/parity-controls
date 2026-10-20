"""Integrations around the zero-dependency `parity` core.

  lockfile             freeze/verify canonical digests of CSV files at rest (stdlib only;
                       the flow `action.yml` runs in CI)
  dbt                  dbt adapter skeleton - extra: pip install 'parity-controls[dbt]'
  great_expectations   Great Expectations adapter skeleton - extra: '[great-expectations]'

The core never imports anything from here, and nothing here is imported by `import parity`.
Each adapter imports its third-party dependency LAZILY, inside the function that needs it,
so `import parity_integrations.dbt` works on a bare interpreter and only the dependency-
backed calls raise `MissingDependency`.
"""
from __future__ import annotations

import importlib

__all__ = ["MissingDependency", "require"]


class MissingDependency(ImportError):
    """An optional integration was called without its third-party dependency installed."""


def require(module: str, extra: str):
    """Import `module` or raise MissingDependency naming the pip extra that provides it."""
    try:
        return importlib.import_module(module)
    except ImportError as e:
        raise MissingDependency(
            f"this call needs `{module}`, which is not installed. Install the optional extra: "
            f"pip install 'parity-controls[{extra}]'  (the parity core itself stays "
            f"dependency-free)"
        ) from e
