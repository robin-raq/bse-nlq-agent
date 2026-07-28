# Architecture Workshop

Status: Complete — 2026-07-27 / 2026-07-28. Implementation pending; nothing
described here has been built or verified.

This document is the primary record of cross-cutting corrections made during the
workshop. `decisions.md` records decision-by-decision rationale; `AI_USAGE.md`
summarizes AI assistance and links here for correction detail.

A curated summary of the architecture workshop that preceded implementation:
what was ambiguous, which options were weighed, what was chosen, and what was
given up. Approved decisions are recorded in full in
[`decisions.md`](decisions.md).

This is a summary, not a transcript. Detailed working notes are kept locally and
untracked.

---

## Ambiguities identified in the exercise

**The deadline is internally inconsistent.** The document's header states a
five-calendar-day deadline; the submission section states ten. This was flagged
rather than silently resolved, and the project planned against the stricter
reading, which is also the one stated in the formal deadline field.

**SQL safety is never mentioned.** The exercise asks for graceful handling of
unsupported queries, empty result sets, and malformed SQL, but says nothing about
treating model-generated SQL as untrusted. Building deterministic safety controls
is therefore an unprompted judgment signal — valuable only if it is demonstrated
and tested rather than asserted.

**Ambiguity handling is scored but undefined.** The evaluation criteria ask
whether the agent "handles ambiguity reasonably" without saying what reasonable
means. The project defines the contract explicitly: ambiguity and unsupported
questions are first-class states the model declares, not outcomes inferred from
prose.

**"Revenue" is not a SQL question.** The exercise's third example question asks
for top event categories by total revenue. Whether that means gross or net of
refunds, and which statuses count, is a business decision the data cannot answer
on its own. The project makes the definition explicit and carries it through the
schema context, tests, evaluation, and documentation.

---

## Decisions and the alternatives rejected

| # | Decision | Chosen | Principal alternative rejected |
|---|---|---|---|
| D-001 | Dataset | Small synthetic BSE ticketing schema from a deterministic seed | Chinook — cannot answer any of the exercise's printed example questions |
| D-002 | Runtime | Python pinned to 3.13 under `uv` with a committed lockfile | System interpreter with a package-only pin, which leaves the interpreter uncontrolled |
| D-003 | Database | SQLite, generated not committed | DuckDB, and PostgreSQL — the latter's stronger enforcement costs reviewer setup |
| D-004 | Model integration | Direct OpenAI-compatible SDK behind one narrow contract | An agent framework, for a pipeline with no orchestration to orchestrate |
| D-005 | Schema context | Introspected structure plus a semantic metadata sidecar | Introspection alone, which is silent on meaning; static prose alone, which drifts |
| D-006 | SQL safety | Static AST policy plus layered runtime enforcement | A single control; string-level heuristics |
| D-007 | State machine | Twelve typed terminal states, deterministic formatting | A second model call to write the answer |
| D-008 | Interface | CLI only | A web interface, which doubles presentation work across every state |
| D-009 | Testing | Fully offline suite, four layers, independent safety tests | Tests that call a live model |
| D-010 | Evaluation | Development set plus locked holdout, result equivalence | Exact SQL-string matching; a single accuracy number |
| D-011 | Observability | Standard-library JSON Lines to stderr | A hosted platform or tracing backend |
| D-012 | Repository | One package under `src`, restructured before implementation | Retaining the speculative empty package tree |

---

## The tradeoffs that mattered most

### Domain accuracy against the appearance of self-grading

The exercise permits any dataset and names Chinook explicitly, which would have
been the safe choice. It cannot answer a single one of the three example
questions the exercise prints — the questions a reviewer is most likely to type.

Choosing a synthetic BSE schema buys that, and pays for it with a fair objection:
the schema, the data, and the evaluation questions are all ours, so any accuracy
figure is open to the charge of being self-graded. The mitigations are structural
rather than rhetorical — the generator will be committed with a fixed seed so the
data is inspectable rather than hand-placed, and the seed will deliberately
include canceled events, refunds, zero-dollar tickets, and a guaranteed
empty-result case so the dataset can make the agent fail.

### Provable controls against convenient types

DuckDB offers native date and decimal types that would have simplified date
filtering and revenue arithmetic. SQLite was chosen because it provides a simpler
zero-server, standard-library path whose controls fit this implementation and
reviewer setup.

The type advantages turned out to be smaller than they looked. Dates will be
resolved by the application before prompting, so the model receives explicit
boundaries rather than computing them. The schema will store money as integer
cents, which gives exact revenue arithmetic and is arguably the better modelling
choice — at the cost of a new risk, since a computed column's unit is not
declared anywhere in the result set.

### One control against several independent ones

The safety design specifies six independent safety layers: a read-only
connection, a session pragma, static AST policy, a default-deny runtime
authorizer, an instruction budget, and a fetch cap.

