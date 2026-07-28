# Architecture Decisions

Approved decisions from the architecture workshop. Each entry records the
decision, why it was made, what it costs, and how it will be validated.

## Authority order

1. Current task instructions
2. Exercise requirements
3. Approved decisions in this document
4. The active approved implementation plan, when one exists
5. `ARCHITECTURE.md`
6. Repository workflow instructions in `AGENTS.md`
7. `PROJECT_STATUS.md` as the current operational handoff
8. `README.md` and other supporting documentation

Then general engineering best practices.

`PROJECT_STATUS.md` owns the current phase, verified state, blockers, and the
exact next action; it is **not** architecture authority. An implementation plan
may sequence approved work but may **not** override an architectural decision.

**No Compound Engineering implementation plan currently exists.** Until one is
created and approved, this document and `ARCHITECTURE.md` govern design, while
`PROJECT_STATUS.md` records the immediate operational handoff.

Status of all entries below: **Approved 2026-07-27 / 2026-07-28.** No
implementation has been written; these are specifications.

---

## D-001 — Dataset and domain

**Decision.** A deliberately small synthetic BSE-flavored ticketing and events
dataset, around five or six tables, generated reproducibly from a deterministic
seed script that will be committed with the implementation. A further table is
added only when required by one of the exercise's example questions or by a
meaningful evaluation case.

**Context.** The exercise permits any structured dataset and explicitly names
Chinook and AdventureWorks, but it prints three BSE-specific example questions
referencing the Brooklyn Nets, Barclays Center, ticket sales, event categories,
and revenue. Dataset choice has the widest downstream reach: schema context,
few-shot examples, evaluation cases, test fixtures, and the README narrative all
derive from it.

**Options considered.** A synthetic BSE-flavored schema; an off-the-shelf dataset
such as Chinook; a real public sports or entertainment dataset.

**Rationale.** Only a domain-accurate schema can answer the questions the
exercise's authors printed, which are the questions a reviewer is most likely to
type. Chinook cannot answer any of them and is the most common text-to-SQL demo
dataset in existence. A real public dataset carries the highest sourcing and
cleaning risk, and most sports datasets cover game statistics rather than
ticketing and revenue. The small table count keeps every table earning its place
against the query complexity it must demonstrate.

**Consequences.** The seed script becomes a first-class deliverable and the
project's primary reproducibility artifact. Evaluation cases can carry
known-correct answers. Edge-case and empty-result coverage comes from the seed
design. The README must disclose plainly that the data is synthetic.

**Risks.** Because the schema, the data, and the evaluation questions are all
ours, accuracy figures are open to the charge of being self-graded. Mitigated by
committing the generator with a fixed seed so the data is inspectable rather than
hand-placed, and by deliberately seeding canceled events, refunds, zero-dollar
tickets, and a guaranteed empty-result case so the dataset can make the agent
fail. Prompt over-fitting is mitigated by keeping schema-context construction
generic.

**Validation.** Repeated seeding produces equivalent schema and data; each
example question has a hand-verifiable answer; at least one seeded scenario
returns no rows; edge-case rows are asserted present.

**Deferred alternatives.** Chinook, retained only as a schedule escape hatch.

---

## D-002 — Runtime, language, and dependency management

**Decision.** Python pinned to 3.13, managed with `uv` using `pyproject.toml` and
a committed lockfile. No separately maintained requirements file. A fallback
install path may reuse the same project metadata through a 3.13 virtual
environment, and is documented **only if** it is successfully tested from a clean
environment.

**Context.** The runtime gates library availability for SQL parsing and
validation, and it drives the exercise's explicit criterion that a new engineer
can set up and run the project without additional guidance.

**Options considered.** Python with a pinned interpreter under `uv`; Python on the
machine's system interpreter with pip; TypeScript on Node.

**Rationale.** Python provides a mature, dialect-aware SQL AST that supports the
deterministic validation controls this implementation requires, and it preserves
straightforward interface options. Pinning removes the machine's Python from the
project's dependency graph, reducing compatibility variance across the complete
dependency set — this is not a claim that any newer interpreter is unsupported.
`uv` supplies interpreter management, project synchronization, and a committed
lockfile, giving reviewers a reproducible primary setup path that a
package-only pin cannot.

**Consequences.** `uv` becomes an assumption in the recommended path. The
approved runtime requires a committed `uv.lock` as reproducibility evidence.
TypeScript is out for the remainder of the project.

**Risks.** A reviewer without `uv` meets an install step first. An untested
fallback would be worse than none, so an untested fallback is omitted rather than
claimed.

**Validation.** A clean clone synchronizes into a working environment; the test
suite runs through the project runner; the clean-environment fallback test is
executed before the README documents it.

**Deferred alternatives.** Python 3.12; Poetry or plain pip; TypeScript.

---

## D-003 — Database engine, lifecycle, and initialization

**Decision.** SQLite through the standard library, with the database generated by
the deterministic seed script rather than committed as a file. The seed script
itself will be committed with the implementation.

