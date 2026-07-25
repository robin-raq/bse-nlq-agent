# AGENTS.md — BSE NLQ Candidate Exercise

## Project Goal

Build a focused Natural Language Query agent that:

1. Accepts a plain-English question.
2. Generates valid SQL using a foundation model.
3. Validates the generated SQL.
4. Executes it against a structured database.
5. Returns a concise human-readable answer.
6. Displays the generated SQL for transparency.
7. Handles common failures gracefully.

This is a five-day candidate exercise, not a production platform.

## Authority

When instructions conflict, use this order:

1. The original BSE candidate exercise
2. User-approved decisions in `docs/planning/decisions.md`
3. The active Compound Engineering plan
4. `ARCHITECTURE.md`
5. This file
6. General engineering best practices

Do not silently override a higher-authority source.

## Scope Discipline

Prioritize:

- NLQ accuracy
- Prompt and schema-context design
- SQL safety
- Clear separation of concerns
- Error handling
- Meaningful evaluation
- Reproducible setup
- Clear documentation

Do not add unless explicitly approved:

- Authentication
- Deployment infrastructure
- Multi-turn memory
- Multi-agent runtime orchestration
- Background job systems
- Production observability platforms
- Unnecessary cloud services
- A highly polished frontend

Prefer the smallest architecture that demonstrates sound judgment.

## Development Workflow

For behavior changes:

1. Identify the intended behavior and acceptance criteria.
2. Write or identify a failing test.
3. Confirm the test fails for the expected reason.
4. Implement the smallest change that makes it pass.
5. Run focused tests.
6. Run the full relevant suite.
7. Run linting and type checks.
8. Review the diff before committing.

Do not claim completion without showing validation evidence.

## Architecture Rules

Keep these concerns separated:

- Prompt and schema-context construction
- Model invocation
- Structured model-output parsing
- SQL validation
- Database execution
- Response formatting
- Evaluation

Treat model output as untrusted input.

Database execution must be read-only. Do not execute destructive or
data-modifying SQL.

Prefer deterministic application logic where an LLM is unnecessary.

## Evaluation

Do not evaluate correctness using exact SQL-string matching alone.

Prefer execution-result comparison or explicit result invariants because
different SQL queries may be semantically equivalent.

Evaluation cases should cover:

- Aggregation
- Multi-table joins
- Date filtering
- Grouping
- Ranking
- Revenue calculations
- Empty results
- Ambiguous questions
- Unsupported requests
- Unsafe or malicious requests
- Malformed model output

Report limitations honestly.

## Documentation

Update documentation when architecture, setup, behavior, or tradeoffs change.

`AI_USAGE.md` is a mandatory completion gate for every implementation phase.
Record:

- AI tools and models used
- Important prompts and decisions
- Validation commands
- Manual review performed
- Mistakes and findings
- Deferred or blocked work

Do not commit secrets, `.env` files, or the private candidate exercise PDF.
