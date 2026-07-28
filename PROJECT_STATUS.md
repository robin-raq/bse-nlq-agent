# Project Status

Last updated: 2026-07-28

This is the operational handoff for coding agents. Read it before starting work to understand the verified repository state, the next implementation objective, and active constraints. Architecture authority remains in `docs/planning/decisions.md` and `ARCHITECTURE.md`.

## Current phase

Prerequisites and project scaffolding are complete. The next phase is the physical SQLite schema, deterministic seed data, and semantic metadata.

No application feature path exists yet: a user cannot submit a question, generate SQL, or query a database.

## Completed work

- Architecture, trust boundaries, terminal states, and evaluation approach were agreed and documented.
- The project uses a single `src/bse_nlq/` package with a `src/` layout.
- Python and dependency management were configured with `.python-version`, `pyproject.toml`, and `uv.lock`.
- Direct dependencies were limited to `openai` and `sqlglot`; development tooling includes pytest, pytest-cov, Ruff, and mypy.
- Speculative empty packages were removed.
- SQLite capabilities required by the design were behaviorally checked in the pinned runtime.
- OpenAI and Groq endpoints were smoke-tested for authentication, model access, strict response-shape compatibility, and local `ModelDecision` invariants.
- Reviewer and agent documentation was consolidated to remove duplicated planning history.

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

1. Define the minimal BSE-flavored event, category, ticket, order, and refund relationships needed by the planned query set.
2. Encode keys, nullability, status domains, quantities, and integer-cent monetary constraints in SQLite.
3. Add a deterministic seed that covers joins, grouping, date ranges, ranking, revenue, refunds, cancellations, zero-value tickets, and an empty-result case.
4. Add semantic metadata for business meanings, units, synonyms, visibility, and canonical revenue rules without duplicating schema-owned facts.
5. Add tests proving repeatable generation, constraint enforcement, foreign-key integrity, and metadata coverage.
6. Run the full formatting, linting, typing, test, lockfile, and secret checks.
7. Update this file and `AI_USAGE.md` with verified outcomes before beginning the connection factory.

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
