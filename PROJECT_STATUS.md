# Project Status

Last updated: 2026-07-28
Current phase: SQLite prerequisites verified; provider verification blocked;
schema and seed design next.

This is the repository's concise implementation handoff and persistent context
document for coding agents. It is **not architecture authority** — approved
decisions live in `docs/planning/decisions.md` and always take precedence.

## Last completed work

- Architecture documentation committed at `9e87d00`.
- Agent handoff contract committed at `51df1a6`.
- Pre-implementation contracts frozen at `e8051f5`.
- Python package and toolchain established at `e58caf1`.
- SQLite behavioral prerequisites verified in the pinned environment
  (this phase).
- No push has occurred; the repository has no remote configured.

## Verified environment

- Python **3.13.14** through `uv` 0.11.28
- SQLite library **3.53.1**
- Package `src/bse_nlq/` imports from the installed environment
- Direct runtime dependencies: `openai`, `sqlglot`
- Direct development dependencies: `pytest`, `pytest-cov`, `ruff`, `mypy`

## SQLite behavioral prerequisites verified in the pinned environment

Isolated capability probes against in-memory databases and a temporary
directory. **This is not verification of the application's SQL safety
boundary**, which is neither implemented nor tested.

**STRICT tables — behaviorally supported.** A minimal STRICT table was created,
a valid row inserted, and an invalid value inserted into an INTEGER column was
rejected with `IntegrityError`.

**Foreign keys — enforced when enabled before a transaction.** Initially
disabled. `PRAGMA foreign_keys = ON` succeeded when issued before any
transaction opened, and the enabled value was read back. A valid parent/child
relationship succeeded; an orphan foreign key was rejected with
`IntegrityError`.

**Read-only URI — enforced.** On a temporary on-disk database whose writable
setup connection had been closed first, `mode=ro` permitted `SELECT` and
rejected `INSERT` with `OperationalError`.

**`query_only` — independently enforced.** Tested on a separate, otherwise
writable connection. It permitted `SELECT` and rejected `INSERT` with
`OperationalError`. It does not replace the read-only URI.

**Authorizer — available and denying.** `Connection.set_authorizer` was
available. A temporary default-deny authorizer permitted the narrowly approved
`SELECT` and denied `INSERT`, `PRAGMA`, and `DROP` behavior with
`DatabaseError`.

Qualifications: this was a **capability probe**, not the final application
action, function, or table allowlist. Denial was **observed when the statement
was submitted**; no direct instrumentation of `sqlite3_prepare_v2` was
performed, and none is claimed.

**Progress handler — available and interrupting.** `set_progress_handler` was
available. A small query completed under a generous budget; an intentionally
expensive recursive query was interrupted with `OperationalError: interrupted`.

**Cleanup.** All temporary databases and directories were removed, and their
absence was verified.

### Action-code caveat for future implementation

Numeric SQLite constants share namespaces across the `sqlite3` module. Action
code `19` represented **`SQLITE_PRAGMA`** in the authorizer callback context,
though `SQLITE_CONSTRAINT` also equals 19 as a result code. Future code must use
an **explicit authorizer-action mapping** rather than a naive reverse lookup over
every `sqlite3` module constant.

### Computation versus materialization

- The **progress handler** bounds SQLite computation.
- The **fetch cap** bounds rows materialized by the application.
- **Neither replaces the other.**

### STRICT fallback status

The approved ordinary-table-plus-`CHECK` fallback is **not needed for the
currently pinned environment**, because STRICT behavior passed. It **remains an
approved portability contingency** and is not withdrawn from the architecture.

## Provider verification — blocked

- `OPENAI_API_KEY`: **not available to the verification environment**
- `GROQ_API_KEY`: **not available to the verification environment**
- A local `.env` file exists on disk. It is gitignored and untracked, and its
  contents were **not read**. No variables from it were loaded into the
  verification shell.
- **No provider request was attempted.** No network call of any kind was made.

Consequently unverified: model access, structured-output enforcement, exact
endpoint identifiers, billing, retry behavior, usage metadata, and
shared-adapter compatibility.

**This is not evidence of provider failure or ineligibility.** Nothing has been
observed about either endpoint's behavior.

## Active blockers

**The model-backed MVP is blocked by:**

- OpenAI credential not available to the verification environment
- unverified OpenAI billing and access
- unverified exact GPT-5 mini endpoint identifier
- unverified strict structured-output behavior

**The optional model comparison is blocked by:**

- Groq credential not available to the verification environment
- unverified hosted GPT-OSS access and schema behavior

Absent Groq credentials must not block offline implementation or the OpenAI MVP
path.

## Next work — two independent tracks

**Immediate offline implementation objective.** Finalize the physical SQLite
schema, deterministic seed scenarios, semantic metadata contract, and reference
business definitions. This requires no credentials and is not blocked.

**Provider prerequisite.** Once `OPENAI_API_KEY` is supplied to the working
environment, run the minimal GPT-5 mini structured-output smoke test **before**
implementing or claiming the model-backed happy path.

## Approved fallbacks

- If Groq is unavailable or ineligible, proceed with GPT-5 mini and record the
  comparison as blocked.
- If SQLite `STRICT` is unavailable in some other environment, use ordinary
  tables with explicit `CHECK` constraints.
- If the REPL threatens the timebox, omit it and retain `ask`, stdin input, and
  JSON output.
- If advanced unit-lineage rules threaten the timebox, retain the minimum
  required rules and return `unknown` rather than guessing.

## Non-negotiable constraints

- One semantic model-generation attempt per request
- Bounded transport retries only
- No model-controlled SQL repair loop
- No runtime model selector or automatic provider failover
- The automated pytest suite remains offline
- Model output and generated SQL remain untrusted
- Essential SQL safety controls exist before the first model-generated query is
  executed
- `AI_USAGE.md` is updated at every completed implementation phase

## Not yet implemented

- Physical SQLite schema
- Deterministic seed script
- Semantic metadata sidecar and business definitions
- Application connection factory
- Final authorizer policy and function allowlist
- SQLGlot AST validator (not exercised in any phase so far)
- Application fetch cap
- Production progress-handler budget
- Schema introspection and context renderer
- Prompt builder
- Provider adapter
- `QueryService`
- Result-unit analyzer
- CLI and its console entry point
- Adapter, integration, CLI, and safety test suites
- Provider smoke tests
- Development-set and locked holdout evaluation
- Final README setup, usage, testing, and evaluation content

`tests/integration/` remains intentionally deferred until the first real
integration test exists. The D-012 integration-test category remains approved.
