#!/usr/bin/env python3
"""test_alarm_offline.py - the alarm-offline test for the parity write gate.

Claim under test: the write gate in ca_surplus_funds.py REFUSES (rc=2, GateViolation)
when one county's rows silently disappear, and the nightly wrapper says WHY.
Run it:  python3 tests/test_alarm_offline.py     (stdlib only, no pytest, no network)

This one is an INTEGRATION test and it is not hermetic, which is why it SKIPS (rc=0) rather
than fails when its inputs are absent - the push path runs every test_*.py it finds, and a
test that needs one host's layout must not be able to block a push from another. Set:
  PIPELINE=/path/to/ca_surplus_funds.py   WRAPPER=/path/to/surplus-gate-nightly.sh
  FIXTURE=/path/to/sample_leads.csv       PARITY_DIR=/path/to/parity

Nothing under the live working copy or parity/ is modified: the pipeline is staged
byte-identically into /tmp/gateproof/run and driven there. The fixture comes from a clone
where it is git-tracked as sample_data/sample_leads.csv, because the live working copy is not
a checkout and does not carry it.

FIVE CHECKS. The one that matters is CHECK 3 - it fails if the gate stops refusing.
CHECK 2 documents, with observed output, a real blind spot in --offline.

  CHECK 1  control: real pipeline, --offline, no fault          -> want rc 0 + GATE OK
  CHECK 2  injected collapse under --offline                    -> observed rc 0 (GAP)
  CHECK 3  same collapse, parse-boundary bookkeeping armed      -> want rc 2 + reason
  CHECK 4  same county's row dropped at the writer, via the real wrapper logic
           (real wrapper body, real pipeline bytes; only the paths are relocated)
                                                                -> want rc 2 + reason
  CHECK 5  gate unarmed (PARITY_DIR=/nonexistent)               -> want rc 2 + NOT ARMED
"""
import csv
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(os.environ.get("PIPELINE_REPO", "/srv/pipeline/repo/main"))
PIPELINE = Path(os.environ.get("PIPELINE", str(REPO / "ca_surplus_funds.py")))
WRAPPER = Path(os.environ.get("WRAPPER", "/srv/pipeline/scripts/surplus-gate-nightly.sh"))
PARITY_DIR = os.environ.get("PARITY_DIR", "/srv/parity")
FIXTURE_SRC = Path(os.environ.get("FIXTURE", "/tmp/parity-fixture/sample_data/sample_leads.csv"))
WORK = Path("/tmp/gateproof")
RUN, OUT, STATE, INJECT = WORK / "run", WORK / "out", WORK / "state", WORK / "inject"
PY = "/srv/venv/bin/python"
if not Path(PY).exists():
    PY = sys.executable
VICTIM = "Orange"          # a county whose rows DO land in the output when healthy
STAGED_WRAPPER = WORK / "wrapper.sh"


# --------------------------------------------------------------------------
# Fault driver. The test re-executes itself in this mode so the fault runs
# inside a real pipeline process and its exit code is a real process exit code.
# --------------------------------------------------------------------------
def drive(mode: str) -> int:
    sys.path.insert(0, str(RUN))
    import ca_surplus_funds as P

    real_row_to_lead = P.row_to_lead

    def drop_victim(row, county, source_url, claim_window_days=None):
        if county == VICTIM:
            return None            # INCIDENT-0047: the county's rows stop parsing
        return real_row_to_lead(row, county, source_url, claim_window_days)

    P.row_to_lead = drop_victim

    if mode == "offline":
        return P.main(["--offline", "--output", str(OUT / "offline_fault.csv")])

    assert mode == "armed", mode
    # Live branch, but the "source" is the bundled fixture - no HTTP anywhere.
    # This is the only structural difference from --offline: main()'s live branch
    # fills offered_by_county / parsed_by_county, so the parse-boundary check has data.
    with (RUN / "sample_data" / "sample_leads.csv").open(newline="") as f:
        by_county = {}
        for r in csv.DictReader(f):
            by_county.setdefault(r["county"], []).append(r)

    P.load_sources = lambda path=None: [
        {"county": c, "url": f"fixture://{c}", "type": "csv"} for c in sorted(by_county)
    ]
    P.fetch_source = lambda cfg, session, timeout: by_county[cfg["county"]]
    return P.main(["--output", str(OUT / "armed_fault.csv")])


