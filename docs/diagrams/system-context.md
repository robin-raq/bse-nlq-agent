# System Context Diagram

Status: Approved target design. Implementation pending; diagrams describe
intended structure, not verified structure.

External actors, the application boundary, and the systems the agent will depend
on.

```mermaid
flowchart TB
    user["Non-technical user<br/>asks a plain-English question"]
    reviewer["Reviewer<br/>clones, installs, runs"]

    subgraph app["BSE NLQ Agent - project boundary"]
        cli["CLI<br/>human output and JSON contract"]
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

## Trust boundary

| Source | Trust |
|---|---|
| User question | Untrusted — inserted as delimited data, never as instructions |
| Model response | Untrusted — the provider schema enforces shape, not truth |
| Introspected schema | Trusted — read from the initialized database |
| Semantic metadata | Trusted — curated and version-controlled |
| Application code | Trusted |

The model provider sits outside the boundary in both directions. The application
sends it one semantic generation attempt per request, and treats everything
returned as input requiring validation.

## Dependency notes

- The database will be generated locally from a deterministic seed script
  committed with the implementation. The database itself is never downloaded and
  never committed.
- The provider endpoint is the only network dependency, and the approved test
  plan requires that no automated test contact it.
- Logs go to stderr so the machine-readable result on stdout stays
  uncontaminated.
- Evaluation reports will be committed artifacts, written by the harness and read
  by reviewers. None exist yet.
