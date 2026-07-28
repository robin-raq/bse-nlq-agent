# Request Flow Diagram

Status: Approved target design. Implementation pending; diagrams describe
intended behavior, not verified behavior.

The end-to-end path for a single question, and where each terminal state is
reached.

## Pipeline

Note the ordering: **projection unit inference runs before execution**, because a
unit is a property of the query's projection expressions, not of the values that
come back.

```mermaid
flowchart TD
    q["User question"] --> dates["Deterministic date resolution<br/>configured as-of, half-open boundaries"]
    dates --> prompt["Prompt assembly<br/>cached schema context + delimited question"]
    prompt --> gen["One semantic model-generation attempt<br/>bounded transport retries only"]

    gen -->|"transport failure after retries"| S_prov["provider_unavailable"]
    gen --> shape["Provider schema enforcement"]
    shape --> inv["Local ModelDecision invariants<br/>cross-field state checks"]

    inv -->|"malformed or contradictory"| S_bad["invalid_model_output"]
    inv -->|"clarification_required"| S_clar["clarification_required"]
    inv -->|"unsupported"| S_unsup["unsupported"]
    inv -->|"sql_generated"| parse["SQLGlot parse"]

    parse -->|"unparseable"| S_invalid["invalid_sql"]
    parse --> policy["Static AST policy<br/>single statement, read-only family,<br/>forbidden-node walk, physical tables,<br/>function policy, no clock constructs"]

    policy -->|"violation"| S_rej["query_rejected<br/>with reason code"]
    policy --> units["Projection unit inference<br/>and alias-consistency validation"]

    units -->|"proven contradiction"| S_rej
    units --> exec["SQLite execution<br/>read-only URI, query_only,<br/>default-deny authorizer,<br/>instruction budget, fetch cap"]

    exec -->|"budget exceeded"| S_limit["execution_limit_exceeded"]
    exec -->|"SQLite error"| S_execerr["execution_error"]
    exec --> raw["Raw execution result<br/>values preserved unchanged"]

    raw --> fmt["Deterministic formatting<br/>currency only where unit is proven"]
    fmt -->|"no rows"| S_empty["answered_empty"]
    fmt -->|"cap exceeded"| S_trunc["result_truncated"]
    fmt --> S_ok["answered"]

    S_int["internal_error<br/>controlled catch-all for any<br/>unexpected application failure<br/>at any stage above"]

    classDef ok fill:#e8f5ec,stroke:#2f7d4f
    classDef blocked fill:#fdf0e3,stroke:#b3701a
    classDef failed fill:#fbeaea,stroke:#a33
    class S_ok,S_empty,S_trunc,S_clar,S_unsup ok
    class S_rej blocked
    class S_bad,S_invalid,S_limit,S_execerr,S_prov,S_int failed
```

## Terminal states

| State | Category | SQL shown | Label |
|---|---|---|---|
| `answered` | Success | Yes | Executed SQL |
| `answered_empty` | Success | Yes | Executed SQL |
| `result_truncated` | Success | Yes | Executed SQL |
| `clarification_required` | Handled semantic | None exists | — |
| `unsupported` | Handled semantic | None exists | — |
| `query_rejected` | Blocked before execution | Yes | Generated SQL — not executed |
| `invalid_sql` | Model output failure | Yes | Generated SQL — not executed |
| `invalid_model_output` | Model output failure | None exists | — |
| `execution_limit_exceeded` | Stopped by policy | Yes | Executed SQL |
| `execution_error` | Database failure | Yes | Executed SQL |
| `provider_unavailable` | Infrastructure failure | None exists | — |
| `internal_error` | Application failure | Depends | — |

An **empty result is a success**, not an error. A rejection is never described as
having been run.

## Where the pipeline deliberately stops

**Safety rejection stops** because deterministic safety policy has final
authority. Asking the model to regenerate after a rejection would create a loop
that repeatedly searches for output which passes or bypasses the validator.

**Execution failure stops** for an entirely different reason — scope. Automatic
repair would add a second model call, latency, cost, more state transitions, more
failure modes, and new evaluation requirements. It is deferred as a separately
designed and evaluated extension.

Both produce the same shape of outcome; only one of them is a security decision.

## Independent execution controls

```mermaid
flowchart TD
    sql["Model-generated SQL<br/>untrusted"]

    subgraph static["STATIC PRE-EXECUTION POLICY - no database contact"]
        direction TB
        p1["SQLGlot parse"]
        p2["Exactly one non-empty statement"]
        p3["Approved read-only query family"]
        p4["Forbidden-node walk, whole tree"]
        p5["Physical-table policy<br/>CTE and derived names excluded"]
        p6["Function policy, fail closed"]
        p7["Unit / alias contradiction validation"]
        p1 --> p2 --> p3 --> p4 --> p5 --> p6 --> p7
    end

    subgraph runtime["CONNECTION AND RUNTIME ENFORCEMENT - SQLite"]
        direction TB
        r1["Read-only connection URI"]
        r2["PRAGMA query_only"]
        r3["Default-deny authorizer<br/>explicit denial during prepare"]
        r4["Progress instruction budget<br/>bounds computation"]
        r5["Fetch cap<br/>bounds materialization"]
        r1 --> r2 --> r3 --> r4 --> r5
    end

    sql --> static
    static -->|"rejected"| rej["query_rejected<br/>never reaches the database"]
    static -->|"approved"| runtime
    runtime --> out["Raw result"]

    classDef bad fill:#fbeaea,stroke:#a33
    class rej bad
```

**Nothing in the static block touches the database.** A query rejected there is
never submitted to SQLite at all. The runtime block engages only once static
policy has approved the statement.

The **six independent safety layers** are: the static AST policy as a whole
(one layer, with the checks listed above), plus the read-only connection URI,
`PRAGMA query_only`, the default-deny authorizer, the progress instruction
budget, and the fetch cap.

These layers matter because they **fail for different reasons**. A construct
SQLGlot parses differently from SQLite still meets the authorizer, which runs
inside SQLite on the real execution plan rather than on our parse tree. A
misconfigured authorizer still meets the read-only connection. No single mistake
opens a write path.

The fetch cap bounds returned materialization; the progress budget bounds
computation. Neither replaces the other.

The approved test plan requires each layer to be tested with the others
deliberately bypassed, so that a passing test would identify which control
actually held.