if len(sys.argv) > 2 and sys.argv[1] == "--drive":
    sys.exit(drive(sys.argv[2]))


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------
def stage() -> bool:
    missing = [p for p in (PIPELINE, WRAPPER, FIXTURE_SRC) if not p.exists()]
    if missing:
        print("SKIP: integration test, inputs absent (rc=0 by design - a missing host layout")
        print("      must never block a push). Set PIPELINE / WRAPPER / FIXTURE to run it:")
        for m in missing:
            print(f"        {m}")
        return False
    for d in (RUN, OUT, STATE, INJECT):
        d.mkdir(parents=True, exist_ok=True)
    (RUN / "sample_data").mkdir(exist_ok=True)
    shutil.copy2(PIPELINE, RUN / "ca_surplus_funds.py")
    shutil.copy2(FIXTURE_SRC, RUN / "sample_data" / "sample_leads.csv")

    # Real wrapper body, only the two path constants relocated (see printed diff below).
    body = WRAPPER.read_text()
    body = body.replace("STATE=/srv/pipeline/state/surplus", f"STATE={STATE}")
    body = body.replace("cd /srv/pipeline/repo/main", f"cd {RUN}")
    STAGED_WRAPPER.write_text(body)
    STAGED_WRAPPER.chmod(0o755)

    # Fault 2 injection point: a row for one county never reaches the disk at the write
    # boundary. Injected at the csv writer, so the pipeline file stays byte-identical.
    # sitecustomize is imported automatically when PYTHONPATH points here.
    (INJECT / "sitecustomize.py").write_text(
        "import csv, os\n"
        "v = os.environ.get('GATE_FAULT_DROP_COUNTY')\n"
        "if v:\n"
        "    _real = csv.DictWriter.writerow\n"
        "    def writerow(self, rowdict, *a, **k):\n"
        "        if rowdict.get('county') == v:\n"
        "            return None\n"
        "        return _real(self, rowdict, *a, **k)\n"
        "    csv.DictWriter.writerow = writerow\n"
    )
    return True


def run(cmd, env_extra=None, cwd=None):
    env = dict(os.environ, PYTHONPATH=str(RUN), **{})
    env.pop("GATE_FAULT_DROP_COUNTY", None)
    env.update(env_extra or {})
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)


def show(title, cp):
    print(f"    $ {title}")
    for line in (cp.stdout + cp.stderr).strip().splitlines():
        print(f"      | {line}")
    print(f"      exit={cp.returncode}")


