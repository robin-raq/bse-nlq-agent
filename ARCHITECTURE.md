# Architecture

**Status: approved target design. Implementation pending.**

This document describes the **approved design** of the BSE Natural Language Query
agent, the reasoning behind the load-bearing choices, and the boundaries the
implementation must respect. No application code, database, test, or evaluation
result exists yet.

Throughout, statements about the architecture are written in the present tense
because the subject is the approved design. Statements about what the software
does are written as requirements — "must", "will" — because the software does not
exist yet.

## Design principle

The foundation model is the only intentionally nondeterministic component in the
design. Everything after it must be deterministic application code.

The model has exactly one responsibility: translate a natural-language question
into a typed query decision. It must not execute SQL, select tools, control
workflow, or retry itself. The application owns orchestration because the
workflow is fixed and known in advance.

**One semantic model-generation attempt per request.** The SDK may make bounded
transport retries for transient provider failures, but the application must never
ask the model to regenerate, repair, or correct its content.

## Request pipeline

```
question
  → deterministic date resolution
  → prompt assembly using cached schema context
  → one semantic model-generation attempt
  → provider schema enforcement
  → local ModelDecision invariants
  → SQLGlot AST policy
  → projection unit inference and alias-consistency validation
  → SQLite read-only execution under the default-deny authorizer
  → raw execution result
  → deterministic formatting using proven unit metadata
  → typed terminal state
```

Unit analysis happens **before** execution. It reasons about the query's
projection expressions, not about returned values, so a unit is established as a
property of the query rather than guessed from data.

## Component responsibilities

The single named application package is **`src/bse_nlq/`**. No second top-level
package is approved. Modules are created only when they contain real
implementation or an immediately required contract; the speculative placeholder
packages currently in the repository will be removed during the isolated
restructuring change and no replacement empty scaffolding will be created.

*Target module layout, relative to `src/bse_nlq/`. None of these files exist yet.*

| Component | Owns |
|---|---|
| `service.py` | Orchestration, terminal-state mapping, request identity |
| `dates.py` | Strict ISO validation, configured `as_of`, half-open boundary resolution |
| `schema/introspect.py` | Live structural facts read from SQLite |
| `schema/metadata.py` | Declared semantic meaning; coverage validation |
| `schema/render.py` | Deterministic schema-context rendering |
| `prompt.py` | Prompt composition only; consumes already-resolved dates |
| `model/base.py` | `QueryGenerator` contract, `QueryRequest`, `ModelDecision` |
| `model/transports.py` | Shared schema and invariant validation, plus the two explicit transport paths: OpenAI Responses and Groq Chat Completions |
| `model/fake.py` | Deterministic test double |
| `sql/validate.py` | Static AST policy |
| `sql/authorizer.py` | Runtime default-deny authorization |
| `sql/units.py` | Projection unit lineage and alias-consistency validation |
| `db.py` | Read-only connection, execution budget, fetch cap |
| `format.py` | Deterministic rendering; currency only where the unit is proven |
| `observability.py` | Structured logging, redaction, completion event |
| `evaluation.py` | Thin harness that reuses `QueryService` |
| `contracts.py` | Shared typed boundaries |
| `errors.py` | Typed exceptional control flow |

A successful result is a contract, not an error. Ordinary outcomes must never be
represented as exceptions.

## Trust boundaries

Untrusted input consists of the user's question and **everything the model
returns**. Trusted inputs are the introspected schema, the curated semantic
metadata, and application code.

When strict provider-side schema enforcement is available and verified, it
constrains the *shape* of a response only. It establishes nothing about SQL
safety, SQL correctness, result correctness, or business correctness.
Prompt instructions request correct behavior; deterministic validation enforces
the permitted boundary.

## SQL safety

Every **static** decision about the submitted SQL's structure must be made from
the parsed AST and the introspected schema — never through regular expressions,
semicolon counting, or other raw-string heuristics. Runtime enforcement belongs
to SQLite.

The design specifies **six independent safety layers**, with different failure
modes:

