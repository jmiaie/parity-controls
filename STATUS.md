# Status — parity-controls

**Updated:** 2026-09-30 (PT)  
**Visibility:** public  
**Maturity:** MVP / public package surface (v0.3.0)  
**Role:** **Public companion** to private [`jmiaie/parity`](https://github.com/jmiaie/parity)

## Honest positioning

Write-boundary integrity controls (`offered_present_parity`, `cross_field`, `share_anomaly`, `canonical_hash`) for financial / AI pipeline data. Private hardening continues in `parity`; safe extracts and public CI live here.

See [`docs/POSITIONING.md`](docs/POSITIONING.md).

| Claim | Reality |
|-------|---------|
| Identical tip to private `parity` | **Companion** — sync after explicit review; do not assume byte-identical |
| Private Actions always green | Private may park on billing; public CI badge is the honest signal for this remote |
| Dependabot PRs auto-landed | Several Dependabot PRs remain **open** (ruff/pytest/setuptools/actions) — owner triage |

## Offline check (2026-09-30, box)

```bash
python3 test_parity.py   # ALL PASS (fault matrix)
```

## Workflows

`.github/workflows/ci.yml` exists. This advance **does not** modify workflow files.

## What is **not** claimed

- New incident metrics beyond documented case studies already in-tree  
- That open Dependabot PRs are reviewed this wave

## Next (owner)

1. Keep public/private sync deliberate after hardening  
2. Triage Dependabot (actions bumps need workflow-scoped token if merging via bot)  
3. Prefer citing this remote for public portfolio links
