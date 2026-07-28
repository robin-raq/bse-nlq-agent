# Evaluation Flow Diagram

Status: Approved target design. Implementation pending; no evaluation has run and
no results exist.

How model quality will be measured, and how the process avoids grading itself.

Deterministic tests and model evaluation are separate. Tests measure the
application and run entirely offline. Evaluation measures the deployed model
system and requires credentials.

## Two case sets

```mermaid
flowchart TD
    subgraph dev["Development phase - iteration allowed"]
        d1["Development cases"] --> d2["Zero-shot baseline"]
        d2 --> d3["Diagnose recurring failure classes"]
        d3 --> d4["Refine prompt, metadata,<br/>business definitions"]
        d4 --> d5{"Do examples materially<br/>improve a measured<br/>failure mode?"}
        d5 -->|"yes"| d6["Add small few-shot set<br/>each traced to an observed failure<br/>disjoint from both manifests"]
        d5 -->|"no"| d7["Remain zero-shot"]
        d6 --> d2
    end

    d7 --> freeze
    d6 --> freeze

    freeze["FREEZE<br/>prompt, metadata, schema, database,<br/>code commit, case manifests, comparator,<br/>thresholds, endpoint configurations"]

    freeze --> gate["Quality gate written down<br/>BEFORE any results are viewed"]
    gate --> holdout["Locked holdout run"]

    holdout --> report["Immutable dated report<br/>machine-readable + summary"]

    classDef iter fill:#eef4fb,stroke:#33628f
    classDef lock fill:#fdf0e3,stroke:#b3701a
    class d1,d2,d3,d4,d5,d6,d7 iter
    class freeze,gate,holdout lock
```

**The holdout is used only after everything is frozen.** Using holdout failures
to tune the prompt and then continuing to describe those cases as unseen is not
permitted. If the holdout forces a change, the honest outcomes are a **failed
final evaluation** followed by a new holdout, or a result **clearly labeled as a
reused validation set** rather than held-out performance.

## Scoring a single case

```mermaid
flowchart TD
    case["Holdout case"] --> run["Run through the real QueryService<br/>repeated k times"]
    run --> state{"Terminal state matches<br/>the expected state?"}

    state -->|"no"| fail["Case run fails"]
    state -->|"yes, non-SQL state"| passns["Pass<br/>clarification, unsupported,<br/>adversarial"]
    state -->|"yes, answerable"| oracle["Execute hand-reviewed reference SQL<br/>against the same frozen database"]

    oracle --> cmp["Compare normalized results"]
    cmp --> rules["Multiset semantics by default<br/>ordered where ordering is the answer<br/>tie-aware invariants for rankings<br/>exact integer cents, no float tolerance"]
    rules -->|"equivalent"| pass["Case run passes"]
    rules -->|"differs"| fail

    classDef good fill:#e8f5ec,stroke:#2f7d4f
    classDef bad fill:#fbeaea,stroke:#a33
    class pass,passns good
    class fail bad
```

Exact SQL-string matching is rejected as the primary oracle: semantically
equivalent queries differ in aliases, join order, subquery structure, CTE usage,
aggregate construction, and predicate ordering. **Multiset comparison is the
default** because duplicates are meaningful in SQL and must not vanish because a
comparator used a set.

Adversarial cases need no reference SQL. They pass on the absence of prohibited
execution, an acceptable terminal state, correct presence or absence of executed
SQL, and the appropriate rejection reason.

## Candidate eligibility and selection

```mermaid
flowchart TD
    a["GPT-5 mini via OpenAI API<br/>required MVP path"] --> gateA{"Passes precommitted<br/>quality gate?"}
    b["gpt-oss-120b via Groq<br/>intended comparison candidate"] --> elig{"Endpoint verifies<br/>strict schema enforcement,<br/>model access, flattened<br/>ModelDecision support?"}

    elig -->|"no"| blocked["TERMINAL: comparison recorded as BLOCKED<br/>candidate excluded from the like-for-like pool<br/>GPT-5 mini proceeds provisionally<br/>MVP is not delayed or weakened"]
    elig -->|"yes"| gateB{"Passes precommitted<br/>quality gate?"}

    gateA -->|"no"| failA["Recorded failure"]
    gateB -->|"no"| failB["Recorded failure"]

    gateA -->|"yes"| pool["Eligible set<br/>like-for-like comparison pool"]
    gateB -->|"yes"| pool

    pool --> pick["Select the least expensive<br/>eligible model"]

    failA --> none{"Did any candidate<br/>pass the gate?"}
    failB --> none
    none -->|"yes"| pick
    none -->|"no"| prov["No production-ready claim.<br/>Provisional demo model only,<br/>clearly labeled, failed gates disclosed"]

    classDef bad fill:#fbeaea,stroke:#a33
    classDef warn fill:#fdf0e3,stroke:#b3701a
    class failA,failB,prov bad
    class blocked warn
```

**A candidate that fails eligibility never rejoins the eligible pool.** The
blocked branch is terminal: the open-weight candidate is excluded from the
like-for-like comparison, the exclusion is recorded with its reason, and GPT-5
mini proceeds as the clearly labeled provisional model.

**Safety is non-compensatory.** Zero unsafe executions is a gate, not a weighted
term — no cost or accuracy advantage offsets a single unsafe execution. Unsafe
SQL *generation* is reported separately from unsafe *execution*, because a
prohibited query the application correctly blocks is a model-quality failure and
a safety-control success at the same time.

**Thresholds are never lowered after results are seen.** A failing candidate
produces a recorded failure; any subsequent change is a new documented iteration
against a new holdout.

## What is reported

Pipeline-stage metrics rather than one accuracy number, so a schema failure,
incorrect SQL, a validator rejection, and an execution failure remain
distinguishable:

- Provider completion rate and structured-output compliance, measured separately —
  a timeout is not malformed output
- Valid decision rate, state-classification accuracy
- SQL parse success, query-policy acceptance, execution success
- Result correctness and end-to-end task success
- Unsafe generation count and unsafe execution count
- Latency percentiles with the denominator stated
- Token usage and cost, with the pricing source and snapshot date

Each case runs multiple times. **Per-run success** and **all-runs consistency**
are primary. **Majority-of-runs is diagnostic only** — it is never a selection
metric and is not implemented in the application, because production makes one
semantic generation attempt per request and a majority score would overstate what
users actually receive.

Naturally occurring provider and execution failures are counted and never removed
from the denominator.
