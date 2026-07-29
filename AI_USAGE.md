# AI Usage Disclosure

AI tools were used as design and implementation assistants for this take-home project.

## Tools

- Claude Code (Claude Opus), including the Compound Engineering plugin
- ChatGPT

## Material assistance

AI assisted with:

- repository setup and project structure;
- comparing architecture options and documenting tradeoffs;
- designing the SQL-safety layers and evaluation approach;
- drafting architecture documentation and diagrams;
- dependency and runtime verification;
- provider smoke-test planning and review;
- test-first implementation of the SQLite physical schema and its contract test suite; and
- test-first implementation of the deterministic seed loader, literal transcription from the tracked manifest, invariant/reconciliation/anchor SQL, and analytical trap regressions.

Claude Code also helped prepare the current Python package scaffolding, dependency configuration, and initial validation checks.

## Seed-phase review

For the seed foundation, AI transcribed the frozen literals from
`docs/planning/seed-manifest.md` into typed Python tuples and drafted the
loader and offline tests. An independent review then found and corrected:

- a non-SQLite/`BaseException` rollback gap in `load_seed_data` and the same
  pattern in `apply_schema`;
- an I-8 E11 boundary test that counted cancelled-order tickets;
- refunded-revenue queries that omitted the completed-order base (latent while
  the seed had no cancelled-order refunds); and
- circular literal checks against `seed_data`, replaced with SHA-256
  fingerprints of the production tuples plus retained database oracles.

Human review owned the final contracts, acceptance of exact financial totals,
and confirmation that schema application and seed loading remain separate
operations.

## Candidate ownership and review

I made the final design decisions and manually reviewed AI-generated proposals and artifacts. During review, I corrected issues including overly broad safety claims, SQL validation rules that would reject valid aliases and CTEs, unsafe logging defaults, unsupported factual assumptions, and formatting that could overstate result semantics.

The SQLite physical schema and deterministic 109-row seed are implemented and test-verified, including database-executed anchors A1–A14. No semantic metadata sidecar, persistent application database file, query service, SQL safety validator, CLI, provider integration for SQL quality, or model-quality evaluation is complete yet. Provider smoke tests only verified endpoint access and structured-response compatibility; they do not establish SQL quality or model superiority.

Secrets and private exercise materials were not committed. API credentials were used only through ignored local environment configuration and were not printed or persisted.
