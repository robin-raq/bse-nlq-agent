# Architecture

> Approved target design. The full vertical flow is implemented and
> test-verified offline: schema, seed, semantic metadata, `ModelDecision`
> validation, deterministic prompt construction, the persistent database
> builder, the read-only runtime factory, the complete SQL-policy
> foundation (`bse_nlq.sql_policy`: parsing, structure, table/column/star/
> function authorization), the default-deny SQLite authorizer and controlled
> execution boundary (`bse_nlq.db.execution`), `QueryService`
> (`bse_nlq.service`), the OpenAI adapter (`bse_nlq.provider_openai`), and
> the `bse-nlq ask` CLI (`bse_nlq.cli`). Only evaluation and a live provider
> smoke test remain.

## Principles

- The model only converts a question into a typed decision.
- The application owns dates, validation, execution, formatting, and workflow.
- Each request permits one semantic model-generation attempt. Provider transport retries may be bounded; model repair loops are excluded.
- User input and all model output are untrusted.

## Request pipeline

```text
question
  -> deterministic date resolution
  -> prompt assembly from schema and semantic metadata
  -> model decision
  -> local contract validation
  -> SQLGlot policy and unit analysis
  -> read-only SQLite execution
  -> deterministic formatting
  -> terminal state
```

Projection-unit analysis occurs before execution. The application never rewrites generated SQL: when execution occurs, `generated_sql` and `executed_sql` are identical.

## Components

| Area | Responsibility |
|---|---|
| Service | Orchestration and terminal-state mapping |
| Dates | Strict `as_of` validation and half-open ranges |
| Schema context | Introspection plus curated business metadata |
| Prompt | Deterministic `build_prompt(PromptInput) -> BuiltPrompt` |
| Decision | Strict `parse_model_decision_json` / `validate_model_decision` |
| Provider adapter | Prompt submission and response normalization (pending) |
| SQL policy | Parsing, structural validation, and unit inference |
| Database | Schema/seed, persistent artifact build, read-only runtime open; authorizer and limits pending |
| Formatting | Human and JSON output from executed values |
| Evaluation | Frozen cases, reference queries, and reporting |

All implementation lives in the single `src/bse_nlq/` package. Modules should be created only when they contain real behavior.

Implemented module paths for this phase:

- `bse_nlq.db` — `apply_schema`, `load_seed_data`, `build_database`, `open_readonly_database` / `ReadOnlyDatabase`, `execute_validated_sql` / `RawQueryResult`
- `bse_nlq.metadata` — `load_semantic_metadata`
- `bse_nlq.decision` — `ModelDecision`, `parse_model_decision_json`, `model_decision_json_schema`
- `bse_nlq.prompt` — `PromptInput`, `BuiltPrompt`, `build_prompt`
- `bse_nlq.generator` — provider-neutral `RawModelGenerator` / `decide_from_raw_generator` (offline boundary; no live adapters)
- `bse_nlq.sql_policy` — Slices 1–4D (complete): `validate_sql` / `ValidatedSql`
  with bounded parsing, structure policy, physical-table authorization,
  canonical column inventories, internal CTE/derived/Union output-name
  schemas, qualified/unqualified column binding and correlation, ORDER BY
  projection aliases, exclusions, canonical physical `referenced_columns`,
  `COUNT(*)`-only star policy, and a fixed function allowlist (`SUM`,
  `COUNT`, `COALESCE`) that rejects every machine-clock form by default-deny

## Model contract

`QueryGenerator.generate(QueryRequest) -> ModelDecision` isolates provider code from the deterministic core. Offline tests use `decide_from_raw_generator(RawModelGenerator, BuiltPrompt) -> ModelDecision` so prompt construction and decision parsing can be exercised without a provider.

`ModelDecision` has four required fields and rejects additional properties:

| Field | Type |
|---|---|
| `status` | `sql_generated`, `clarification_required`, or `unsupported` |
| `sql` | string or null |
| `clarification` | string or null |
| `explanation` | string or null |

