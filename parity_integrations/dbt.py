"""dbt adapter - SKELETON. Extra: pip install 'parity-controls[dbt]'.

Interface (see docs/ROADMAP.md, "Next", for what is built and what is not):

  freeze_seeds(project_dir, seed_dir="seeds") -> lock dict      WORKS without dbt installed
  verify_seeds(project_dir, lock, seed_dir="seeds") -> True       WORKS without dbt installed
  relation_key_parity(project_dir, offered, present, key)         needs dbt; NOT IMPLEMENTED

The seed functions need no dbt at all: a seed is a CSV file in the project, and what dbt
loads from it is exactly what `parity_integrations.lockfile` digests. Freezing seeds is how a
reviewer can see that a "refactor" PR did not quietly change reference data.

`relation_key_parity` is the real write-boundary check for a model - distinct keys offered by
an upstream relation vs distinct keys present in the built model, compared with
`parity.offered_present_parity` - and it needs a warehouse connection, which is dbt's job.
It imports dbt lazily and is a stub until the roadmap item lands: it raises, it never returns
a fake pass.
"""
from __future__ import annotations

import os
from pathlib import Path

from parity_integrations import require
from parity_integrations.lockfile import freeze, verify

ROADMAP = "docs/ROADMAP.md, Next: 'dbt adapter - relation_key_parity'"


def _seed_root(project_dir: str | os.PathLike, seed_dir: str) -> Path:
    project = Path(project_dir)
    if not (project / "dbt_project.yml").is_file():
        raise FileNotFoundError(f"{project}: no dbt_project.yml - not a dbt project directory")
    return project / seed_dir


def freeze_seeds(project_dir: str | os.PathLike, seed_dir: str = "seeds") -> dict:
    """Lockfile document for every `*.csv` under the project's seed directory.

    `seed_dir` is not read from dbt_project.yml (`seed-paths`): parsing YAML would need a
    dependency the core refuses. Pass it explicitly if your project moved it.
    """
    return freeze(_seed_root(project_dir, seed_dir), "*.csv")


def verify_seeds(project_dir: str | os.PathLike, lock: dict, seed_dir: str = "seeds") -> bool:
    """Refuse (ParityViolation) if any seed file was added, removed, renamed or changed."""
    return verify(_seed_root(project_dir, seed_dir), lock)


def relation_key_parity(project_dir: str | os.PathLike, offered_relation: str,
                        present_relation: str, key: str) -> bool:
    """Distinct `key` values of `offered_relation` vs `present_relation`, via dbt. NOT BUILT.

    Raises MissingDependency without dbt-core; with it, NotImplementedError until the
    roadmap item lands.
    """
    require("dbt.cli.main", "dbt")
    raise NotImplementedError(
        f"relation_key_parity is a skeleton: it would query both relations through dbt and "
        f"compare key sets with parity.offered_present_parity. Tracked in {ROADMAP}."
    )
