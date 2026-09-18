#!/usr/bin/env python3
"""Which of these tests would notice if the fix were reverted?

A check that passes with the defect present cannot detect that defect - it is decoration, and it
reads as protection. The third adversarial review of this repo found five of those by hand
(2026-09-18): fixtures that never constructed the collision they named, and assertions on an
exception TYPE the unfixed module raised as well. This is the mechanical version, so the claim
is checkable instead of trusted, and so the next reviewer does not have to find them again.

    python3 tools/audit_tests.py <rev-before-the-fix>
    python3 tools/audit_tests.py 2b08a2b --module parity.py --tests test_parity.py

Exit 0 when every check either fails on the old module or is labelled a pin; exit 1 when a check
passes on both revisions, which means it detects nothing.

Pins are exempt on purpose: a check whose name contains "ceiling pin" or "not a regression test"
asserts a documented equivalence or a stability property, and both revisions should agree on it.
Label them in those words or the tool will report them forever.
"""
import argparse
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

PINS = ("ceiling pin", "not a regression test")
CHECKNAME = re.compile(r'check\(\s*"([^"]+)"')


def check_names(text: str) -> list:
    return CHECKNAME.findall(text)


def status(text: str, name: str) -> str:
    """PASS / FAIL / not reached, matched on the check name as printed."""
    for line in text.splitlines():
        if name[:55] in line and ("[PASS]" in line or "[FAIL]" in line):
            return "PASS" if "[PASS]" in line else "FAIL"
    return "not reached"


def run_suite(repo: pathlib.Path, module_source: str, tests: str, module: str) -> str:
    """Run the CURRENT test file against this module source, in a throwaway copy of the repo."""
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp) / "repo"
        shutil.copytree(repo, work, ignore=shutil.ignore_patterns(".git", "__pycache__", "build", "dist", "*.egg-info"))
        (work / module).write_text(module_source)
        p = subprocess.run([sys.executable, tests], cwd=work, capture_output=True, text=True)
        return p.stdout + p.stderr


def show(ref: str, path: str, repo: pathlib.Path) -> str:
    p = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=repo, capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"git show {ref}:{path} failed: {p.stderr.strip()}")
    return p.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rev", help="the revision BEFORE the fix (e.g. the commit the review came from)")
    ap.add_argument("--module", default="parity.py")
    ap.add_argument("--tests", default="test_parity.py")
    a = ap.parse_args()

    repo = pathlib.Path(__file__).resolve().parent.parent
    cur_test = (repo / a.tests).read_text()
    old_checks = check_names(show(a.rev, a.tests, repo))
    added = [n for n in check_names(cur_test) if n not in old_checks]
    if not added:
        print(f"no check names added since {a.rev}: nothing to audit against it")
        return 0

    old_out = run_suite(repo, show(a.rev, a.module, repo), a.tests, a.module)
    new_out = run_suite(repo, (repo / a.module).read_text(), a.tests, a.module)
    old_pass, old_fail = old_out.count("[PASS]"), old_out.count("[FAIL]")
    print(f"{a.rev}: {old_pass} pass / {old_fail} fail   |   HEAD: {new_out.count('[PASS]')} pass / {new_out.count('[FAIL]')} fail")
    print(f"checks added since {a.rev}: {len(added)}\n")

    dead = []
    for name in added:
        a_old, a_new = status(old_out, name), status(new_out, name)
        pin = any(k in name for k in PINS)
        flag = ""
        if a_old == "PASS" and a_new == "PASS":
            if pin:
                flag = "  pin (exempt)"
            else:
                flag = "  TAUTOLOGY: detects nothing"
                dead.append(name)
        elif a_old != "FAIL" and not pin:
            flag = f"  undetermined ({a_old} on the old module)"
        print(f"  old={a_old:11s} new={a_new:11s} {name[:92]}{flag}")

    print()
    if dead:
        print(f"{len(dead)} check(s) pass with the defect present and must be rewritten:")
        for n in dead:
            print(f"  - {n}")
        return 1
    print("every check either fails on the old module or is labelled a pin: nothing decorative")
    return 0


if __name__ == "__main__":
    sys.exit(main())