Local validation enforces the allowed null/non-null combination for each status:

- `sql_generated` → nonempty `sql`; `clarification` and `explanation` null
- `clarification_required` → nonempty `clarification`; `sql` and `explanation` null
- `unsupported` → nonempty `explanation`; `sql` and `clarification` null

Malformed or contradictory envelopes raise `InvalidModelOutputError`, which maps to the `invalid_model_output` terminal state. Provider schema enforcement constrains response shape, not SQL safety or correctness. A deterministic JSON Schema is available from `model_decision_json_schema()` for later structured-output configuration; cross-field invariants remain application-owned.

Adapter contract for raw model responses: pass the provider's response text to `parse_model_decision_json`. Do not `json.loads` and then call `validate_model_decision` for raw provider payloads—ordinary JSON decoding collapses duplicate keys before validation can reject them. Runtime code must construct `ModelDecision` through validation rather than by instantiating the dataclass directly.

The MVP endpoint is GPT-5 mini through OpenAI Responses. The evaluation-only
comparison candidate is `openai/gpt-oss-120b` through Groq Chat Completions;
it is not a runtime provider option. Both accept the same strict decision
schema, and their comparative results are recorded in the model-comparison
reports without changing this boundary.

## SQL safety

U1 implements the read-only runtime open boundary only:
`open_readonly_database(database_path) -> ReadOnlyDatabase`. The wrapper is
context-managed, privately owns one `sqlite3.Connection` (package-private
`_connection`; no public arbitrary-SQL surface), opens an absolute filesystem
path via `Path.as_uri()` with `mode=ro` and `uri=True`, enables and verifies
`PRAGMA foreign_keys=ON` and `PRAGMA query_only=ON`, rejects exact sibling
`-wal` / `-shm` / `-journal` sidecars without deleting them, reconciles packaged
semantic metadata before readiness, and exposes immutable
`physical_tables` / `physical_columns` / `prompt_visible_columns` /
`prompt_excluded_columns` inventories. Existing filenames containing `?`, `#`,
`%`, spaces, or Unicode are supported; missing ordinary paths are reported as
missing filesystem paths, not URI strings. `:memory:` and `file:` inputs are
rejected explicitly.

Error and lifecycle contract: expected open failures — filesystem
`OSError`, path-expansion `RuntimeError`, invalid-path `ValueError` /
`TypeError`, `sqlite3.Error`, and `MetadataError` — surface as
`DatabaseRuntimeError` with the original exception preserved as `__cause__`.
Normalization is localized to the specific path, SQLite-connection, or
metadata operation that can legitimately raise it, not applied broadly across
the whole open sequence. Programming defects (for example `AttributeError`,
or a `RuntimeError` / `TypeError` / `ValueError` raised by a bug inside a
metadata/inventory helper or the PRAGMA setup helper rather than an actual
path, SQLite, or metadata failure) and `KeyboardInterrupt` /
`SystemExit` propagate unwrapped after cleanup. `close()` is idempotent after
a successful close. A SQLite close failure becomes `DatabaseRuntimeError`;
programming, resource, and control-flow failures propagate unchanged. Every
failed close leaves the wrapper open rather than reporting closure. When a
`with` body and `close()` both fail, the close failure is primary and the body
failure remains available through standard exception context.
`database_path` is immutable identity and stays readable after close; every
connection-dependent property and the package-private `_connection` reject use
after close.

U3 (`execute_validated_sql` / `RawQueryResult` in `bse_nlq.db.execution`)
completes controlled execution on top of the U1 read-only runtime boundary:
a `sqlite3.Connection` authorizer allows exactly `SQLITE_SELECT`
unconditionally, `SQLITE_READ` only for the query's own
`referenced_tables`/`referenced_columns`, and `SQLITE_FUNCTION` only for the
same fixed allowlist the static policy enforces; every other action code —
writes, schema changes, PRAGMA, ATTACH/DETACH, transactions, recursive CTEs,
and unknown codes — is denied by one catch-all default-deny branch. A
progress handler bounds total VDBE instructions (budget calibrated well
above real anchor cost, ~1-2k opcodes, while still bounding runaway
execution); row/column counts are hard-capped with overflow rejection rather
than silent truncation. Both callbacks are installed immediately before
execution and removed in `finally`, so a failure never leaves them attached
for a later, unrelated query. Accepts only `ValidatedSql` and executes
`original_sql`, never `normalized_sql`.