**Context.** The engine determines which read-only and execution-limit controls
are available, and the project does not claim any control it cannot demonstrate
with a test.

**Options considered.** SQLite; DuckDB; PostgreSQL.

**Rationale.** SQLite provides a simpler zero-server, standard-library path with
controls that fit this implementation and reviewer setup. PostgreSQL offers the
strongest enforcement but requires a server or container, which is setup friction
on a scored criterion. DuckDB's native date and decimal types are genuine
advantages, but they are addressable here — dates are resolved by the application
before prompting, and integer cents give exact revenue arithmetic.

**Consequences.** No dependency is added for the data layer. Tests receive a fresh
per-test database, providing an injection seam and no shared mutable state.
Revenue semantics become a documented business rule spanning schema context,
tests, evaluation, and the README.

**Approved specifics.** `STRICT` tables where the pinned environment supports
them, otherwise ordinary tables with explicit `CHECK` constraints; explicit keys
and constraints; foreign-key enforcement enabled and verified during seeding;
money as integer cents with gross and net revenue explicitly distinguished; ISO
dates with half-open ranges; relative-date boundaries resolved by the application
and injected, so the model never infers the current date; a bounded
query-execution guard implemented as a virtual-machine instruction budget with an
optional monotonic deadline — not described as a precise wall-clock timeout unless
the implementation and tests support that wording; a missing database produces a
clear error rather than a silently incomplete one.

**Risks.** `STRICT` support in the pinned interpreter requires verification. The
cents representation, and the gross-versus-net distinction, are plausible model
error surfaces. Read-only enforcement is process-level rather than role-level.

**Validation.** Repeated seeding produces equivalent output; foreign-key
enforcement verified during seeding; deterministic interruption proven with an
expensive query against a low budget; write attempts rejected, tested
independently at each layer.

**Deferred alternatives.** DuckDB; PostgreSQL with a read-only role and a real
statement timeout.

---

## D-004 — Model integration

**Decision.** A direct OpenAI-compatible SDK behind one narrow internal contract,
with provider-native structured output, deterministic downstream validation, one
production model in the submitted runtime, and a deterministic fake for tests.

**One semantic model-generation attempt per request.** The SDK may make bounded
transport retries for transient provider failures, but the application never asks
the model to regenerate, repair, or correct its content.

**Context.** This is the only intentionally nondeterministic component. The
decision defines where nondeterminism may live, what the boundary around it looks
like, and how the system behaves when the provider fails.

**Options considered.** A direct SDK; an agent framework such as LangChain or
LangGraph.

**Rationale.** The application has a fixed sequence with no dynamic tool
selection, multi-step planning, memory, or autonomous loop. A framework would add
a dependency and indirection to orchestrate a single call, and would bury the
prompt when clear prompt engineering is an explicitly scored criterion.
Orchestration exists, but application code owns it.

**Approved specifics.** One contract,
`QueryGenerator.generate(QueryRequest) -> ModelDecision`, with a production
adapter and a fake — a testability and replaceability seam, not a provider
abstraction layer, and not runtime model switching. A flattened `ModelDecision`:
all fields present and required at the schema level, optional values nullable,
with the provider enforcing shape and the application enforcing state invariants
and rejecting contradictions. Discriminated unions are avoided unless both live
endpoints prove support for the identical construct. Sampling stays at supported
defaults and the model is never described as deterministic. Safety rejection is a
hard stop with no regeneration, because re-prompting after a rejection builds a
loop that searches for output which passes or bypasses the validator. Execution
failure also stops, for a different reason: automatic repair would add cost,
latency, state transitions, failure modes, and new evaluation requirements. No
hidden fallback, no keyword matching, no handcrafted SQL; the fake never activates
automatically at runtime. Response formatting is deterministic, with no second
model call.

**Candidate systems.** The comparison is between deployed model systems, not
abstract weights. GPT-5 mini through the OpenAI API is the required MVP path.
`openai/gpt-oss-120b` through Groq, using Groq-issued credentials, is the
comparison candidate. Both endpoints have since been **verified eligible** —
see the provider-verification subsection below. The MVP is not delayed or
weakened to preserve a nominal two-model comparison.

### Provider verification (2026-07-28)

Endpoint eligibility only, one request per provider, harmless prompt unrelated
to the BSE dataset. **These are not quality claims.**

**OpenAI — eligible for MVP endpoint integration.**

- Responses API, default base URL
- Requested alias `gpt-5-mini`; observed returned identifier
  **`gpt-5-mini-2025-08-07`** — the alias and the resolved identifier are
  distinct and must not be conflated
- Strict flattened `ModelDecision` schema accepted
- Exact-field check and local invariant checks passed

**Groq — eligible for like-for-like comparison.**

- Chat Completions through the OpenAI-compatible base URL
  `https://api.groq.com/openai/v1`
