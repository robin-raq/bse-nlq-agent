# Architecture Workshop Summary

The workshop converted the exercise requirements into the decisions in [`decisions.md`](decisions.md). This file records only the review lessons that materially changed the design.

## Key tradeoffs

- A synthetic BSE dataset answers the exercise’s likely domain questions but limits the independence of evaluation.
- SQLite minimizes reviewer setup but requires explicit handling for dates, money, permissions, computation limits, and row limits.
- Several independent SQL controls were chosen because AST policy and SQLite runtime enforcement fail differently.
- Deterministic result formatting is less fluent than a second model call but cannot introduce claims absent from executed results.
- Scope is cut in this order if necessary: comparison model, optional REPL, advanced unit inference, diagnostic polish, then evaluation repetitions.

## Corrections made during review

- Restricted the “AST owns safety” claim to static policy; SQLite owns runtime enforcement.
- Rejected a global column allowlist that would block valid aliases and CTE outputs.
- Distinguished physical tables from CTE and derived relation names.
- Kept malformed provider payloads at the adapter boundary instead of violating the typed generator contract.
- Prevented aliases from being treated as proof of monetary units or business formulas.
- Removed raw questions and prompts from default logging.
- Removed unsupported assumptions about deadlines, credentials, and endpoint equivalence.
- Replaced configuration-only provider reuse with a shared core plus small transport-specific branches after smoke testing.

## Remaining risks

The specification may exceed the timebox; metadata can be complete but still wrong; SQLite is process-level isolation; unit inference is deliberately incomplete; and a small synthetic holdout supports descriptive rather than general claims.
