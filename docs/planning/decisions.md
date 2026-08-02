# Architecture Decisions

> Approved pre-implementation decisions. `ARCHITECTURE.md` is the consolidated technical contract.

| ID | Decision | Rationale / tradeoff |
|---|---|---|
| D-001 | Deterministically seeded synthetic BSE ticketing dataset | Supports the exercise’s likely event, category, attendance, and revenue questions. Results are self-authored and therefore reported with limited external validity. |
| D-002 | Python 3.13 managed by `uv`, with committed lockfile | Reproducible, low-friction reviewer setup. |
| D-003 | Locally generated SQLite database | Zero-server setup and useful runtime controls. Gives up role-level permissions and native date/decimal types. |
| D-004 | Direct SDK behind `QueryGenerator`; one generation attempt | The workflow is fixed and does not justify an agent framework or repair loop. OpenAI Responses is the MVP transport; Groq Chat Completions is the comparison transport. |
| D-005 | Introspected schema plus curated semantic metadata | Separates structural truth from business meaning and avoids duplicate schema declarations. No raw sample rows by default. |
| D-006 | Parsed-AST policy plus independent SQLite controls | Model SQL is untrusted. Static checks and runtime enforcement cover different failure modes. |
| D-007 | Explicit typed terminal states | Prevents rejected SQL from being presented as executed and distinguishes empty success from failure. |
| D-008 | CLI only | Satisfies the exercise with minimal presentation code; all modes use the same service. |
| D-009 | Offline deterministic automated tests | Eliminates credentials, cost, network failures, and model nondeterminism from application tests. |
| D-010 | Development set plus locked holdout; result-equivalence scoring | Allows prompt iteration without tuning on final cases and accepts semantically equivalent SQL. |
| D-011 | Standard-library JSONL logging to stderr | Preserves clean JSON stdout without adding a hosted observability stack. |
| D-012 | One `src/bse_nlq/` package | Avoids speculative packages and working-directory import mistakes. |
| D-013 | Six-table schema: `venues`, `events`, `ticket_tiers`, `orders`, `order_items`, `refunds` | Normalizes list price to the tier so pricing questions have a source of truth, and keeps category a CHECK domain rather than a lookup table. The `order_items → ticket_tiers → events` hop is retained deliberately: it gives the join evaluation slice real depth. |
| D-014 | Revenue uses actual paid price; fees are not modeled | `unit_price_cents` is the only price input; `face_value_cents` is descriptive list price. One revenue definition, no fee-inclusion ambiguity. |
| D-015 | Deterministic 109-row seed with published reconciliation totals | Small enough to audit by hand, since every evaluation number inherits the seed's correctness. |

## Frozen contracts

### Model decision

Every provider response maps to four required fields: `status`, `sql`, `clarification`, and `explanation`; no additional fields are allowed. Local validation enforces status-specific invariants.

### SQL and execution

- Exactly one approved read-only SQLite statement.
- Whole-tree rejection of mutation, DDL, administrative, recursive, or clock-dependent constructs.
- Physical tables checked against introspection; CTE and derived names handled separately.
- No SQL rewriting: executed SQL equals generated SQL byte for byte.
- Read-only URI, `query_only`, default-deny authorizer, progress budget, and fetch cap.
- Authorizer actions use an explicit action-code mapping, never a reverse lookup over `sqlite3` constants. Numeric values repeat across namespaces: action code 19 is `SQLITE_PRAGMA`, while the unrelated result code `SQLITE_CONSTRAINT` is also 19.
- Unit/alias contradictions rejected before execution; unknown units remain unformatted.

#### Locked U2 Slice 3 authorization rules

- Physical-source classification uses only `scope.sources`: an `exp.Table`
  value is a physical-table candidate, while a nested `Scope` is a CTE or
  derived source. Neither `scope.tables` nor raw `find_all(exp.Table)` is an
  authorization authority.
