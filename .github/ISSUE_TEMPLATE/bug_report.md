---
name: Bug report
about: A control fired on healthy data, or stayed silent on broken data
title: "[bug] "
labels: bug
---

<!--
Before you file: run `make check` (or `python3 test_parity.py` then `python3 demo.py`) and
paste the result. A control that has never been observed to fail is not a control, so the
first question here is always which way it went wrong.
-->

## Which way did the control go wrong?

A control has exactly two failure modes, and they have different fixes. Tick one.

- [ ] **False alarm** — a control FIRED on healthy data. (This is the more urgent one: a
      control that cries wolf gets muted, and a muted control is worse than no control.)
- [ ] **False negative** — a control stayed SILENT on broken data. (Nothing was reported
      while the data was wrong.)

Which control: <!-- offered_present_parity / cross_field / share_anomaly / canonical_hash / verify_canonical -->

## What I ran

<!-- The exact command, and the code around the failing call if it is your own. -->

```
```

## What I expected

<!-- And which mechanism you expected the message to name. -->

## What happened

<!-- The control's actual message, or its silence. -->

## Exact output

<!-- Full traceback or full message. Do not trim the numbers: a delta and a key count are
     usually the whole diagnosis. -->

```
```

## Minimal reproduction

<!-- The smallest dataset and the fewest lines that still show it. An in-memory list of
     dicts is ideal - if it needs a database, the case will not get reproduced. -->

```python
```

## Environment

- Python version (`python3 --version`):
- OS and version:
- `parity` version or commit:
- Install method (repo checkout / `pip install -e .`):

## Anything else

<!-- Anything you already ruled out, so it is not re-checked. -->