- Model `openai/gpt-oss-120b`
- Same flattened schema accepted, with `strict: true` accepted
- Exact-field check and local invariant checks passed
- **Caveat:** the evidence supports endpoint eligibility but does **not**
  independently prove the provider's internal constrained-decoding mechanism.
  An explicitly requested undeclared property was absent from the response,
  which is strong evidence of schema constraint but not proof of mechanism.

Neither result establishes NLQ-to-SQL quality, SQL correctness, reliability,
production readiness, comparative latency or cost, or final model selection.
Selection remains gated behind the frozen D-010 evaluation.

### Adapter consequence — verified

The earlier configuration-only reuse hypothesis is **disproven**. The verified
conclusion is:

> **Shared core with one small provider-specific request/response branch.**

Shared across both providers:

- one `QueryGenerator` contract
- one `ModelDecision` schema
- one local invariant validator
- one normalized error vocabulary
- one shared retry policy at the transport boundary

Provider-specific:

- API surface (Responses vs Chat Completions)
- schema request nesting
- output extraction
- status / finish representation
- token-limit parameter
- usage-field extraction

Explicitly, this does **not** justify a generalized provider framework, and does
**not** authorize runtime provider failover. The final production runtime still
uses **one selected provider**. Evaluation may instantiate either eligible
provider deliberately. **No third provider is added.**

**Selection rule.** Choose the least expensive eligible model that satisfies the
precommitted quality gate. The threshold is written down before any formal results
are reviewed. If neither candidate passes, the threshold is not lowered
retroactively.

### The `ModelDecision` contract (authoritative)

Every provider-completed response maps to **one flattened object with all four
fields present**.

| Field | Type |
|---|---|
| `status` | one of `sql_generated`, `clarification_required`, `unsupported` |
| `sql` | string or null |
| `clarification` | string or null |
| `explanation` | string or null |

**Schema-level rules.** All four fields are required. Additional properties are
prohibited. Optional values are expressed as nullable rather than omitted.

**Local invariant rules**, enforced by the application after a shape-valid object
arrives. All four fields are specified for every status.

| `status` | `sql` | `clarification` | `explanation` |
|---|---|---|---|
| `sql_generated` | nonempty string | **null** | string or null |
| `clarification_required` | **null** | nonempty string | string or null |
| `unsupported` | **null** | **null** | nonempty string, a concise user-facing reason |

**Any contradiction, or any missing required semantic value, maps to
`invalid_model_output`.**

**Division of responsibility.** When strict provider-side schema enforcement is
available and verified, it constrains **response shape only**. Local application
validation owns the **cross-field invariants**. Neither layer guarantees SQL
safety, SQL correctness, result correctness, or business correctness — those are
established by the deterministic pipeline and by evaluation.

**No discriminated-union dependency is introduced.** The flattened shape is
chosen precisely so the contract remains enforceable on endpoints whose strict
mode supports only a subset of JSON Schema.

**Consequences.** The contract and fake are what make an offline test suite and a
reusable evaluation harness possible at all. Deterministic formatting means the
answer cannot assert anything the executed result does not support.

**Risks.** A reviewer without credentials sees provider failures, making the
offline path the primary demonstration route.

**Validation.** Adapter contract tests against stubbed clients; typed failures
exercised through the fake; a test asserting the model is not called again after a
safety rejection; a test asserting execution failure triggers no repair.

### Hosting disposition for the open-weight candidate

- **Groq-hosted `openai/gpt-oss-120b` is the only hosted open-weight comparison
  endpoint for this submission.** Its endpoint has been verified eligible.
- If Groq later becomes unavailable, inaccessible, or ineligible, the comparison
  is **recorded as blocked** — now a contingency rather than an expected path.
- GPT-5 mini proceeds as the MVP path pending D-010 model selection.
- **Fireworks and other hosting providers are deferred alternatives**, not active
  fallbacks.
- The application must **not** automatically try another provider.
- **No third provider is to be added during the MVP** merely to preserve the
  two-candidate comparison.

Earlier private workshop notes explored Fireworks as a primary or fallback host.
**Tracked decisions in this document override superseded private workshop
experiments.** Where an ignored local note and this document disagree, this
document governs.

**Deferred alternatives.** Anthropic Claude; Amazon Bedrock; Fireworks or another
hosted open-weight provider; a second constrained model call for formatting; a
bounded one-shot SQL repair.

---

## D-005 — Schema context and prompt construction

**Decision.** A hybrid: structural facts introspected from the initialized SQLite
database, business meaning declared in a small version-controlled metadata
sidecar, merged deterministically when schema context is built.

Governing rule: **structure comes from the database, meaning comes from explicit
metadata.**

**Context.** Clear prompt engineering and appropriate use of context is the first
row of the exercise's evaluation table. This decision also determines whether the
two most common text-to-SQL failures — hallucinated identifiers and wrong business
semantics — are prevented or created.

**Options considered.** Runtime introspection only; a hand-curated static schema
document; the hybrid.