- SQLGlot `qualify()` is supporting analysis only. Application code remains
  authoritative for table allowlists, prompt exclusions, qualifiers,
  ambiguity, column visibility, and functions.
- Unqualified columns resolve local-ambiguity-first: inspect local sources,
  reject more than one local match, bind exactly one local match, and consult
  the next outer scope only after zero local matches. Apply the same ambiguity
  rule independently at every outer level.
- `COUNT(*)` is allowed; bare projection `*` and qualified `alias.*` are
  rejected. Detect bare projection stars through the projection AST rather
  than `scope.stars` alone, and never expand stars by executing against SQLite.
- Identifier comparisons follow SQLite-compatible case-insensitive behavior,
  including quoted identifiers. Canonical output names come from application
  inventories; identifier normalization operates on a copy only.
- Validation never rewrites the execution payload: `original_sql` remains the
  later byte-for-byte payload and `normalized_sql` remains evidence only.
  Casing or qualifier normalization must not replace `original_sql`.

#### Locked U2 Slice 4B qualified-column rules

- A qualified column resolves against the nearest lexical scope whose
  `scope.sources` key matches the qualifier under the existing ASCII-only fold.
  Finding the qualifier stops the search even when its requested column is
  unknown or excluded; a more distant source is never a fallback.
- A source alias replaces its physical table name as a qualifier. An unknown
  qualifier is `unknown_column_qualifier`; a known source with no matching
  output is `unknown_column`; a physical column outside the prompt-visible
  inventory is `excluded_column`.
- Qualified correlated lookup may cross subquery/Union parents. It does not
  make CTE or derived-table bodies lateral. Physical bindings contribute
  inventory-canonical `(table, column)` pairs to `referenced_columns`; internal
  CTE/derived outputs validate by their output schema and add no synthetic pair.
- Only `COUNT(*)` may contain a star. Authored bare or qualified projection
  stars are `projection_star`; SQLGlot's pinned synthetic `VALUES` wrapper is
  not treated as authored SQL.
- Unqualified local/outer binding, projection aliases, and mixed closure remain
  Slice 4C work.

#### Locked U2 Slice 4C unqualified-column rules

- An unqualified column binds only against sources local to its own scope
  (`scope.sources`), never an outer scope, regardless of candidate count.
  More than one local candidate is `ambiguous_column`; exactly one candidate
  binds through the same physical/internal authorization the qualified path
  uses (so `unknown_column` / `excluded_column` reasons stay consistent);
  zero local candidates is `unknown_column`.
- An unqualified name that appears inside ORDER BY and matches the
  immediately enclosing SELECT's own projection alias resolves to that alias
  — mirroring SQLite's own result-column-alias precedence — and contributes
  no physical identity of its own. This is the only projection-alias context
  implemented: WHERE, JOIN ON, GROUP BY, and HAVING never see alias binding.
  Generalized outer-scope unqualified correlation is explicitly out of scope
  for this take-home; qualified correlation (Slice 4B) is sufficient for the
  planned product.

#### Locked U2 Slice 4D function/machine-clock rules

- Authorization is by SQLGlot expression *type*, not by parsed function-name
  string: only `exp.Sum`, `exp.Count`, and `exp.Coalesce` are permitted.
  Every other `exp.Func` node is `forbidden_function`. This is a fixed
  allowlist sized to the 14 anchors (`SUM`, `COALESCE`) plus `COUNT` (already
  assumed legitimate by the Slice 4B `COUNT(*)`-only star policy) — not a
  general SQL function surface.
- `AVG` is deliberately excluded even though a PRD example question uses the
  word "average": the frozen `average_ticket_price` metric forbids naive
  `AVG(unit_price_cents)` in favor of the quantity-weighted `SUM(...) /
  SUM(...)` form the anchors already use, so no correctly-implemented query
  needs it.
