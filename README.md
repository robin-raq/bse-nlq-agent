# BSE Natural Language Query Agent

A natural-language-to-SQL agent for the Brooklyn Sports and Entertainment AI Engineer take-home exercise. It is designed to turn a plain-English question into SQL, validate the generated query, execute it against a read-only SQLite database, and return the result with the SQL used.

> **Current status:** the physical SQLite schema, deterministic 109-row seed
> loader, JSON semantic metadata sidecar, strict ModelDecision validation,
> deterministic prompt construction, a persistent database builder, a safe
> read-only runtime open (`open_readonly_database` / `ReadOnlyDatabase`), and
> SQL-policy Slices 1–3 (`validate_sql` / `ValidatedSql`: parse/normalize/
> fingerprint, structure policy, and physical-table allowlisting via
> `scope.sources` with canonical `referenced_tables`) are implemented and
> verified offline. CTE and derived names are not mistaken for physical
> tables. Column/star authorization, authorizer/limits, query execution, the
> NLQ service/CLI, and final evaluation remain pending. There is no public
> raw-SQL API and no product ask command. Model-generated SQL has not been
> tested. The application is not runnable end-to-end.


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
- SQLGlot 30.14.0 for SQL parsing and validation
- SQLite
- pytest, Ruff, and mypy

The MVP targets GPT-5 mini. A hosted `openai/gpt-oss-120b` endpoint is planned as an evaluation comparison; no final model selection or quality result is claimed yet.

## Safety

Model output is treated as untrusted input. The planned execution boundary combines:

- a read-only database connection (**implemented** as `open_readonly_database`);
- SQLite `query_only` (**implemented** and verified on that connection);
- parsed-AST policy checks (**Slices 1–4A structure, physical-table
  authorization, canonical column inventories, and internal output-name
  schemas implemented**; public column binding / global star / function / date
  authorization pending);
- a default-deny SQLite authorizer (pending);
- an execution instruction budget (pending); and
- a result-row cap (pending).

The open boundary is tested offline. Remaining safety layers must be tested
independently before model-generated SQL is executed.

## Running and testing

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Hatchling 1.31.0 is pinned as both the build backend and a locked development
dependency. After `uv sync --group dev`, an offline wheel build can use the
synchronized environment directly:

```bash
uv build --wheel --offline --no-build-isolation
```

The ordinary isolated `uv build --wheel --offline` also works when the uv cache
already contains the pinned backend. A cold empty cache cannot construct the
isolated build offline because it has no Hatchling artifact; dependencies must
be synchronized while available first. The project does not vendor build tools.

Build a local synthetic database artifact (not committed; not an NLQ CLI):

```bash
uv run python -m bse_nlq.db.build /tmp/bse-nlq.sqlite3
# replace an existing regular file only with an explicit flag:
uv run python -m bse_nlq.db.build /tmp/bse-nlq.sqlite3 --overwrite
```

`overwrite=False` fails closed if the destination already exists (atomic
no-clobber). `overwrite=True` replaces a regular non-symlink file and clears
stale SQLite sidecars beside that path. Do not build over a database that
another process has open.

Open a published artifact read-only (developer/library API; not an NLQ CLI):

```bash
uv run python -c "from pathlib import Path; from bse_nlq.db import open_readonly_database; \
db = open_readonly_database(Path('/tmp/bse-nlq.sqlite3')); print(sorted(db.physical_tables)); db.close()"
```

Path, connection, and metadata failures raise `DatabaseRuntimeError` with the
underlying cause attached. Programming defects are not normalized into that
type. A SQLite failure from `close()` becomes `DatabaseRuntimeError`;
programming, resource, and control-flow failures propagate unchanged. Any
failed close leaves the wrapper open and retryable rather than silently
reporting success;
`database_path` stays readable after close for diagnostics, while metadata and
inventory access does not.

The automated suite is offline and does not require API credentials. Live
provider checks and evaluation are separate explicit commands (not yet part of
the default workflow).


## Key design choices

- A fixed pipeline is used instead of an agent framework because the application makes one model call and has no planning loop or dynamic tool selection.
- Answers are formatted from executed results without a second model call.
- Money will be stored as integer cents, and relative dates will be resolved from an explicit as-of date.
- Evaluation will compare executed results with reference queries rather than matching SQL strings.

Detailed design notes are available in [`ARCHITECTURE.md`](ARCHITECTURE.md). The database design is specified in [`docs/planning/schema-design.md`](docs/planning/schema-design.md), with an entity-relationship diagram in [`docs/diagrams/schema-erd.md`](docs/diagrams/schema-erd.md). AI assistance is disclosed in [`AI_USAGE.md`](AI_USAGE.md).
