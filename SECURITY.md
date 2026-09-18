# Security Policy

`parity` is a small, dependency-free library that checks data at a write boundary. This
document says which versions are supported, how to report a problem privately, and what
this library's actual attack surface is — which is smaller than the phrase "financial data
and AI pipelines" might suggest.

## Supported versions

| Version | Supported | Notes |
|---|---|---|
| 0.2.x | ✅ | Current line. Fixes land here. |
| `< 0.2` | ❌ | Superseded. Please reproduce on 0.2.x before reporting. |

The library is pure Python with no runtime dependencies (`dependencies = []` in
`pyproject.toml`), so a fix is a text change and there is nothing to backport for.

## Reporting a vulnerability

**Do not open a public issue for a security problem.** Open a **private security advisory**
via GitHub's Security tab on this repository — *Security → Advisories → Report a
vulnerability*. That is the only channel that keeps a report private until there is a fix. A
public issue or pull request exposes the defect before anything has been tested, and on a
library whose whole job is catching silent corruption, the exposure *is* the defect.

There is no security email address to write to. The private advisory is the channel.

A useful report contains:

- the version (`parity.__version__`) and the exact call you made;
- the smallest input that produces the behaviour, pasted inline — **not** a real dataset;
- what the control returned, and what you expected it to do instead;
- which documented claim in `README.md` or in the function docstring you believe is wrong.

## What to expect

This is a solo portfolio/research project with one maintainer, not a staffed product. That
is the honest framing, so here is what it means in practice:

- **Acknowledgement** of the advisory within about 7 days.
- **Assessment**: whether it is in scope (see below), how it fails, and whether it fails
  **open** or closed — that distinction is usually the whole answer.
- **Fix** on the 0.2.x line, with the failure pinned by a test *before* the fix, because a
  defect in a control has to be demonstrated rather than argued.
- **Disclosure** once a fixed version exists: the advisory is published naming the mechanism
  and the affected calls. Credit goes to the reporter unless you ask otherwise.

There is no bug bounty. Nothing here runs a service, so there is no server to take down and
no data to lose while a fix is prepared.

## Threat model

**What `parity` is.** Advisory functions over data the caller already holds —
`offered_present_parity`, `cross_field`, `share_anomaly`, `canonical_hash`. The library
imports only `collections`, `hashlib` and `math` from the standard library: there is no
network access, no credential handling, no file I/O and no configuration loading inside it.
It computes over values it is handed. The security-relevant failures are therefore not
remote ones. They are:

1. **A control that fails open.** A function that returns "pass" on a fault it documents
   itself as catching. This is the class of primary interest, and it is the reason the repo
   ships a fault matrix and a fuzzed encoding test rather than anecdotes. Defects of this
   family that were found and fixed are recorded in `README.md` under *What is proven, and
   what is not*.
2. **A document that overclaims.** A docstring or README line asserting a control cannot be
   fooled, where it can. Stated equivalences are intentional (`None` and `""` are the same
   cell, as are `True` and `"True"`); undisclosed ones are bugs, and they are worth an
   advisory.
3. **Input data carrying personal data.** The library runs on real pipelines, and a real
   input may contain personal data: this project's own first run was over a file carrying
   **owner names and mailing addresses**, which is precisely why that input file is
   deliberately not shipped in this repository. Do not commit real datasets, and do not
   paste them into issues or advisories. Do not assume a `canonical_hash` digest makes a
   file safe to share either — it is a deterministic, unsalted integrity digest, not a
   redaction, and it can be recomputed by anyone who can guess the input.

**Out of scope** — already named as limits in `README.md`, so they are not vulnerabilities:
no concurrency claim (the live adapter is single-writer and says so in the code); no
warehouse adapter; `share_anomaly` is a heuristic that is WARN-only and never raises, by
design; and the write boundary passes on empty (`0` vs `0`) by design, because the caller —
not this library — owns the distinction between "nothing was offered" and "a dead fetcher
offered nothing".