| Layer | Control |
|---|---|
| Connection | Database opened with URI `mode=ro` |
| Session | `PRAGMA query_only=ON` |
| Static policy | SQLGlot AST validation |
| Runtime | Default-deny `sqlite3` authorizer returning `SQLITE_DENY` |
| Computation | Progress-handler instruction budget |
| Materialization | Fetch cap |

Independence is the point. A construct that SQLGlot parses differently from
SQLite still meets the authorizer, which runs inside SQLite on the real execution
plan. A misconfigured authorizer still meets the read-only connection. No single
mistake should open a write path.

The fetch cap bounds returned materialization; the progress handler bounds
computation. Neither replaces the other.

**The approved test plan requires each layer to be tested independently, with the
others deliberately bypassed**, so that a passing test would identify *which*
control held.

### Static policy

- Exactly one non-empty parsed statement
- Approved read-only query family only; fail closed on every other root
- Full-tree walk rejecting mutation, DDL, administrative, and
  connection-changing constructs anywhere in the tree
- Recursive CTEs rejected
- Physical source tables validated against the introspected schema, with CTE and
  derived-relation names distinguished from physical tables
- One shared function policy, applied in AST validation where representable and
  in authorizer function handling where applicable
- Clock-dependent constructs rejected, so SQL cannot reintroduce machine-clock
  dependence after the application has resolved dates deterministically

Generated SQL must never be rewritten. When a query executes, the executed SQL
must be byte-for-byte identical to the generated SQL, which is what makes the
transparency claim precise.

### Machine-contract identifiers

The design names three identifiers that appear in the typed result and in
rejection reporting.

| Identifier | Meaning |
|---|---|
| `generated_sql` | The SQL the model produced |
| `executed_sql` | The SQL actually submitted to SQLite |
| `result_unit_mismatch` | Reason code for a proven unit/alias contradiction |

- **Rejected or invalid SQL:** `generated_sql` is present and `executed_sql` is
  **null**.
- **Executed SQL:** both are present and **byte-for-byte identical**, because the
  application does not rewrite SQL.
- **A proven contradiction between an inferred unit and the model's alias** maps
  to terminal state `query_rejected` with reason code `result_unit_mismatch`.

The exact serialized response schema — the full field list of the `--json`
contract — is **implementation pending** and is not specified further here.

## Dataset and database

A small synthetic BSE-flavored ticketing and events schema, to be generated from
a deterministic seed script that will be committed with the implementation. The
data is synthetic and the README says so plainly.

- SQLite, standard-library `sqlite3`, no server
- Explicit primary and foreign keys, `NOT NULL` where appropriate, and `CHECK`
  constraints for statuses, quantities, and monetary values
- Foreign-key enforcement must be enabled and verified during seeding
- The schema will store money as integer cents; revenue arithmetic is then exact
- Dates stored as ISO-8601 text and filtered with half-open ranges
- Deliberate edge cases: canceled events, refunds, zero-dollar tickets, and a
  guaranteed empty-result scenario
- The database is generated, not committed; a missing database must produce a
  clear error rather than a silently incomplete one

### Monetary semantics

Revenue is a business definition, not only a SQL question. The metadata must
declare whether revenue means gross or net, how refunds affect it, and which
statuses are included, and those rules must appear in the rendered model context
rather than being assumed from column names.

Because computed columns carry no declared unit, the application must never guess
one. A unit is honored only when it can be proven from the projection AST and
trusted metadata. A proven contradiction between an inferred unit and the model's
alias is rejected before execution. When a unit cannot be proven, the value is
returned raw and unformatted — which is a safe and valid outcome.

## Schema context and prompting

Structure comes from the database. Meaning comes from explicit metadata.

SQLite is authoritative for tables, columns, types, nullability, and keys. The
metadata sidecar is authoritative for meaning, units, business definitions,
synonyms, declared categorical domains, and prompt visibility. Metadata must never
duplicate SQLite-owned facts, so there are no competing sources of truth.

Every introspected table and column must be accounted for in validation, but
obvious identifiers do not require prose — fields are classified as documented,
self-explanatory, or excluded with a recorded reason. This gives semantic drift
detection without generating meaningless descriptions.

