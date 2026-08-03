# System Context

> Approved design. The end-to-end CLI product path is implemented.

```mermaid
flowchart TB
    user["Non-technical user<br/>asks a plain-English question"]
    reviewer["Reviewer<br/>clones, installs, runs"]

    subgraph app["BSE NLQ Agent - project boundary"]
        cli["CLI<br/>human output and SQL transparency"]
        service["QueryService<br/>orchestration and terminal states"]
        core["Deterministic core<br/>dates, schema context, SQL policy,<br/>authorizer, unit lineage, formatting"]
        db[("SQLite<br/>read-only, generated from seed")]
        harness["Evaluation harness<br/>reuses QueryService"]
    end

    provider["Model provider endpoint<br/>OpenAI-compatible<br/>output is untrusted"]
    logs["stderr<br/>JSON Lines logs"]
    reports["Committed evaluation reports"]

    user --> cli
    reviewer --> cli
    reviewer --> reports
    cli --> service
    service --> core
    service -->|"one semantic generation attempt"| provider
    provider -.->|"untrusted ModelDecision"| service
    core --> db
    db -.->|"raw values"| core
    service --> logs
    harness --> service
    harness --> reports

    classDef external fill:#f4f4f4,stroke:#888888,stroke-dasharray: 4 3
    classDef owned fill:#eef4fb,stroke:#33628f
    class user,reviewer,provider,logs external
    class cli,service,core,db,harness owned
```

| Source | Trust |
|---|---|
| User question | Untrusted, delimited data |
| Model response | Untrusted; schema enforcement covers shape only |
| Introspected database schema | Trusted structural source |
| Version-controlled semantic metadata | Trusted business source |
| Application code | Trusted |

The model provider is the only network dependency. The database is generated locally, tests never contact a provider, logs use stderr, and evaluation artifacts are committed only after they exist.