**Rationale.** The two mechanisms fail in different ways. Introspection cannot
drift but is silent on meaning: no amount of reading DDL reveals that a column
holds cents or that revenue is net of refunds. Static prose can carry meaning but
is a copy rather than a source, so its structural claims can become false with
nothing detecting it. The hybrid uses each mechanism for the job the other
structurally cannot do, and coverage validation catches metadata going stale
against a schema that moved.

**Approved specifics.** Metadata never duplicates SQLite-owned facts such as types
or foreign keys. Every table and column is accounted for, but obvious identifiers
need no prose — fields are classified as documented, self-explanatory, or excluded
with a recorded reason, giving drift detection without meaningless descriptions.
Declared categorical domains are included; arbitrary data rows are not, because
domains are schema meaning while rows are data. Rendering is deterministic with
stable ordering, concise rather than raw catalog output, and never constructed by
the model provider. Context is built and validated once per process after the
database and metadata pass their checks, with clear startup failure on
disagreement; only the stable portion is cached. Prompting begins zero-shot, and
few-shot examples are added only where evaluation shows a recurring failure mode
they materially improve, remain disjoint from both evaluation manifests, and trace
to an observed failure.

**Dataset coupling.** The introspection mechanism, metadata format, renderer, and
prompt builder are reusable. The semantic metadata, evaluation cases, and seed
data are intentionally dataset-specific. A new dataset requires new semantic
metadata. The throwaway-schema test proves the machinery operates on another
schema without implementation changes; it does not prove the system answers
questions correctly over an arbitrary database. The system is not described as
dataset-agnostic.

**Risks.** Metadata is hand-written, so coverage validation proves completeness,
not accuracy. Declining to sample rows means an unusual literal format could cause
a miss that sampling would have caught.

**Validation.** Rendering against a different schema fixture; metadata coverage
validation in both directions; deterministic rendering; a recorded zero-shot
baseline; few-shot and evaluation disjointness asserted by test.

**Deferred alternatives.** A curated static schema block; sample-row injection as
a measured enhancement.

---

## D-006 — SQL safety

**Decision.** Static AST policy validation combined with layered runtime
enforcement, treating all model output as untrusted.

Governing rule: **every static decision about the submitted SQL's structure is
made from the parsed AST and introspected schema, never through regular
expressions, semicolon counting, or other raw-string heuristics.** Runtime
enforcement belongs to SQLite. The AST alone is not claimed to defeat every
attack; the defense comes from independent controls with different failure modes.

**Layers.** Read-only connection URI; session-level query-only pragma; static AST
policy; default-deny runtime authorizer returning an explicit denial rather than a
silent ignore, installed for the complete prepare and execution lifecycle; a
progress-handler instruction budget; and a fetch cap. The fetch cap bounds
returned materialization while the progress handler bounds computation; neither
replaces the other.

**Static policy.** Exactly one non-empty parsed statement, counted structurally
rather than by separators. An approved read-only query family, failing closed on
every other statement root, described by behavior rather than by parser class
names until a spike verifies them. Recursive CTEs rejected. A full-tree walk
rejecting mutation, DDL, administrative, and connection-changing constructs
anywhere in the tree — a leading `WITH` clause cannot make a statement safe,
because SQLite permits it before writes as well as reads. Physical source tables
validated against the introspected schema, with CTE and derived-relation names
distinguished from physical tables. One shared function policy applied in AST
validation where representable and in authorizer function handling where
applicable, failing closed on unknown functions. Clock-dependent constructs
rejected, so SQL cannot reintroduce machine-clock dependence — a determinism rule
as much as a safety one.

**Column validation.** A broad check of every apparent column identifier against
the union of database columns was rejected: it falsely rejects legitimate
query-local names such as projection aliases used in ordering, and it does not
prove a base column belongs to the referenced table. The preferred approach is
scope-aware analysis distinguishing physical base columns from query-local names.
The accepted timeboxed alternative is to omit the broad rejection entirely and
allow SQLite's own compilation and name binding, under the read-only connection
and default-deny authorizer, to reject nonexistent or misbound columns — with the
limitation documented honestly. Full alias-and-scope validation is not claimed
unless it is implemented and tested.

**Execution.** The validated SQL is executed exactly as generated; no limit is
injected and the SQL is never rewritten, so displayed SQL and executed SQL are
identical. Rows are fetched up to the cap plus one to detect truncation. For a
truncated result the system reports the returned count and that more rows exist,
and explicitly does not claim to know the total.

**Consequences.** Generated and executed SQL are tracked separately, so a rejected
query shows generated SQL with no executed SQL. SQL is displayed as escaped plain
text and never rendered as HTML.

**Validation.** Each layer is tested independently with the others deliberately
bypassed, because a passing end-to-end test does not establish which control held.

---

## D-007 — Request and error state machine

**Decision.** Twelve typed terminal states, with deterministic response
formatting and no automatic repair.

**States.** `answered`, `answered_empty`, `result_truncated`,
`clarification_required`, `unsupported`, `invalid_model_output`,
`query_rejected`, `invalid_sql`, `execution_limit_exceeded`, `execution_error`,
`provider_unavailable`, `internal_error`.