- Every machine-clock form is rejected by the same default-deny path, not by
  inspecting arguments: `CURRENT_DATE`/`CURRENT_TIME`/`CURRENT_TIMESTAMP` and
  every `date`/`datetime`/`julianday`/`strftime`/`unixepoch(...)` call are
  simply not in the allowlist. No date-expression grammar or `'now'` /
  `'localtime'` / `'utc'` argument parser was built.
- `exp.Binary` and `exp.Exists` are excluded from the function walk as
  non-function syntax, not as allowlisted functions: in the pinned SQLGlot
  30.14.0 release, `exp.And`/`exp.Or` multiply-inherit from both `exp.Binary`
  and `exp.Func`, and `exp.Exists` (the Slice 4B correlated-subquery
  predicate) is also `exp.Func`-derived. Nested function calls inside either
  are still checked independently — only the connective/predicate node itself
  is exempt.

#### Prompt policy v2 SQL compatibility rules

- The provider neutral application prompt names the complete SQL function
  allowlist: `SUM`, `COUNT`, and `COALESCE`. It explicitly excludes `AVG`,
  `ROUND`, and `NULLIF` so one shot generation sees the same boundary enforced
  by static validation and the SQLite authorizer.
- Quantity weighted average ticket price uses exact nonnegative integer round
  half up arithmetic, with a `CASE` zero quantity guard and `(2 * SUM(gross) +
  SUM(quantity)) / (2 * SUM(quantity))`. Floating point literals are forbidden
  for this calculation.
- This is a prompt policy change, not a SQL policy expansion or provider
  specific instruction. It advances `APPLICATION_POLICY_VERSION` to `2` and
  changes the frozen prompt SHA-256 to
  `214bbf9f0260a5a33da06251c0dd0cbde2435d8d1f86d411363d7a35b90bc1e7`.
  Prior comparison artifacts remain immutable. A future comparison must rerun
  both providers rather than reuse the version 1 OpenAI baseline.

#### Locked U3 authorizer/execution rules

- The SQLite authorizer allowlists exactly three action codes:
  `SQLITE_SELECT` unconditionally, `SQLITE_READ` only for the executing
  query's own `referenced_tables`/`referenced_columns`, and
  `SQLITE_FUNCTION` only for the same fixed function allowlist the static
  policy enforces. Every other action code — including ones not yet defined
  by SQLite — is denied by one catch-all branch, not an enumerated deny list.
- `sqlite3` gives no single reliable signal for "this failure was an
  authorizer denial": statement-level and read denials raise with
  `sqlite_errorcode == SQLITE_AUTH` but inconsistent message text; function
  denial raises with the "not authorized" wording but `sqlite_errorcode ==
  SQLITE_ERROR`. Classification checks both signals.
- Row/column limits reject on overflow (the `(N+1)`th row) rather than
  truncating; the opcode budget is calibrated well above real anchor cost
  (~1-2k opcodes) while still bounding runaway execution.

### Schema and dataset

Full contract in [`schema-design.md`](schema-design.md).

- STRICT tables; integer cents; foreign keys enforced and asserted.
- Event status: `scheduled`, `completed`, `cancelled`. Order status: exactly
  `completed` and `cancelled` — `pending` and `failed` add no required analytics
  capability and would add schema, metadata, seed, and query complexity.
- Gross revenue sums `unit_price_cents * quantity` over completed orders; net
  subtracts refunds **pre-aggregated per line item**, since a flat refund join
  multiplies gross by the refund count.
- `tickets_sold` and `tickets_net` are distinct named metrics.
- Cancelled orders are excluded from all metrics; cancelled events remain in
  gross and are zeroed in net by their refunds.
- Attendance is nullable on `events`, present only for completed events, bounded
  by event capacity. It is a turnstile fact, not derived from ticket sales.
- Timestamps are America/New_York business-local wall-clock, `YYYY-MM-DDTHH:MM:SS`,
  no offset. Default `as_of` is 2026-03-15. `upcoming` is
  `event_date >= as_of AND status = 'scheduled'`: `as_of` carries no time of day,
  so a strict comparison would drop a same-day event that has not happened.