(Schema-aware SQLGlot AST authorization — tables, columns, stars, functions,
and machine-clock rejection — is complete as of Slice 4D.)

The SQL-policy package (`validate_sql` → immutable `ValidatedSql`) parses with
SQLGlot's SQLite dialect, rejects empty/semicolon-only and multi-statement
input, preserves trimmed `original_sql` for later execution, fingerprints
deterministic `normalized_sql`, accepts only `Select`/`Union` roots (including
parenthesized SELECT and nonrecursive CTEs), requires every unwrapped CTE body
to use those same approved query roots, default-denies other roots, rejects
forbidden constructs anywhere in the tree, rejects recursive CTEs, rejects
parameters/`Placeholder`/`Parameter`/unquoted `$…` forms, and authorizes
physical tables from SQLGlot `scope.sources` against the caller-supplied
`physical_tables` inventory. Canonical names are returned in
`referenced_tables`. Nested `Scope` sources (CTEs/derived tables) are not
physical tables; database/catalog qualifiers and non-identifier table sources
(for example table-valued functions) are rejected. Slice 4A validates and
canonicalizes `physical_columns` / `prompt_visible_columns` against
`physical_tables` (ASCII-only fold, inventory spelling, visible ⊆ physical)
and builds internal CTE/derived/Union output-name schemas for duplicate and
arity detection (`ambiguous_column`, `invalid_cte_column_list`,
`invalid_union_arity`). Slice 4B binds qualified physical/internal columns,
resolves qualified correlation through the nearest permitted lexical scope,
rejects unknown qualifiers/columns and excluded physical columns, populates
canonical physical `referenced_columns`, and rejects authored stars except
`COUNT(*)`. SQLGlot's synthetic `VALUES` star remains distinguishable from
authored SQL. Slice 4C binds unqualified columns against sources local to
the column's own scope only: more than one local candidate is
`ambiguous_column`; exactly one binds through the same physical/internal
authorization as the qualified path; zero local candidates is
`unknown_column` and never climbs to an outer scope. An unqualified ORDER BY
name that matches the immediately enclosing SELECT's own projection alias
resolves to that alias — matching SQLite's own precedence — without
contributing a physical identity; WHERE, JOIN ON, GROUP BY, and HAVING do not
see alias binding. Slice 4D authorizes every function call by SQLGlot
expression *type* against a fixed allowlist (`exp.Sum`, `exp.Count`,
`exp.Coalesce`); every other call is rejected, which covers every
machine-clock form (`CURRENT_DATE`/`CURRENT_TIME`/`CURRENT_TIMESTAMP`,
`date`/`datetime`/`julianday`/`strftime`/`unixepoch(...)`) without inspecting
`'now'`/`'localtime'`/`'utc'` arguments — no date-expression grammar was
built. `exp.Binary` (this SQLGlot version multiply-inherits `And`/`Or` from
both `Binary` and `Func`) and `exp.Exists` (the Slice 4B correlated-subquery
predicate) are excluded from the function walk as non-function syntax; nested
calls inside them are still checked independently. Allowed names populate
`referenced_functions`. Static policy uses the parsed SQLite AST, never regex
or semicolon heuristics as the primary authority. Rejected SQL will expose
`generated_sql` but leave `executed_sql` null. **The static SQL-safety
foundation (Slices 1–4D) and the U3 authorizer/execution boundary are both
now complete**; `QueryService`, provider adapters, and the product CLI
remain.