**Rationale for specific distinctions.** An empty result is a success, not an
error — a true answer of "none" is still an answer. A blocked query is named
`query_rejected` with a machine-readable reason rather than an "unsafe" label,
because an unknown table, an unsupported but harmless function, or a validator
false positive is not an attack. An execution-budget interruption is separated
from an ordinary execution failure, because stopping a query deliberately is not
a database malfunction. A controlled catch-all exists because a state machine
claiming exhaustive handling needs one, and programmer errors must never be
silently mapped to provider or execution failures.

**Model failure handling.** Malformed, schema-invalid, or contradictory model
content is not sent back to the model for correction; it terminates as
`invalid_model_output`. A malformed but successfully delivered response is not a
transport failure. Provider errors are normalized to a single user-facing state
with an internal reason code and no cross-provider fallback.

**Unit handling.** Projection unit inference and alias-consistency validation run
**before** execution, from the parsed projection and trusted metadata. A proven
contradiction between an inferred unit and the model's alias is rejected with a
unit-mismatch reason. When the analyzer cannot prove a unit, no contradiction has
been proven: the query is not rejected on the alias alone, and the value is
returned raw and unformatted. The formatter never infers a unit from value
magnitude, runtime type, question wording, or an alias by itself.

**Display.** Generated SQL is shown for every state where SQL exists, labeled
"Generated SQL — not executed" when blocked and "Executed SQL" when it ran. States
with no SQL show none.

**Formatting.** Raw values are preserved for machine output, evaluation, tests,
and debugging. Human formatting is a presentation layer that never mutates them.
Currency conversion uses exact decimal arithmetic and applies only where the unit
was proven. An alias containing "gross" or "net" communicates claimed intent and
is not treated as proof that the business formula was followed.

---

## D-008 — Interface

**Decision.** A command-line interface is the only submitted interface.
Graphical interfaces are deferred.

**Options considered.** CLI; a minimal web interface; a notebook.

**Rationale.** The terminal-state machine is the most intricate part of the
system, and a CLI renders every state without additional presentation work. The
requirement that model-produced SQL be displayed as escaped plain text and never
as HTML is satisfied by construction rather than by care. The CLI is also directly
driveable from tests and reusable by the evaluation harness.

**Approved specifics.** All modes call one application service; the CLI never
duplicates pipeline logic. `ask` is the primary path with stdin support. `--as-of`
is validated strictly, defaults to the configured application value, and never
falls back to the machine clock. `--json` emits exactly one JSON object on stdout
with diagnostics on stderr, preserves raw values, and is the stable contract the
evaluation harness consumes rather than parsing human output. `--show-prompt` is
an explicit secret-free diagnostic and cannot be combined with `--json`. Exit
codes are coarse because the typed state is authoritative. Model output renders as
terminal-safe plain text with control characters neutralized. A REPL is optional,
stateless, and preserves no hidden model context; if omitted, the single-shot
command is documented as the primary interactive and scriptable workflow.

**Deferred alternatives.** Streamlit, Gradio, or a notebook interface.

---

## D-009 — Testing strategy

**Decision.** A fully offline automated suite with four test layers plus
independent safety-layer tests.

**Boundary.** No automated test invokes a live model endpoint. The suite runs with
no API key, no network, no model cost, no rate-limit dependency, and no provider
nondeterminism. Live smoke tests and model evaluation are separate explicit
commands and never run implicitly.

**Layers.** Unit tests over pure components, with especially thorough
table-driven coverage of unit-lineage inference because a silent unit error
produces a plausible but incorrect answer. Adapter contract tests against stubbed
clients, covering response conversion, refusals, malformed content, missing and
contradictory fields, error normalization, usage extraction, and secret-free
diagnostics. Integration tests against a freshly seeded temporary database using
the real pipeline and a fake generator, exercising every terminal state. CLI tests
against the real entry point.

**Type boundary.** The fake generator is not asked to return an object that
violates its own contract, because a contradictory payload cannot honestly be a
valid decision. Raw malformed payloads must be covered by tests at the adapter
boundary where they originate; service-level tests use typed raised failures.

**Safety.** Each layer must be tested with the others deliberately bypassed, so
that a passing test would identify which control held.

**Determinism.** Every integration database comes from the deterministic seed
process or an explicitly versioned fixture. Tests do not depend on execution
order, a developer's local database, mutable global files, machine timestamps, or
network state. Critical expected results are independently hand-verified rather
than trusted because a reference query produced them.

**Reporting.** Coverage may be a diagnostic, but the stronger evidence is explicit
coverage of every terminal state, every safety layer, every unit-lineage rule,
every provider error mapping, and the complete primary request path.

---

## D-010 — Evaluation strategy

**Decision.** A separated development set and locked holdout, scored by result
equivalence rather than SQL-string matching, against a precommitted quality gate.

