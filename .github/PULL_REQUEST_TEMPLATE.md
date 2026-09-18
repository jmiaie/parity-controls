<!-- CI is parked (.github/workflows/ci.yml.disabled), so this checklist IS the gate. -->

## What this changes

<!-- One paragraph. Say which control or mode it touches, if any. -->

## Checklist

- [ ] Ran `python3 test_parity.py` — result: <!-- PASS/FAIL, and the count -->
- [ ] Ran `python3 demo.py` — result: <!-- the numbers it printed -->
- [ ] Added no third-party runtime dependency (the library is stdlib only)
- [ ] If a new control was added: it ships with a fault in `faults.py` that makes it fire,
      **and** a case in the fault matrix that proves it fires
- [ ] If behaviour changed: README updated (including the known-blind-spots section, if the
      change moves one)
- [ ] CHANGELOG updated

## Notes for the reviewer

<!-- Anything you deliberately did not do, and why. Negative results are welcome here:
     a check that cannot see a fault is worth recording in the README. -->
