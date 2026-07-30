# Architecture

> Approved target design. Schema, seed, semantic metadata, ModelDecision
> validation, deterministic prompt construction, and the persistent database
> builder are implemented; read-only runtime connections, provider adapters,
> SQL policy, execution, and the product CLI remain pending.

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
| Database | Schema/seed, persistent artifact build, read-only connections, authorizer, and limits |
| Formatting | Human and JSON output from executed values |
| Evaluation | Frozen cases, reference queries, and reporting |

All implementation lives in the single `src/bse_nlq/` package. Modules should be created only when they contain real behavior.

Implemented module paths for this phase:

- `bse_nlq.db` — `apply_schema`, `load_seed_data`, `build_database`
- `bse_nlq.metadata` — `load_semantic_metadata`
- `bse_nlq.decision` — `ModelDecision`, `parse_model_decision_json`, `model_decision_json_schema`
- `bse_nlq.prompt` — `PromptInput`, `BuiltPrompt`, `build_prompt`
- `bse_nlq.generator` — provider-neutral `RawModelGenerator` / `decide_from_raw_generator` (offline boundary; no live adapters)

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

The MVP endpoint is GPT-5 mini through OpenAI Responses. The comparison candidate is `openai/gpt-oss-120b` through Groq Chat Completions. Both passed endpoint compatibility checks; neither has been evaluated for SQL quality.

## SQL safety

Static policy uses the parsed SQLite AST and introspected schema, never regex or semicolon heuristics. It requires one approved read-only statement, rejects forbidden constructs and recursive CTEs, validates physical tables separately from CTE names, applies a fail-closed function policy, and rejects clock-dependent SQL.

Execution uses independent controls:

1. SQLite URI opened with `mode=ro`.
2. `PRAGMA query_only=ON`.
3. SQLGlot AST policy.
4. Default-deny SQLite authorizer.
5. Progress-handler instruction budget.
6. Result-row cap.

Each layer must be tested independently. Rejected SQL exposes `generated_sql` but leaves `executed_sql` null.

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
Read-only runtime connection factories remain a later boundary.

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
