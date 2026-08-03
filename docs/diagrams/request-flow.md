# Request Flow

> Approved design. The end-to-end request pipeline is implemented.

Currency formatting is applied after execution from the `_cents` column-name
convention, not from projection-unit inference.

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
    policy --> exec["SQLite execution<br/>read-only URI, query_only,<br/>default-deny authorizer,<br/>instruction budget, fetch cap"]

    exec -->|"budget exceeded"| S_limit["execution_limit_exceeded"]
    exec -->|"SQLite error"| S_execerr["execution_error"]
    exec -->|"row/column overflow"| S_limit
    exec --> raw["Raw execution result<br/>values preserved unchanged"]

    raw --> fmt["Deterministic formatting<br/>currency when column ends in _cents"]
    fmt -->|"no rows"| S_empty["answered_empty"]
    fmt --> S_ok["answered"]

    S_int["internal_error<br/>controlled catch-all for any<br/>unexpected application failure<br/>at any stage above"]

    classDef ok fill:#e8f5ec,stroke:#2f7d4f
    classDef blocked fill:#fdf0e3,stroke:#b3701a
    classDef failed fill:#fbeaea,stroke:#a33
    class S_ok,S_empty,S_clar,S_unsup ok
    class S_rej blocked
    class S_bad,S_invalid,S_limit,S_execerr,S_prov,S_int failed
```

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
        p1 --> p2 --> p3 --> p4 --> p5 --> p6
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

Safety rejection and execution failure both stop the request. Rejection is authoritative policy; automatic execution repair is a deferred feature with separate cost, state, and evaluation requirements.