Declared categorical domains are included because they affect interpretation and
filtering. Arbitrary data rows must not be injected: declared domains are part of
the schema's meaning, while individual rows are data, and injecting them would add
prompt size, accidental overfitting, and a data-disclosure risk in any production
extension.

Schema context is built and validated once per process, after the database is
initialized, foreign-key enforcement is enabled, introspection succeeds, and
metadata validation and coverage checks pass. Startup must fail clearly if
metadata and the live schema disagree. The stable context is cached; the user
question, resolved date boundaries, configured `as_of`, and request identity are
assembled per request.

Prompting begins from a zero-shot baseline. Few-shot examples will be added only
if evaluation identifies recurring failure modes that examples materially improve,
they must remain disjoint from both evaluation manifests, and each must trace to
an observed failure. The README will state whether examples were ultimately used
and how that choice was justified.

The user's question is inserted as clearly delimited, untrusted data, and the
prompt states that content inside the delimiter is a request to analyze rather
than a source of instructions. This is risk reduction, not a security boundary —
security authority remains with the deterministic controls downstream.

## Model integration

A direct OpenAI-compatible SDK. No agent framework: the application has a fixed
sequence with no dynamic tool selection, multi-step planning, memory, or
autonomous loop. Orchestration exists, but application code owns it.

One narrow internal contract isolates the external dependency:

```
QueryGenerator.generate(QueryRequest) -> ModelDecision
```

The production adapter and a deterministic fake will implement it. This is a
testability and replaceability seam, not a provider abstraction layer, and it does
not imply runtime model switching. The submitted application must expose no model
selector, no provider failover, and no silent fallback.

### The `ModelDecision` contract

Every provider-completed response maps to one flattened object with all four
fields present.

| Field | Type |
|---|---|
| `status` | one of `sql_generated`, `clarification_required`, `unsupported` |
| `sql` | string or null |
| `clarification` | string or null |
| `explanation` | string or null |

All four fields are required at the schema level; additional properties are
prohibited; optional values are expressed as nullable rather than omitted.

Local invariants, enforced by the application after a shape-valid object
arrives. All four fields are specified for every status.

| `status` | `sql` | `clarification` | `explanation` |
|---|---|---|---|
| `sql_generated` | nonempty string | **null** | string or null |
| `clarification_required` | **null** | nonempty string | string or null |
| `unsupported` | **null** | **null** | nonempty string, a concise user-facing reason |

Any contradiction, or any missing required semantic value, maps to
`invalid_model_output`.

**When strict provider-side schema enforcement is available and verified, it
constrains response shape only. Local application validation owns the
cross-field invariants.** Neither layer guarantees SQL safety, SQL correctness,
result correctness, or business correctness.

No discriminated-union dependency is introduced. The flattened shape keeps the
contract enforceable on endpoints whose strict mode supports only a subset of
JSON Schema.

Sampling parameters stay at supported defaults. The model must never be described
as deterministic. Variability is reduced through a fixed model ID, a tightly
scoped prompt, explicit business definitions and schema context, deterministic
date resolution, structured output, and deterministic validation.

### Candidate model systems

The comparison is between **deployed model systems**, not abstract weights.
Both endpoints have been verified eligible by a single-request endpoint smoke
test; neither has been evaluated for quality.

| Role | System | Endpoint status |
|---|---|---|
| MVP path | GPT-5 mini through the OpenAI API, Responses transport | Eligible |
| Comparison candidate | `openai/gpt-oss-120b` through Groq, Chat Completions transport, Groq-issued credentials | Eligible |

Eligibility means the endpoint authenticated, accepted the exact model
identifier, accepted the strict flattened `ModelDecision` schema, and returned an
object that passed local invariant validation. It does **not** mean the model
produces correct SQL. Final model selection remains gated behind the frozen
D-010 quality, safety, latency, and cost evaluation, which has not run.

The MVP must not be delayed or weakened to preserve a nominal two-model
comparison.

### Model transport design

The two endpoints share a contract but differ at the request/response boundary,
so the design is a **shared core with one small provider-specific branch** — not
configuration-only reuse.

```
QueryService
  → QueryGenerator contract          (one interface)
      → shared: prompt payload assembly, strict flattened schema,
        ModelDecision parsing, local invariant validation,
        normalized error vocabulary, transport retry policy
      → branch: OpenAI Responses transport
      → branch: Groq Chat Completions transport
  ← normalized ModelDecision
```