def csv_rows(path: Path) -> int:
    return len(path.read_text().strip().splitlines()) - 1 if path.exists() else -1


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def main() -> int:
    if not stage():
        return 0
    print(f"pipeline : {PIPELINE}  (staged byte-identical to {RUN/'ca_surplus_funds.py'})")
    print(f"parity   : {PARITY_DIR}/parity.py")
    print(f"wrapper  : {STAGED_WRAPPER}  (real body, paths relocated)")
    print()

    # CHECK 1 - control: healthy offline run, gate armed, must succeed with a digest.
    print("CHECK 1 - control: --offline, no fault")
    cp = run([PY, "ca_surplus_funds.py", "--offline", "--output", str(OUT / "control.csv")],
             {"PARITY_DIR": PARITY_DIR}, cwd=RUN)
    show("python ca_surplus_funds.py --offline --output out/control.csv", cp)
    healthy = csv_rows(OUT / "control.csv")
    check("CHECK 1 control: rc==0 and gate digest printed",
          cp.returncode == 0 and "GATE OK" in cp.stdout and healthy > 0,
          f"rc={cp.returncode} leads={healthy}")
    print()

    # CHECK 2 - the requested injection under --offline, run as a real process.
    print(f"CHECK 2 - injected collapse ({VICTIM} rows -> 0) under --offline")
    cp = run([PY, __file__, "--drive", "offline"], {"PARITY_DIR": PARITY_DIR}, cwd=RUN)
    show(f"python {__file__} --drive offline   (wraps row_to_lead: {VICTIM} -> None)", cp)
    offline_rows = csv_rows(OUT / "offline_fault.csv")
    refused_offline = cp.returncode == 2 or "GATE VIOLATION" in (cp.stdout + cp.stderr)
    check("CHECK 2 the injected fault really did remove a county (CHECK 1 is the unfaulted control)",
          offline_rows >= 0 and offline_rows < healthy,
          f"leads {healthy} -> {offline_rows}")
    if refused_offline:
        print("      OBSERVED: --offline refuses too - it got armed; tighten this into a check")
    else:
        print(f"      GAP, NOT SCORED: under --offline the gate reports GATE OK while {healthy - offline_rows} "
              f"leads are missing. main()'s offline")
        print("      branch never fills the per-county parse bookkeeping, so the collapse check it feeds has")
        print("      nothing to compare against. The live path the nightly takes IS armed (6/6 sources parsed).")
        print("      Offline tests the pipeline, not the gate - named here because a gate that is quiet in the")
        print("      mode you test with is how a control gets muted.")
    print()

    # CHECK 3 - the alarm. Same fault, on the path where offered/parsed per county exist.
    print(f"CHECK 3 - ALARM: same collapse with the parse-boundary check armed")
    armed_out = OUT / "armed_fault.csv"
    if armed_out.exists():
        armed_out.unlink()
    cp = run([PY, __file__, "--drive", "armed"], {"PARITY_DIR": PARITY_DIR}, cwd=RUN)
    show(f"python {__file__} --drive armed   (live-branch bookkeeping, fetch from fixture)", cp)
    err = cp.stdout + cp.stderr
    check("CHECK 3 ALARM: gate REFUSES with rc=2 and names the collapsed source",
          cp.returncode == 2 and "GATE VIOLATION" in err and "silent collapse" in err
          and VICTIM in err,
          f"rc={cp.returncode}")
    check("CHECK 3b ALARM: nothing was committed at the write boundary",
          not armed_out.exists(),
          f"{armed_out.name} exists={armed_out.exists()}")
    print()

    # CHECK 4 - the wrapper. Real wrapper body, real pipeline bytes, paths relocated.
    print("CHECK 4 - wrapper alarm: same county's row dropped at the WRITER")
    before = (STATE / "leads.csv")
    digest_before = before.read_bytes() if before.exists() else b""
    cp = run(["bash", str(STAGED_WRAPPER), "--offline"],
             {"PARITY_DIR": PARITY_DIR, "PYTHONPATH": str(INJECT),
              "GATE_FAULT_DROP_COUNTY": VICTIM})
    show(f"GATE_FAULT_DROP_COUNTY={VICTIM} bash {STAGED_WRAPPER.name} --offline", cp)
    check("CHECK 4 wrapper: rc==2 and stdout carries a real reason, not just an exit code",
          cp.returncode == 2 and re.search(r"^GATE FAILED rc=2: .*GATE VIOLATION.*", cp.stdout, re.M)
          and ("never landed" in cp.stdout or "silent collapse" in cp.stdout),
          cp.stdout.strip().splitlines()[0] if cp.stdout.strip() else "no stdout")
    check("CHECK 4b wrapper: the refusal left the previous night's file untouched",
          (before.read_bytes() if before.exists() else b"") == digest_before and digest_before != b"",
          f"{before.name} unchanged ({len(digest_before)} bytes)")
    print()

    # CHECK 5 - fail closed: parity not importable is a refusal, not a silent pass.
    print("CHECK 5 - gate unarmed: PARITY_DIR=/nonexistent")
    cp = run(["bash", str(STAGED_WRAPPER), "--offline"], {"PARITY_DIR": "/nonexistent"})
    show("PARITY_DIR=/nonexistent bash wrapper.sh --offline", cp)
    check("CHECK 5 fail-closed: rc==2 and reason names the missing gate",
          cp.returncode == 2 and "NOT ARMED" in cp.stdout,
          cp.stdout.strip().splitlines()[0] if cp.stdout.strip() else "no stdout")
    print()

    print("NOTE - the real wrapper, run as-is against the live working copy:")
    cp = run(["bash", str(WRAPPER), "--offline"])
    show("bash /srv/pipeline/scripts/surplus-gate-nightly.sh --offline", cp)
    print("      -> rc=1 FileNotFoundError, i.e. the gate is never reached: the fixture is")
    print(f"         missing from {REPO}/sample_data/. Restoring that one tracked file")
    print("         (`git checkout sample_data/sample_leads.csv` in the live tree) makes the")
    print("         real wrapper run --offline verbatim. Not done here: uploads/main is off-limits.")
    print()

    failed = [n for n, ok, _ in results if not ok]
    print(f"=== {len(results) - len(failed)}/{len(results)} checks PASS ===")
    for n, ok, d in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {n}")
    if failed:
        print("FAILED: " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