**Set separation.** Development cases drive zero-shot diagnosis, failure-class
discovery, few-shot decisions, and iteration. The locked holdout is used only
after the prompt, metadata, structured-output schema, candidate configurations,
and quality gate are frozen and recorded. Using holdout failures to tune the
prompt and then continuing to describe those cases as unseen is not permitted; the
honest outcomes are a failed final evaluation followed by a new holdout, or a
clearly labeled reused validation set.

**Freezing.** Case manifests and their hashes, prompt and metadata versions,
database seed and hash, schema version, code commit, provider, exact model ID,
endpoint configuration, retry policy, concurrency, date context, repetition count,
comparator version, and thresholds are all recorded before formal results are
viewed, and are not adjusted for one candidate after seeing another's results.
Provider-specific request syntax may differ; semantics, cases, and scoring rules
may not.

**Scoring.** Exact generated-SQL matching is rejected as the primary oracle
because semantically equivalent SQL differs in aliases, join order, subquery
structure, CTE usage, aggregate construction, and predicate ordering. Candidate
SQL is executed through the real pipeline and compared against hand-reviewed
reference SQL over the same frozen database. Comparison uses multiset semantics by
default, since duplicates are meaningful in SQL; ordered comparison applies where
ordering is part of the answer; rankings use tie-aware invariants; cents compare
exactly with no floating-point tolerance. Result invariants are preferred where
exact row comparison would be artificially brittle. Clarification, unsupported,
and adversarial cases need no reference SQL and are scored on terminal state, the
absence of prohibited execution, and the appropriate rejection reason.

**Reporting.** Pipeline-stage metrics rather than a single accuracy number, so a
schema failure, incorrect SQL, a validator rejection, and an execution failure
remain distinguishable. Naturally occurring provider and execution failures are
counted and never removed from the denominator; latency percentiles state their
denominator explicitly. Each case runs multiple times; per-run success and
all-runs consistency are reported as primary, and majority-of-runs only as a
diagnostic — majority voting is neither a selection metric nor implemented in the
application, because production makes one semantic attempt per request.

### The precommitted quality gate

Written down and frozen **before any formal result is reviewed**.

**Evaluation composition**

- Locked holdout contains **at least 24 cases**
- Multi-label tagging is allowed
- Formal comparison uses **k = 3** independent runs per case, for every eligible
  candidate

**Percentage-gated critical slices** — five slices, each carrying an 80%
threshold:

- joins
- date filtering
- revenue calculations
- ambiguous requests
- unsupported requests

Each percentage-gated slice must contain **at least 4 cases**, and each must meet
its 80% threshold.

**Mandatory adversarial and safety coverage** — **not** a percentage-gated slice:

- The locked holdout must include **at least 4 adversarial or safety-oriented
  cases**
- These cases are governed by the **non-compensatory requirement of exactly zero
  unsafe executions**, not by a percentage threshold
- Unsafe SQL *generation*, correctly *blocked* prohibited SQL, and unsafe
  *execution* are reported separately
- **No additional 80% safety-slice threshold exists.** Do not invent one.

A prohibited query that is generated and blocked is a **model-quality failure**
and a **safety-control success**. A **single prohibited execution fails endpoint
eligibility**, regardless of any other result.

Adversarial cases remain part of overall per-run task-success reporting.

**Non-compensatory safety gate**

- Unsafe executions: **exactly 0**

Unsafe SQL *generation* is reported separately from unsafe *execution*. A
prohibited query that is generated and blocked is a **model-quality failure** and
a **safety-control success**. A single prohibited execution fails eligibility
regardless of cost or any other accuracy result.

**Structured contract and availability** — measured separately, because a timeout
is not malformed output and a completed contract violation is not a transport
failure.

- Locally valid `ModelDecision` among completed provider responses: **100%**
- Provider completion after bounded transport retries: **at least 98%**

**End-to-end quality**

- Overall per-run task-success rate: **at least 85%**
- Answerable-case result correctness: **at least 85%**
- All-three-runs case-consistency rate: **at least 75%**

**Percentage-gated critical slices**, measured across runs — five slices only

- Joins: at least 80%
- Date filtering: at least 80%
- Revenue calculations: at least 80%
- Ambiguous requests classified `clarification_required`: at least 80%
- Unsupported requests classified `unsupported`: at least 80%

Adversarial and safety coverage is **not** in this list; it is governed by the
zero-unsafe-execution gate above.

Always report integer counts alongside percentages. **Do not apply a percentage
gate to a slice with fewer than four cases.**

**Latency**

- Completed provider-call p95 hard ceiling: **15 seconds**
- Target: 10 seconds or less

Report the sample count. Do not imply high statistical precision from a small
benchmark.

**Cost** — no fixed monetary threshold is approved. For every eligible candidate
report mean cost per request, mean cost per successful task, projected cost per
1,000 requests, total benchmark cost, and the pricing source with its snapshot
date. **Cost is considered only after all eligibility gates pass.**

**Stability reporting** — report per-run success, all-three-runs consistency, and
the majority-of-three rate. The majority rate is **diagnostic only**: it is not a
model-selection metric and is never implemented in the production application.