- Date CHECKs use `IS strftime(...)`, never `=`. With `=`, `strftime` returns
  NULL on malformed input and SQLite treats the NULL result as passing, silently
  accepting invalid dates.
- Division units are closed: cents/count → `cents_per_item`; count/count →
  dimensionless; dimensionless × scale stays dimensionless; a proven
  dimensionless value with a `_bp` alias may display as basis points; anything
  else is unknown and returned raw. Rounding is integer-only `(2a + b) / (2b)` to
  keep results exactly comparable in cents.
- Four question shapes are ambiguous by contract and must reach
  `clarification_required`; no default may be chosen silently:
  **bare revenue** (gross vs net after refunds), **"best event"** (metric, plus a
  period when none is given), **"how are sales doing"** (metric, period, and
  baseline when a trend judgment is requested), and **"sold out"**
  (`tickets_sold >= capacity` ever vs `tickets_net >= capacity` currently). The
  seed makes the sold-out readings disagree so a silent choice is detectable.
- `as_of` is a date and carries no time of day, so questions depending on the
  current moment within that day — "has tonight's show started?", "what is
  happening right now?" — are `unsupported_question`. No midnight or
  end-of-day convention is invented, since any such convention would return a
  confident wrong answer instead of an honest refusal.
- The two refund measures are independent: `refunded_qty` governs `tickets_net`
  and `refund_amount_cents` governs net revenue. Neither is derived from the
  other and no proportionality constraint connects them — a returned
  complimentary ticket has positive quantity and zero amount. Their aggregate
  upper bounds are enforced by I-1 and I-2, in addition to the ordinary row-level
  DDL constraints on each refund record. There is no proportional-refund
  invariant.
- Metadata must state that `venues.capacity` is the physical maximum while
  `events.capacity` is the released capacity used for sold-out calculations, and
  that `tier_name` is unique only within an event, so grouping by it across
  events combines distinct offerings.
- Cross-table invariants are enforced in seed logic and tests, not triggers: the
  database is written once and read-only thereafter, so a trigger could only fire
  where seed logic already runs. `tickets_sold <= events.capacity` is asserted as
  `<=`; the seed includes an event exactly at capacity.
- I-6 is stated as two equalities over completed-order lines of a cancelled
  event: refunded quantity equals the line's quantity **and** refunded amount
  equals its gross. Both are needed because the measures are independent, and the
  pair holds for complimentary lines where a full refund of zero money is
  correct. Cancelled-order lines are excluded, having never contributed to gross.
- Exact seed literals — identifiers, event names, order references, purchase
  timestamps, and order-to-line packing — are frozen in
  [`seed-manifest.md`](seed-manifest.md), separate from the design contract so
  the seed module has one unambiguous source.
- Semantic metadata is JSON, parsed with the standard library, and must not
  restate types, primary keys, or foreign keys.

### Evaluation gate

The holdout contains at least 24 cases and runs each candidate three times. Join, date, revenue, ambiguity, and unsupported slices each contain at least four cases and require 80% success. Safety requires zero unsafe executions; any unsafe execution disqualifies the candidate. Candidate selection considers cost only after quality and safety gates pass.

Thresholds, cases, prompt, metadata, schema, provider configuration, and pricing source are frozen before formal results are reviewed.

### Logging privacy

Default logs exclude raw questions, prompts, generated SQL, results, model output, credentials, and headers. Debug diagnostics require explicit opt-in and still redact secrets.

## Implementation freeze points

The fetch cap and progress budget are measured against the seeded database and frozen before development evaluation. The function allowlist is derived from required reference queries and frozen before prompt iteration. Retry counts are configured and tested before evaluation.

## Deferred

PostgreSQL, GUI, repair attempts, multi-turn memory, generalized provider abstraction, sample-row prompting, and full alias/scope resolution are outside the submitted MVP unless measurement justifies them.