The branch covers API surface, schema request nesting, output extraction,
status/finish representation, token-limit parameter, and usage-field extraction.
Everything else is shared.

This is not a provider framework and does not authorize runtime failover or a
model selector. The submitted runtime uses **one selected provider**; the second
transport exists so evaluation can instantiate either eligible candidate
deliberately.

## Terminal states

*Approved target contract.*

| State | Meaning |
|---|---|
| `answered` | Query executed, rows returned |
| `answered_empty` | Query executed successfully, no rows matched |
| `result_truncated` | More rows exist than the fetch cap returns |
| `clarification_required` | The question is materially ambiguous |
| `unsupported` | The schema cannot answer the question |
| `invalid_model_output` | Model content unusable; no regeneration attempted |
| `query_rejected` | Blocked before execution, with a reason code |
| `invalid_sql` | Model output did not parse |
| `execution_limit_exceeded` | Execution budget stopped the query |
| `execution_error` | SQLite reported an execution failure |
| `provider_unavailable` | Provider failed after bounded transport retries |
| `internal_error` | Unexpected application failure |

An empty result is a success, not an error.

Rejection reasons must be machine-readable and must distinguish a policy mismatch
from an attack — not every rejected query is malicious, and a validator false
positive must not be reported as one.

Generated SQL will be displayed for every SQL-bearing outcome, labeled
*"Generated SQL — not executed"* when it was blocked and *"Executed SQL"* when it
ran. The system must never imply a rejected query was executed. The per-state
display rules are tabulated in
[`docs/diagrams/request-flow.md`](docs/diagrams/request-flow.md).

## Response formatting

Formatting must be deterministic application code. There is no second model call
to write the answer, which means the response cannot assert anything the executed
result does not support — a correctness property, not merely a simplification.

Raw execution values must be preserved unchanged for JSON output, evaluation,
tests, and debugging. Human-readable formatting is a presentation layer applied
afterward and must never mutate the underlying values. Currency is rendered with
exact decimal arithmetic only where the unit was proven to be cents.

An alias communicates the model's claimed intent; it is not evidence. The
formatter must not narrate business semantics from an alias, so a name containing
"net" never becomes a claim that refunds were handled correctly. That remains an
evaluation concern.

## Interface

A command-line interface will be the only submitted interface. Graphical
interfaces are deferred.

All modes must call the same application service, so the CLI never duplicates
prompt construction, model invocation, validation, execution, terminal-state
mapping, unit analysis, or formatting policy.

- `ask` is the primary path, with stdin input supported
- `--as-of` is validated strictly; when omitted, the configured application
  default applies and the machine's current date must never be silently
  substituted
- `--json` emits exactly one JSON object on stdout while diagnostics go to
  stderr, and it is the stable machine contract the evaluation harness consumes
- `--show-prompt` is an explicit, secret-free diagnostic and cannot be combined
  with `--json`
- Exit codes are coarse because the typed state is authoritative
- Model-produced SQL and text must render as terminal-safe plain text; HTML, ANSI
  escapes, and other control characters must never be interpreted

## Testing

**The approved test plan requires that no automated test invoke a live model
endpoint.** The full suite must run with no API key, no network, no model cost,
and no provider nondeterminism. Live smoke tests and evaluation will be separate
explicit commands.

The layers will be unit tests, adapter contract tests against stubbed clients,
integration tests against a freshly seeded temporary database with a fake
generator, and CLI tests exercising the real entry point. Safety layers must be
tested independently, bypassing the others.

The fake generator must honor the `QueryGenerator` contract: valid responses are
valid `ModelDecision` objects, and failures are raised as typed errors. A
contradictory raw payload cannot honestly be a valid decision, so those must be
covered by tests at the adapter boundary where they actually originate.

## Evaluation

Evaluation measures the model; tests measure the application. Synthetic malformed
output and provider failures will be injected deterministically in tests, while
the evaluation records failures that occur naturally.

