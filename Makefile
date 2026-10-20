# parity - task runner. Shell and stdlib only: nothing here needs a tool the repo does
# not already have, because the repo has no dependencies and no build step.
#
# CI is live on this public repo (.github/workflows/ci.yml) and runs the same gate plus
# `pytest`. `make check` is the local form: the fault matrix, then the demo, and a red result
# means the controls did not prove themselves. Run it before pushing.

PYTHON ?= python3

.PHONY: help check test pytest demo bench example clean

help:  ## list every target (default)
	@echo "parity - available targets:"
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

check:  ## the gate: fault matrix, then the demo in dollars
	$(PYTHON) test_parity.py
	@echo
	$(PYTHON) demo.py

test:  ## run the fault matrix - every control fires on its fault, silent when healthy
	$(PYTHON) test_parity.py

pytest:  ## tests/ under pytest (needs the dev extra: pip install -e '.[dev]')
	$(PYTHON) -m pytest -q -rs

demo:  ## the same failure in dollars: 97 rows vanish and the book is off by 22.7%
	$(PYTHON) demo.py

bench:  ## the load measurement the README quotes, so the numbers can be argued with
	$(PYTHON) bench.py

example:  ## the four controls on a small in-memory dataset, healthy and broken
	$(PYTHON) examples/quickstart.py

clean:  ## remove caches and build artefacts
	rm -rf __pycache__ build dist *.egg-info .pytest_cache
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