**Failed gate behavior** — thresholds may not be lowered after results are
reviewed. A changed prompt, metadata file, model configuration, or comparator
starts a new documented iteration. A new final held-out claim requires a **new
locked holdout**.

**On failure.** Thresholds are not lowered after reviewing results. A failing
candidate produces a recorded failure, and any change is a new documented
iteration with a new holdout before a new held-out claim. If neither candidate
passes, the better failing model is not called production-ready; it may serve as a
clearly labeled provisional demo model with the failed gates disclosed.

**Harness.** The evaluation reuses the same application service the CLI uses and
consumes the typed result or the same machine-readable serialization. It never
parses human-readable output and never reimplements the pipeline.

**Artifacts.** Each formal run produces an immutable dated machine-readable report
and a concise summary, recording provider and model identity, endpoint, date,
commit, artifact hashes, case counts and repetitions, thresholds, per-case and
per-category outcomes, observed failures, latency, usage, cost, the selection
decision, unmet gates, limitations, and anything not measured. Credentials and
environment dumps are excluded.

---

## D-011 — Observability

**Decision.** Newline-delimited JSON logging through the standard library to
stderr, default level `WARNING`, with no hosted observability platform, tracing
backend, or metrics service.

**Rationale.** The evaluation report already owns formal aggregate measurement.
Adding a second measurement system would duplicate it without improving the
submission.

**Approved specifics.** A stable event envelope with schema version, UTC
timestamp, level, event name, request identity, and component. Durations measured
monotonically and reported in a consistent unit. Arbitrary Python objects and
environment dictionaries are never serialized into events.

Exactly one canonical completion event per request reaching the application
service, for every terminal state, carrying the applicable request identity,
resolved date context, state and reason code, provider and exact model identity,
provider latency, token usage, validation and execution outcomes, timings, row
count, and truncation flag. Token fields remain null when the provider does not
report them, and usage is never estimated or fabricated. Severity follows outcome,
so the default level keeps successful demos quiet while surfacing real failures.

Stage events exist only at debug level. They are diagnostic, not a second state
machine, must not alter behavior, and a request still produces its canonical
completion event when an earlier stage fails.

**Privacy posture.** Raw user questions are not logged by default; character
counts and optional stable hashes are, along with an evaluation case identifier
when the request comes from the harness. Raw input logging requires an explicit
opt-in and never applies at the default level. The full prompt is never written to
structured logs at any level — only version and content hashes, size estimates,
and configuration identifiers — and the exact prompt remains reachable solely
through the user-invoked diagnostic flag. This prevents an ordinary log-level
change from unexpectedly persisting user questions, schema details, business
metadata, or provider-bound content. Generated SQL appears as a hash rather than
in full, since the SQL itself is already available through the response, the
machine-readable result, the evaluation report, and tests.

This is a synthetic-data exercise, but the architecture should not normalize
capturing arbitrary user text without an explicit policy. A real deployment would
require retention, access, and privacy decisions first.

**Correlation and failure handling.** One request identifier is generated at the
application boundary and passed explicitly through every stage, appears in the
machine-readable result, and may appear in the user-facing message for an internal
error. The formatter preserves one event per line; multiline tracebacks never
spill into stderr, and stack traces never appear in ordinary user output or
default logs. Credentials, authorization headers, environment dumps, and raw
request headers are never logged.

---

## D-012 — Repository structure and delivery

**Decision.** Consolidate into a single named application package under a `src`
layout, performed as one small reviewable change before feature implementation.

**Rationale.** The initial repository contained speculative empty subpackages
committed to a decomposition before any architecture decision existed. Structure
should follow the approved architecture, not precede it. A `src` layout prevents
accidental working-directory imports from masking packaging errors.

**Approved package name.** The single named application package is
**`src/bse_nlq/`**.

- `bse_nlq` is the one application package; no second top-level package is
  approved.
- The existing speculative placeholder packages (`src/agent/`, `src/database/`,
  `src/response/`, the placeholder `src/sql/`, `src/evals/`, and `tests/evals/`)
  will be removed during the isolated restructuring change.
- **No replacement empty scaffolding is to be created.**
- Package modules are created **only** when they contain real implementation or
  an immediately required contract.

**Approved structure.** One application package containing flat modules for the
command-line entry point, application service, configuration, shared contracts,
typed errors, date handling, prompt composition, database access, formatting,
observability, and the evaluation runner; plus focused subpackages for schema,
model, and SQL, each with a clear responsibility and several meaningful modules.
Generic containers such as `utils`, `core`, `services`, `managers`,
`repositories`, `abstractions`, or `providers` are not approved unless later
implementation evidence creates a real cohesive responsibility.

Shared typed boundaries are separated from exceptional control flow: a successful
result is a contract, not an error. Date interpretation has a dedicated module and
does not hide inside prompt construction or the CLI — the prompt consumes resolved
dates rather than owning date semantics. Observability has a dedicated module
rather than being scattered through handlers.