Development cases will drive prompt diagnosis and any few-shot decision. A
**locked holdout** will be used only after the prompt, metadata, schema,
candidate configurations, and quality gate are frozen and recorded. Using holdout
failures to tune the prompt and then continuing to describe those cases as unseen
is not permitted; the honest outcomes are a failed final evaluation or a clearly
labeled reused validation set.

The evaluation will measure correctness by executing the candidate SQL through
the real pipeline and comparing results against hand-reviewed reference SQL over
the same frozen database. Exact SQL-string matching is rejected because
semantically equivalent queries differ in aliases, join order, subquery structure,
and aggregate construction. Comparison uses multiset semantics by default, since
duplicates are meaningful in SQL; ordering is compared where ordering is part of
the answer; cents compare exactly with no floating-point tolerance.

Results will be reported as pipeline-stage metrics rather than a single accuracy
number, so a schema failure, incorrect SQL, a validator rejection, and an
execution failure never collapse together. Each case will run multiple times, and
both per-run success and all-runs consistency will be reported. Majority-of-runs
is a diagnostic statistic only — it must never be a selection metric and must not
be implemented in the application, because production makes one semantic
model-generation attempt per request.

The quality gate is precommitted. Zero unsafe executions is non-compensatory: no
cost or accuracy advantage offsets one. Unsafe SQL *generation* will be reported
separately from unsafe *execution*, since a blocked prohibited query is a model
failure and a control success. Failed thresholds must never be lowered
retroactively.

The harness must reuse `QueryService` and consume the typed result or the same
JSON serialization as `--json`. It must never parse human-readable output.

## Observability

Newline-delimited JSON to stderr through the standard library, default level
`WARNING`, no hosted platform and no tracing dependency.

Exactly one canonical completion event must be emitted per request, for every
terminal state, carrying request identity, resolved `as_of`, state and reason
code, provider and model identity, latency, token usage where the provider
reports it, validation and execution outcomes, timings, row count, and
truncation. Token fields stay null when unreported; usage must never be estimated
or fabricated.

Raw user questions must not be logged by default — character counts and optional
stable hashes are. Raw input logging requires an explicit opt-in and must never
apply at the default level. The full prompt must never be written to logs at any
level; only hashes and metadata, with the prompt reachable solely through the
user-invoked diagnostic flag. Generated SQL appears in logs as a hash, since the
SQL itself is already available in the response, the JSON result, the evaluation
report, and tests.

This is a synthetic-data exercise, but the architecture should not normalize
capturing arbitrary user text without an explicit policy. A real deployment would
require retention, access, and privacy decisions first.

## Reproducibility

- Python pinned to 3.13, managed with `uv`; the approved runtime requires a
  committed `uv.lock`
- A deterministic seed script, to be committed with the implementation; repeated
  generation must produce equivalent schema and data
- Deterministic schema-context rendering with stable ordering
- Explicit `as_of` with no machine-clock fallback, and clock-dependent SQL
  rejected
- Evaluation artifacts frozen and hashed before formal results are viewed

## Known limitations of the approved design

- The dataset will be synthetic. Metadata is hand-written, so coverage validation
  can prove completeness, not accuracy.
- Column-to-table binding will be resolved by SQLite during compilation rather
  than by the static validator. The system does not claim full alias-and-scope
  validation.
- The planned unit analyzer intentionally covers only the expression family the
  evaluation requires. Unsupported expressions will return unknown, and unknown
  values will be returned raw.
- Read-only enforcement will be process-level rather than role-level. A database
  role with genuine read-only permissions would be stronger.
- The fetch cap will bound returned rows, not the work SQLite performs to produce
  them.
- Prompt delimiting reduces injection risk but is not a security boundary.
- Alias claims will be checked against inferred units, but this will not prove
  gross/net business-formula correctness.
- The planned evaluation uses a small locked holdout, so its results will be
  descriptive rather than broad statistical evidence.

## Deliberately deferred

PostgreSQL with role-level read-only enforcement and a real statement timeout; a
graphical interface; a bounded one-shot SQL repair attempt; sample-row injection
as a measured enhancement; a semantic business-formula validator; multi-turn
memory; a generalized provider abstraction; full alias-and-scope column
resolution.
