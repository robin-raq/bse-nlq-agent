# Project Status

Last updated: 2026-07-29

This is the operational handoff for coding agents. Read it before starting work to understand the verified repository state, the next implementation objective, and active constraints. Architecture authority remains in `docs/planning/decisions.md` and `ARCHITECTURE.md`.

## Current phase

The schema and dataset contracts are complete, and the entity-relationship diagram is prepared. The next implementation step is test-first SQLite DDL.

Design artifacts: `docs/planning/schema-design.md` (physical contract), `docs/planning/seed-manifest.md` (exact deterministic literals), `docs/diagrams/schema-erd.md` (ERD).

No application feature path exists yet: a user cannot submit a question, generate SQL, or query a database. No schema, seed, or database file exists.

**Anchor values are document-level, hand-computed expectations. No anchor has been verified against a real seeded database.** The reconciliation arithmetic has been cross-checked between documents only; that is not database verification.

## Completed work

- Architecture, trust boundaries, terminal states, and evaluation approach were agreed and documented.
- The project uses a single `src/bse_nlq/` package with a `src/` layout.
- Python and dependency management were configured with `.python-version`, `pyproject.toml`, and `uv.lock`.
- Direct dependencies were limited to `openai` and `sqlglot`; development tooling includes pytest, pytest-cov, Ruff, and mypy.
- Speculative empty packages were removed.
- SQLite capabilities required by the design were behaviorally checked in the pinned runtime.
- OpenAI and Groq endpoints were smoke-tested for authentication, model access, strict response-shape compatibility, and local `ModelDecision` invariants.
- Reviewer and agent documentation was consolidated to remove duplicated planning history.
- The schema and seed design was worked through and approved: six tables, revenue and refund formulas, ticket-count metrics, attendance model, timestamp convention, unit and rounding rules, a 109-row deterministic seed with reconciliation totals, and 14 development anchors. Recorded in `docs/planning/schema-design.md` and `docs/planning/decisions.md`.
- Ambiguity policy, time-of-day limits, refund-measure independence, and an executable I-6 were frozen after independent review. Exact seed literals were completed in `docs/planning/seed-manifest.md`, and an ERD was added at `docs/diagrams/schema-erd.md`.

## Verified state

| Area | Verified evidence |
|---|---|
| Runtime | Python 3.13.14 through `uv` 0.11.28; SQLite 3.53.1 |
| Package | `bse_nlq` imports from the installed environment |
| Toolchain | Ruff formatting and linting, mypy, pytest, and `uv lock --check` passed after scaffolding |
| SQLite | STRICT enforcement, foreign keys, read-only URI, `query_only`, authorizer denial, and progress interruption behaved as required in isolated probes |
| OpenAI | GPT-5 mini accepted the strict four-field decision schema and returned a locally valid response |
| Groq | `openai/gpt-oss-120b` accepted the same schema and returned a locally valid response |
| Secrets | Credentials and the private exercise document remain untracked |

Provider checks establish endpoint eligibility only. They do not establish SQL quality, comparative performance, or final model selection. SQLite probes establish runtime capabilities, not an implemented application safety boundary.

## Immediate next objective

Implement the data foundation as one reviewable phase:

1. Test-first SQLite DDL: six STRICT tables, CHECK domains, generated columns, foreign keys, and indexes.
2. Deterministic seed data module and loader reproducing the 109 rows in `docs/planning/seed-manifest.md`.
3. Invariant assertions I-1 through I-8, with I-8 asserted as `<=`.
4. Reconciliation tests for the overall, channel, venue, and category totals.
5. Anchor verification: execute all 14 anchors and assert their expected results, including A14's empty result.
6. JSON semantic metadata sidecar, asserted against introspection and duplicating no schema-owned fact.
7. Run the full formatting, linting, typing, test, lockfile, and secret checks.
8. Reconcile `PROJECT_STATUS.md` with verified outcomes and update `AI_USAGE.md` only if this phase materially changes the reviewer-facing AI disclosure.

Anchor expected results are hand-computed and remain unverified until step 5 executes them.

Do not begin provider integration, prompt iteration, or model-generated SQL execution during this phase.

## Subsequent sequence

1. Read-only connection factory, authorizer, progress budget, and fetch cap.
2. SQLGlot policy and unit inference with isolated safety tests.
3. Schema-context renderer, date resolution, and prompt builder.
4. Provider adapters and shared `ModelDecision` validation.
5. `QueryService`, deterministic formatting, and terminal-state mapping.
6. CLI and JSON contract.
7. Development evaluation, frozen holdout, and final model selection.

## Active blockers

None.

Model quality and final selection are intentionally blocked on the frozen evaluation, not on missing access or endpoint compatibility.

## Non-negotiable constraints

- One semantic model-generation attempt per request; bounded transport retries only.
- No model repair loop, runtime provider selector, or automatic failover.
- Automated tests must run offline without credentials.
- Questions, model output, and generated SQL remain untrusted.
- All essential SQL safety controls must exist before the first model-generated query is executed.
- Unknown units remain raw rather than guessed.

## Approved fallbacks

- If Groq later becomes unavailable, continue with GPT-5 mini and report the comparison as blocked.
- If SQLite STRICT is unavailable in another environment, use ordinary tables with explicit `CHECK` constraints.
- If scope must be cut, remove the optional REPL and advanced unit inference before weakening the core CLI, safety boundary, or evaluation integrity.

## Not yet implemented

Physical schema, seed data, semantic metadata, application database factory, SQL policy, provider adapters, service, result formatting, CLI, integration and safety suites, evaluation cases, evaluation results, and final model selection.

The schema design is approved but no DDL, seed code, metadata file, or database exists.