**Evaluation artifacts.** Development cases, locked holdout cases, and committed
formal reports live outside the test tree. Top-level evaluation data is not a test
directory and not application runtime data, and the ordinary test command never
discovers or invokes live model evaluation. The evaluation runner is importable
from the package and reuses the application service.

**Packaging.** The semantic metadata sidecar ships as package data and is loaded
through a packaging-safe resource mechanism rather than assuming the working
directory is the repository root, with an explicit path override for tests and
future datasets. Console scripts are declared for the application and the
evaluation runner. Project metadata, the lockfile, the interpreter pin, and a
credential-free environment example are added.

**Disposition of prior placeholders.** The speculative empty package directories
and the evaluation directory inside the test tree are removed, after confirming
they contain no unique non-placeholder work. Existing unit and integration test
directories are retained; adapter, CLI, and safety test directories are added when
they contain real tests. No replacement empty scaffolding is created.

The empty architecture-review placeholder is removed and not replaced by another
planning-status document. Diagrams are retained, with the primary system diagram
embedded directly in the README, which is the reviewer's primary entry point.
Repository audit counts are never presented as application test results.

### `PROJECT_STATUS.md` — retained (supersedes the earlier removal decision)

**Decision.** `PROJECT_STATUS.md` is **retained** as the repository's concise
implementation handoff and persistent context document for coding agents.

**Purpose.** It communicates the current implementation phase, verified
repository state, most recently completed work, immediate next actions, active
blockers, approved fallbacks, validation commands and outcomes, and work
explicitly not yet completed. It must remain concise and current.

**It must not duplicate:** architectural rationale from this document; reviewer
setup and usage instructions from `README.md`; workshop history from
`architecture-workshop.md`; AI-assistance disclosure from `AI_USAGE.md`.

**It must not contain:** stale test counts; speculative completion percentages;
unverified claims; planned behavior described as implemented; long historical
activity logs.

**Why this reverses the earlier decision.** The prior decision removed
`PROJECT_STATUS.md` on the grounds that it was a redundant *reviewer-facing*
status document whose content belonged in the README, the architecture summary,
test output, and the evaluation report. That reasoning misidentified its role. Its
actual role is **operational**: preserving implementation context and handoff
state for coding agents across sessions. That role is distinct from `README.md`
and the architecture documents, none of which carry session-to-session working
state. The original concern — that a second status document goes stale and
creates claims a reviewer must reconcile — is addressed by the content
constraints above rather than by deletion.

`PROJECT_STATUS.md` is **not** architecture authority. It never overrides
approved decisions recorded in this document.

**Ignore policy.** Generated database files remain ignored and dead commentary is
removed. Committed formal evaluation reports are not ignored. Credentials,
environment files, unsanitized environment dumps, local caches, and temporary
databases are never committed.

**Constraint.** The restructuring change must not mix in substantial query
behavior. Afterward, package import succeeds, console-script help succeeds once
entry points exist, test discovery remains offline, and the working tree contains
no unexplained empty placeholder structure.

---

## Implementation-owned constants and freeze points

The following values are **implementation configuration with explicit freeze
points**, not unresolved architecture principles. Each mechanism is already
approved; only the concrete value remains, and none may be invented arbitrarily.

**Fetch cap.** The mechanism is approved. The numeric N is an implementation
configuration value, chosen during executor and CLI implementation. Test N, N+1,
zero rows, and truncation behavior. **Freeze before development evaluation.**

**Progress-handler budget.** The mechanism is approved. The budget must be
*measured* against the deterministic seeded database, not guessed. Choose an
initial conservative value during database implementation, and test both ordinary
queries and intentionally expensive ones. **Freeze before the locked holdout.**

**Default `as_of`.** An explicit configured default is required; no machine-clock
fallback is allowed. Select the concrete default once the deterministic dataset
timeline is finalized. **Freeze before prompt and date evaluation cases are
written.**

**Function allowlist.** The fail-closed policy is approved. Exact SQLGlot
expression forms and SQLite function entries are finalized after the
parser/authorizer spike. The list must be explicit and test-covered **before any
model-generated SQL is executed.**

**Reason codes.** One canonical enum is required, and it must include the
already-approved `result_unit_mismatch`. The full enum is finalized alongside the
contracts and validator implementation. **No duplicate free-form reason strings
may be created across modules.** Freeze before CLI and evaluation integration.

**JSON response schema.** The exact serialized v1 envelope remains implementation
pending. The `generated_sql` and `executed_sql` semantics recorded in D-006 are
already authoritative. Serialization must be frozen **before the evaluation
harness consumes it**, and the harness must never parse human-readable output.

---

## Corrections

Corrections that changed the substance of a specific decision are recorded inside
that decision's entry above — the column-validation approach in D-006, the
rejection-state naming in D-007, and the test-double type boundary in D-009.

The full cross-cutting correction record, including corrections that changed
framing rather than a single decision, is kept in
[`architecture-workshop.md`](architecture-workshop.md). It is not duplicated here.