Physical-source classification uses only `scope.sources`: `exp.Table` is a
physical candidate; nested `Scope` is CTE/derived. `scope.tables`, raw
`find_all(exp.Table)`, and `qualify()` are not authorization authorities.
Unqualified resolution is locked to local-ambiguity-first, no-outer-climb
semantics; ORDER BY alias resolution is the only projection-alias context
supported. Column matching stays SQLite-compatible ASCII case-insensitive
(non-ASCII code points preserved; no Unicode casefold) with
inventory-canonical names, no rewrite of `original_sql`, and no in-place
AST identifier mutation during authorization. All 14 executable development
anchors pass the complete static validator
(`tests/unit/sql_policy/test_anchor_compatibility.py`).

## Query service and CLI

`bse_nlq.service.answer_question` is the single orchestrator (D-008: one
service for every mode). Pipeline: `PromptInput` -> `build_prompt` -> exactly
one `generator.complete()` call -> `parse_model_decision_json` ->
`ModelDecision` branch -> `validate_sql` -> `execute_validated_sql` ->
`render_result` -> `QueryResult`. No retry, repair, or second semantic
attempt anywhere in this path.

`QueryResult.terminal_state` is a closed `TerminalState` enum matching the
project's frozen terminal-state contract
(`docs/planning/architecture-workshop.local.md` D-007 §18): `answered`,
`answered_empty`, `clarification_required`, `unsupported`,
`invalid_model_output`, `query_rejected`, `invalid_sql`,
`execution_limit_exceeded`, `execution_error`, `provider_unavailable`,
`internal_error`. `result_truncated` is the one state from that contract
intentionally not implemented: U3 hard-rejects row/column overflow rather
than truncating, so it is unreachable by design. `generated_sql` is set
whenever the model produced SQL, even if later rejected; `executed_sql` is
set only once SQL was submitted to SQLite, and is always byte-identical to
`generated_sql`. Only the outermost `answer_question` catches a bare
`Exception`, mapping any unexpected failure to `internal_error`; every more
specific failure is handled by its own typed exception first.

Rendering (`render_result`) is deliberately narrow: empty result, one scalar
(currency when the column name ends in the project's `_cents` convention,
otherwise a plain number or string), one aggregate row, and multiple
rows as a small table. No semantic type inference or narrative generation;
a column not ending in `_cents` renders its raw value rather than a guessed
unit.

`bse_nlq.provider_openai.OpenAIRawGenerator` is the one production
`RawModelGenerator`: GPT-5 mini via the OpenAI Responses API, requesting
`model_decision_json_schema()` as strict structured output. Every
`openai.APIError` (connection, timeout, rate limit, service, or auth
failure) maps to `ProviderUnavailableError` -> `provider_unavailable`; the
SDK's own bounded transport retries are the only retry behavior. No second
provider, no failover, no model selection logic.

`bse_nlq.cli` (`bse-nlq ask "question"`, `[project.scripts]` entry point) is
a thin wrapper: argument parsing, database-path resolution
(`--db` / `$BSE_NLQ_DB` / `./bse_nlq.db`), and output rendering only. A
missing `OPENAI_API_KEY` is checked before any database or provider access
and fails closed with a clear message and no network attempt. Generated and
executed SQL are shown as deliberate user-facing output (transparency), not
logged as a diagnostic; API keys, full prompts, raw provider responses,
questions, and raw SQL/rows are never logged by default.

## Data and prompting

The dataset will be synthetic, BSE-flavored ticketing data produced by a deterministic seed. SQLite owns structural facts; version-controlled semantic metadata at `src/bse_nlq/metadata/schema.json` owns meanings, units, synonyms, categories, visibility, and business definitions. The typed loader is `bse_nlq.metadata.load_semantic_metadata(connection)`, which validates the packaged JSON (including duplicate-key rejection), returns deeply frozen nested mappings, and reconciles every physical application column plus exact foreign-key join guidance against SQLite introspection without restating types, keys, or nullability.

Money is stored as integer cents. Dates use ISO text and half-open ranges. Relative dates are resolved from an explicit `as_of`; machine-clock SQL is prohibited. Default `as_of` is `2026-03-15` when the caller omits it.

