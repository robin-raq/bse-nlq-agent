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
- provider smoke-test planning and review; and
- test-first implementation of the SQLite physical schema and its contract test suite.

Claude Code also helped prepare the current Python package scaffolding, dependency configuration, and initial validation checks.

## Candidate ownership and review

I made the final design decisions and manually reviewed AI-generated proposals and artifacts. During review, I corrected issues including overly broad safety claims, SQL validation rules that would reject valid aliases and CTEs, unsafe logging defaults, unsupported factual assumptions, and formatting that could overstate result semantics.

The SQLite physical schema is implemented and test-verified; no seed data, dataset loading, application feature pipeline, or model-quality evaluation is complete yet. Provider smoke tests only verified endpoint access and structured-response compatibility; they do not establish SQL quality or model superiority.

Secrets and private exercise materials were not committed. API credentials were used only through ignored local environment configuration and were not printed or persisted.
