#!/usr/bin/env python3
"""Load measurement. The README quotes numbers; this is how to disagree with them.

    python3 bench.py [rows]        e.g. python3 bench.py 1000000

One process, one core, five columns per row. Keys are passed in reverse so the set
comparison does real work instead of short-circuiting on identical ordering.
"""
import resource
import sys
import time

from parity import canonical_hash, offered_present_parity, share_anomaly


def run(n: int) -> dict:
    rows = [{"wallet": "0x%040x" % (i % 4000), "slug": f"m-{i % 97}", "oi": i % 2,
             "stake": round((i % 500) + 0.25, 2), "label": ("Yes", "No")[i % 2]}
            for i in range(n)]
    keys = list(range(n))
    t = time.perf_counter(); offered_present_parity(keys, list(reversed(keys))); set_s = time.perf_counter() - t
    t = time.perf_counter(); digest = canonical_hash(rows); hash_s = time.perf_counter() - t
    t = time.perf_counter(); share_anomaly([r["oi"] for r in rows], name="oi"); share_s = time.perf_counter() - t
    return {"rows": n, "set": set_s, "hash": hash_s, "share": share_s,
            "rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, "digest": digest[:8]}


if __name__ == "__main__":
    for arg in (sys.argv[1:] or ["100000", "1000000"]):
        m = run(int(arg))
        print(f"{m['rows']:>9,} rows | set parity {m['set']:5.2f}s | canonical_hash "
              f"{m['hash']:6.2f}s | share_anomaly {m['share']:5.2f}s | peak RSS "
              f"{m['rss_mb']:7.1f} MB | {m['digest']}")