Revenue definitions must state included statuses and refund treatment. Currency formatting is applied only when a unit can be proven from the projection and trusted metadata. Unknown units remain raw; a proven alias/unit contradiction is rejected.

`build_prompt` assembles stable system instructions (application rules, introspected physical schema, semantic metadata), a clearly delimited user-question block, and the ModelDecision response schema. Raw sample rows, seed literals, reconciliation totals, and `orders.order_ref` are excluded from model-facing sections.

## Persistent database artifact

`bse_nlq.db.build_database(destination, *, overwrite=False) -> DatabaseBuildResult`
composes the approved `apply_schema` and `load_seed_data` APIs into a filesystem
SQLite file. The builder validates destination preconditions (parent must exist;
existing destinations must be non-symlink regular files when overwritten),
builds into a unique temporary sibling, validates the temporary database
(enabling `PRAGMA foreign_keys` on the construction connection only — foreign-key
enforcement is connection-local, not a permanent file property), computes file
size/SHA-256/header checks and the logical fingerprint from the closed temporary
artifact **before** publication, then publishes with atomic no-clobber `os.link`
when `overwrite=False` or `os.replace` when `overwrite=True`. After successful
publication it removes exact destination `-wal` / `-shm` / `-journal` sidecars
before returning; a post-publication hygiene failure reports that publication
already occurred and does not claim the previous destination survived.
Concurrent external use or mutation of the destination during publication is
unsupported. Generated `*.db` / `*.sqlite` / `*.sqlite3` files are gitignored
and must not be committed. Logical content is fingerprinted for
cross-environment reproducibility; SQLite file bytes are not claimed portable
across engines or platforms. The developer utility
`python -m bse_nlq.db.build PATH [--overwrite]` is not the product `ask` CLI.
Read-only runtime opening is `open_readonly_database`; it is not a query
service and does not install an authorizer, progress handler, or executor.

## Interface and states

The submitted interface is a CLI with an `ask` command, stdin support, strict `--as-of`, `--json`, and a secret-free `--show-prompt` diagnostic. A GUI and multi-turn interaction are out of scope.

Terminal states distinguish successful answers, empty or truncated results, clarification, unsupported questions, invalid model output or SQL, policy rejection, execution limits or errors, provider failure, and internal failure. Every SQL-bearing result labels whether the SQL ran.

## Testing and evaluation

Automated tests must run without credentials, network access, model cost, or provider nondeterminism. They cover pure components, provider adapters with stubbed clients, database integration with a deterministic fake generator, the CLI, and each safety layer in isolation.

Evaluation measures deployed model systems through the real pipeline. Development cases may guide prompt changes; the holdout is locked after the prompt, metadata, schema, candidates, and thresholds are frozen. Answerable cases are scored by executed-result equivalence with hand-reviewed reference queries, not SQL-string equality.

Safety is a non-compensatory gate: one unsafe execution disqualifies a candidate. Among candidates meeting the frozen quality gate, select the least expensive eligible system.

## Observability and reproducibility

Structured logs go to stderr and omit raw questions, prompts, SQL, results, and model output by default. One completion event records state, reason, timings, provider metadata, reported token use, row count, and truncation.

Python and dependencies are pinned with `uv`; seed generation and schema rendering are deterministic; `as_of` is explicit; formal evaluation artifacts are frozen and hashed.

## Known limitations

- Synthetic data and hand-written metadata limit external validity.
- SQLite provides process-level rather than role-level read-only enforcement.
- SQLite compilation, not the static validator, resolves full column scope.
- Unit inference intentionally fails closed to unknown for unsupported expressions.
- The row cap bounds materialization, while the progress handler bounds computation.
- Prompt delimiting reduces injection risk but is not a security boundary.
- The planned holdout is small, so results will be descriptive.

Deferred: PostgreSQL role enforcement, GUI, SQL repair, multi-turn memory, generalized provider abstraction, and full scope-aware semantic validation.