Layers are only worth having when they **cannot fail the same way**. A construct
the SQL parser reads differently from SQLite still meets the authorizer, which
runs inside SQLite on the real execution plan rather than on a parse tree. A
misconfigured authorizer still meets the read-only connection. The fetch cap
bounds returned materialization while the instruction budget bounds computation,
and neither substitutes for the other.

That is also why the approved test plan requires each layer to be tested with the
others deliberately bypassed. A passing end-to-end safety test would prove that
*something* held, not which thing.

### A pretty answer against an answer that cannot be wrong

Formatting the final response with a second model call would produce more fluent
prose. It was rejected because deterministic formatting has a property fluency
cannot buy: it can only restate what the executed result contains, so it cannot
assert something the query did not return.

The same principle drove the unit-handling rule. A computed column such as a
summed revenue expression carries no declared unit, and formatting it as currency
on the strength of its name would produce a wrong monetary figure that passes
every structural control in the system. The rule is that a unit is honored only
when it can be proven from the projection expression and trusted metadata. When it
cannot, the value is returned raw — an unglamorous outcome that is never wrong.

### Rigor against the time box

The specification is larger than the remaining schedule comfortably supports. The
response was to decide the cut order in advance rather than improvise it under
pressure: the second model candidate first, then the optional REPL, then advanced
unit-lineage rules beyond the minimum the evaluation actually requires, then
optional diagnostic polish, and only last the number of evaluation repetitions.

The ordering follows engineering time saved. Reducing repetitions saves evaluation
runtime and cost but almost no implementation work, so it must not precede cuts
that meaningfully reduce delivery risk.

---

## Corrections made during the workshop

Recorded because they changed the design, not merely its wording.

- **"Every safety decision is made on the AST" was false.** The authorizer, the
  session pragma, and the instruction budget are runtime controls. The AST owns
  static query-shape policy; SQLite owns runtime enforcement. Overclaiming here
  would have undercut the layering argument itself.
- **A column allowlist checked against the union of all database columns rejects
  valid SQL.** It would refuse projection aliases used in ordering, CTE output
  columns, and aggregate aliases. A control that fails on correct input is worse
  than no control, so the broad check was dropped in favor of SQLite's own name
  binding under the authorizer, with the limitation documented.
- **A naive table allowlist would reject every CTE name.** Physical source tables
  must be distinguished from query-local relation names.
- **"Unsafe" was the wrong name for the rejection state.** An unknown table, an
  unsupported but harmless function, and a validator false positive are not
  attacks. Rejections carry machine-readable reasons instead.
- **A test double must not violate its own contract.** Simulating malformed model
  output by having the fake return an invalid decision object would quietly say
  the type boundary is not real. Malformed payloads will be covered by tests at
  the adapter boundary where they originate; the fake raises typed failures.
- **An alias is a claim, not evidence.** An alias containing "net" communicates
  intent; it does not prove refunds were handled correctly. The formatter does not
  narrate business semantics from a string the model chose.
- **A threshold set after seeing results is not a threshold.** The quality gate is
  written down and frozen before any formal result is reviewed, and cannot be
  lowered retroactively.
- **The application is not dataset-agnostic.** The introspection mechanism,
  metadata format, and renderer are reusable; the semantic metadata, evaluation
  cases, and seed data are dataset-specific by design. The throwaway-schema test
  proves the machinery moves, not that the system answers correctly elsewhere.

---

## Unresolved risks carried into implementation

**Second-candidate eligibility — since resolved.** The open-weight comparison
candidate is reachable only through a hosted endpoint, and strict schema
enforcement is a property of that endpoint rather than of the model. A live
endpoint smoke test on 2026-07-28 confirmed eligibility, so the comparison is no
longer provisional. The contingency stands if the endpoint later becomes
unavailable: record the comparison as blocked rather than present it as
equivalent, and let the primary model path proceed unchanged.

**Environment verification.** Strict-table support depends on the SQLite library
bundled with the pinned interpreter, and foreign-key enforcement is per-connection
and off by default. Both will be verified rather than assumed, and both have
approved fallbacks. Neither has been checked yet.

**Scope against schedule.** The planned unit-lineage analyzer is the largest
single piece of new logic. Its approved design explicitly permits returning
"unknown" for unsupported expressions, which is what would make a reduced rule set
a safe reduction rather than a correctness compromise.

**Business-formula correctness.** The design can establish that a value is in
cents. It cannot establish that the query implemented the approved revenue
definition. That remains an evaluation concern, and is stated as a limitation
rather than covered by a control.

---

## Deliberately deferred

PostgreSQL with role-level read-only enforcement and a real statement timeout; a
graphical interface; a bounded one-shot SQL repair attempt; sample-row injection
as a measured enhancement; a semantic business-formula validator; multi-turn
memory; a generalized provider abstraction; full alias-and-scope column
resolution.
