# BSE Natural Language Query Agent

A natural-language-to-SQL agent for the Brooklyn Sports and Entertainment AI Engineer take-home exercise. It is designed to turn a plain-English question into SQL, validate the generated query, execute it against a read-only SQLite database, and return the result with the SQL used.

> **Current status:** architecture and project scaffolding are complete; the application, dataset, and evaluation are not yet implemented.

## Planned approach

The request pipeline is intentionally small:

1. Resolve relative dates deterministically.
2. Provide the model with schema and business context.
3. Generate one typed decision: SQL, clarification, or unsupported.
4. Parse and validate generated SQL before execution.
5. Execute through a read-only SQLite connection with runtime limits.
6. Format results deterministically and show the executed SQL.

Only SQL generation is nondeterministic. Validation, execution, and formatting remain application-controlled.

## Technology

- Python 3.13 managed with `uv`
- OpenAI SDK
- SQLGlot for SQL parsing and validation
- SQLite
- pytest, Ruff, and mypy

The MVP targets GPT-5 mini. A hosted `openai/gpt-oss-120b` endpoint is planned as an evaluation comparison; no final model selection or quality result is claimed yet.

## Safety

Model output is treated as untrusted input. The planned execution boundary combines:

- a read-only database connection;
- SQLite `query_only`;
- parsed-AST policy checks;
- a default-deny SQLite authorizer;
- an execution instruction budget; and
- a result-row cap.

These controls will be tested independently. No safety claim is considered verified until the implementation and tests exist.

## Running and testing

Commands will be added when the application is implemented and verified from a clean checkout. At present, the repository contains project scaffolding and architecture documentation only.

## Key design choices

- A fixed pipeline is used instead of an agent framework because the application makes one model call and has no planning loop or dynamic tool selection.
- Answers are formatted from executed results without a second model call.
- Money will be stored as integer cents, and relative dates will be resolved from an explicit as-of date.
- Evaluation will compare executed results with reference queries rather than matching SQL strings.

Detailed design notes are available in [`ARCHITECTURE.md`](ARCHITECTURE.md). The database design is specified in [`docs/planning/schema-design.md`](docs/planning/schema-design.md), with an entity-relationship diagram in [`docs/diagrams/schema-erd.md`](docs/diagrams/schema-erd.md). AI assistance is disclosed in [`AI_USAGE.md`](AI_USAGE.md).
