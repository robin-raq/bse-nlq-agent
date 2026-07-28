# Project Status

Last updated: 2026-07-28
Current phase: SQLite and provider prerequisites verified; physical schema and
deterministic seed design next.

This is the repository's concise implementation handoff and persistent context
document for coding agents. It is **not architecture authority** — approved
decisions live in `docs/planning/decisions.md` and always take precedence.

## Last completed work

- Architecture documentation committed at `9e87d00`.
- Agent handoff contract committed at `51df1a6`.
- Pre-implementation contracts frozen at `e8051f5`.
- Python package and toolchain established at `e58caf1`.
- SQLite behavioral prerequisites verified in the pinned environment.
- Provider endpoint prerequisites verified; both endpoints eligible
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

## Provider endpoint prerequisites verified

Endpoint eligibility only. One request per provider, using a harmless prompt
unrelated to the BSE dataset. **No BSE SQL was generated or executed.**

**OpenAI — eligible for MVP endpoint integration.** Responses API, default base
URL. Requested alias `gpt-5-mini`; the API returned identifier
`gpt-5-mini-2025-08-07`. The strict flattened `ModelDecision` schema was
accepted, completion status was `completed`, exactly the four required fields
were returned, an explicitly requested undeclared field was absent, and local
invariants passed. No refusal occurred. Observed latency 9,117 ms; usage 155
input / 336 output / 491 total tokens.

**Groq — eligible for like-for-like comparison.** Chat Completions through
`https://api.groq.com/openai/v1`, model `openai/gpt-oss-120b`. The same strict
flattened schema was accepted with `strict: true`, finish reason was `stop`,
exactly the four required fields were returned, the requested undeclared field
was absent, and local invariants passed. Observed latency 1,088 ms; usage 289
prompt / 343 completion / 632 total tokens.

Both latency figures are **single observational samples from one request each**.
They are not comparative evidence and imply nothing about p95 behavior.

**Both endpoints are eligible.** No provider prerequisite blocker remains for the
MVP. The two-candidate comparison is available for later D-010 evaluation.

**Not established by these probes:** NLQ-to-SQL quality, SQL correctness, model
reliability, production readiness, comparative latency, comparative cost, p95
latency, constrained decoding as Groq's internal mechanism, final model
selection, retry reliability, and refusal behavior across representative cases.

**No production adapter exists.** No application model call has been implemented.

## Active blockers

None for the prerequisite phase. Model quality and final model selection remain
unverified and are gated behind the frozen D-010 evaluation, which has not run.

## Next work — two tracks

**Immediate offline implementation objective.** Finalize the physical SQLite
schema, deterministic seed scenarios, semantic metadata, and reference business
definitions.

**Later implementation objective.** Implement the narrow `QueryGenerator`
boundary with shared `ModelDecision` validation and provider-specific
request/response transports.

## Approved fallbacks

- If Groq later becomes unavailable or ineligible, proceed with GPT-5 mini and
  record the comparison as blocked. Its endpoint has now been verified eligible,
  so this is a contingency rather than an expected path.
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
- Development-set and locked holdout evaluation
- Final README setup, usage, testing, and evaluation content

`tests/integration/` remains intentionally deferred until the first real
integration test exists. The D-012 integration-test category remains approved.
