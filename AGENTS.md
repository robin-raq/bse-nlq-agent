# Repository Guidance

## Goal

Build the smallest credible natural-language-to-SQL take-home: accept a question, generate and validate SQL, execute it read-only, return a concise answer, show the SQL, and handle common failures.

## Source of truth

When instructions conflict, use this order:

1. Current task and exercise requirements
2. `docs/planning/decisions.md`
3. Active implementation plan
4. `ARCHITECTURE.md`
5. This file
6. `PROJECT_STATUS.md`
7. Supporting documentation

`PROJECT_STATUS.md` tracks current work; it does not override architecture.

## Scope

Prioritize NLQ accuracy, prompt/schema context, SQL safety, separation of concerns, error handling, evaluation, reproducibility, and reviewer clarity.

Do not add authentication, deployment infrastructure, multi-turn memory, runtime multi-agent orchestration, background jobs, hosted observability, unnecessary cloud services, or a polished frontend without explicit approval.

## Workflow

For behavior changes:

1. Define the expected behavior.
2. Add or identify a failing test.
3. Implement the smallest sufficient change.
4. Run focused tests, then the relevant full suite.
5. Run formatting, linting, and type checks.
6. Review the diff and update affected documentation.

Do not claim completion without validation evidence.

## Engineering rules

- Keep prompt construction, provider calls, model-output parsing, SQL policy, database execution, formatting, and evaluation separate.
- Treat questions, model output, and generated SQL as untrusted.
- Keep database execution read-only.
- Prefer deterministic code wherever an LLM is unnecessary.
- Evaluate answer correctness by execution results or explicit invariants, not SQL text alone.
- Keep automated tests offline; live provider checks and evaluation are explicit commands.
- Never commit secrets, `.env`, the private exercise PDF, raw chat transcripts, or scratch notes.

## Documentation

- `README.md`: reviewer setup, usage, design summary, and results.
- `ARCHITECTURE.md`: technical contract and boundaries.
- `docs/planning/decisions.md`: concise rationale for consequential choices.
- `PROJECT_STATUS.md`: current phase, blockers, next work, and verified state.
- `AI_USAGE.md`: curated material AI assistance and candidate review.
- `AI_USAGE.local.md`: optional private detail; ignored by Git.

Update only the document that owns the changed fact. Avoid parallel histories and duplicate task lists.
