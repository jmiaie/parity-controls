#!/bin/bash
# Nightly: the live CA surplus pipeline, run THROUGH the parity write gate.
#
# Zero tokens. stdout carries the RESULT and is delivered verbatim: the gate's one-line digest
# on success, or `GATE FAILED rc=N: <reason>` on refusal - an alert that says only "exited 2"
# is a noise generator, not an alert. Scrape noise and the full run tail go to the log.
# Exit 2 = the gate refused; any other non-zero = the run broke. Both alert.
# Extra args are passed to the pipeline, so the failure branch is testable without a full fetch:
#   PARITY_DIR=/nonexistent bash surplus-gate-nightly.sh --offline
set -uo pipefail
STATE=/srv/pipeline/state/surplus
LOG="$STATE/run.log"
mkdir -p "$STATE"
cd /srv/pipeline/repo/main || exit 9
echo "=== $(date -Is) start" >> "$LOG"

ERR=$(mktemp)
/srv/venv/bin/python ca_surplus_funds.py \
    --output "$STATE/leads.csv" "$@" 2>"$ERR" | tee -a "$LOG"
rc=${PIPESTATUS[0]}   # tee's status is not the pipeline's; the digest line is now durable
# Read the reason from THIS night's stderr, never from $LOG - the log accumulates, so grepping
# it would happily report a violation from a previous night as tonight's. Prefer the gate's own
# line, then the exception message; 'Traceback (most recent call last):' is not a reason.
reason=$(grep -m1 'GATE VIOLATION' "$ERR")
[ -n "$reason" ] || reason=$(grep -E 'Error|Exception|error:' "$ERR" | tail -1)
[ -n "$reason" ] || reason=$(tail -1 "$ERR")
cat "$ERR" >> "$LOG"
rm -f "$ERR"

echo "$(date -Is) rc=$rc" >> "$LOG"
if [ $rc -eq 0 ]; then
    echo "leads -> $STATE/leads.csv"
else
    echo "GATE FAILED rc=$rc: ${reason:-no reason line in stderr, see $LOG}"
fi
exit $rc
