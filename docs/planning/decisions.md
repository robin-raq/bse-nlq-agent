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

## Frozen contracts

### Model decision

Every provider response maps to four required fields: `status`, `sql`, `clarification`, and `explanation`; no additional fields are allowed. Local validation enforces status-specific invariants.

### SQL and execution

- Exactly one approved read-only SQLite statement.
- Whole-tree rejection of mutation, DDL, administrative, recursive, or clock-dependent constructs.
- Physical tables checked against introspection; CTE and derived names handled separately.
- No SQL rewriting: executed SQL equals generated SQL byte for byte.
- Read-only URI, `query_only`, default-deny authorizer, progress budget, and fetch cap.
- Unit/alias contradictions rejected before execution; unknown units remain unformatted.

### Evaluation gate

The holdout contains at least 24 cases and runs each candidate three times. Join, date, revenue, ambiguity, and unsupported slices each contain at least four cases and require 80% success. Safety requires zero unsafe executions; any unsafe execution disqualifies the candidate. Candidate selection considers cost only after quality and safety gates pass.

Thresholds, cases, prompt, metadata, schema, provider configuration, and pricing source are frozen before formal results are reviewed.

### Logging privacy

Default logs exclude raw questions, prompts, generated SQL, results, model output, credentials, and headers. Debug diagnostics require explicit opt-in and still redact secrets.

## Implementation freeze points

The fetch cap and progress budget are measured against the seeded database and frozen before development evaluation. The function allowlist is derived from required reference queries and frozen before prompt iteration. Retry counts are configured and tested before evaluation.

## Deferred

PostgreSQL, GUI, repair attempts, multi-turn memory, generalized provider abstraction, sample-row prompting, and full alias/scope resolution are outside the submitted MVP unless measurement justifies them.
