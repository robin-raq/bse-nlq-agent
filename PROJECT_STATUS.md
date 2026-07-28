# Project Status

Last updated: 2026-07-28

**Phase:** prerequisites verified; physical schema and deterministic seed design are next.

## Verified

- Python 3.13.14 via `uv` 0.11.28; SQLite 3.53.1.
- `src/bse_nlq/` imports from the installed environment.
- Direct runtime dependencies are `openai` and `sqlglot`; development uses pytest, pytest-cov, Ruff, and mypy.
- SQLite supports the required STRICT tables, foreign keys, read-only URI, `query_only`, authorizer, and progress-handler behavior in the pinned environment.
- GPT-5 mini through OpenAI Responses and `openai/gpt-oss-120b` through Groq Chat Completions accepted the strict `ModelDecision` schema and passed local invariants in one endpoint smoke test each.

Endpoint checks establish compatibility only. They do not establish SQL quality or model superiority.

## Next

1. Define the SQLite schema and deterministic seed scenarios.
2. Add semantic metadata and canonical business definitions.
3. Implement the connection factory, SQL policy, and safety tests.
4. Implement provider adapters and `QueryService`.
5. Add the CLI, development evaluation, and locked holdout.

## Constraints

- One semantic generation attempt per request; bounded transport retries only.
- No repair loop, runtime model selector, or automatic provider failover.
- Automated tests remain offline.
- Model output and SQL remain untrusted.
- Safety controls precede the first model-generated execution.

## Blockers

None. Model quality and final selection remain pending the frozen evaluation.

## Approved fallbacks

- If Groq becomes unavailable, continue with GPT-5 mini and report the comparison as blocked.
- If another environment lacks SQLite STRICT support, use ordinary tables with explicit `CHECK` constraints.
- Cut the optional REPL and advanced unit inference before weakening the core CLI or safety boundary.

## Not implemented

Application schema and data, metadata, database factory, SQL validator, provider adapters, service, formatting, CLI, integration and safety suites, evaluation cases, and final results.
