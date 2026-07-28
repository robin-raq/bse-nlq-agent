# AI Usage Disclosure

This document provides a curated, reviewer-facing disclosure of material AI
assistance used during the candidate exercise. It is not a raw prompt history
or chat transcript.

Detailed prompts, scratch notes, and routine interactions may be recorded in
the ignored `AI_USAGE.local.md` file. Only assistance that materially affects
architecture, implementation, testing, evaluation, safety, or submitted
artifacts should be summarized here.

## 2026-07-25 — Repository initialization

### Tools used

- ChatGPT for workflow design and repository setup guidance
- Claude Code with the Compound Engineering plugin installed for future planning,
  implementation, and review

### Work performed

- Created the initial repository structure
- Established project scope and engineering guardrails
- Configured Git exclusions for private exercise materials and secrets
- No application implementation has been generated yet

### Manual review

- Confirmed the candidate exercise PDF remains local and untracked
- Reviewed the proposed directory and documentation structure

## 2026-07-27 to 2026-07-28 — Architecture workshop

### Tools used

- Claude Code (Claude Opus) as an interactive design counterpart for the
  architecture workshop and for drafting the architecture documentation
- ChatGPT for earlier workflow and repository setup guidance

### How the workshop was run

The architecture was developed as a sequence of single decisions. For each one,
the assistant presented realistic options, concrete project-specific tradeoffs, a
recommendation, and what the recommendation gave up. I approved, modified, or
rejected each decision explicitly, and I set the constraints the design had to
satisfy. Every approved decision is recorded in `docs/planning/decisions.md`.

Substantial parts of the final specification originated from my modifications
rather than from the assistant's proposals — including the flattened structured-
output schema, the default-deny authorizer, the precommitted quality gate, the
development-versus-holdout evaluation split, the result-unit lineage analyzer, the
logging privacy posture, and the repository layout.

### Where AI assistance materially affected the design

- Framing the safety architecture as independent controls with different failure
  modes, and the accompanying rule that a control is not described as effective
  unless a test demonstrates it
- Identifying the deadline contradiction in the exercise document rather than
  resolving it silently
- Identifying that a computed monetary column carries no declared unit, which led
  to the rule that a unit is honored only when it can be proven
- Drafting `ARCHITECTURE.md`, the decision log, the workshop summary, the Mermaid
  diagrams, and this README architecture content, from decisions I approved

### Corrections I made to AI proposals

I reviewed and corrected the assistant's proposals throughout. The most material
corrections were:

- A proposed column-validation control that would have **rejected valid SQL**
  (projection aliases in ordering, CTE output columns, aggregate aliases). It was
  replaced with a narrower approach and an honestly documented limitation.
- A proposed table allowlist that would have **rejected every CTE name** as an
  unknown table.
- An overbroad safety claim — "every safety decision is made on the parsed AST" —
  which is false, since the authorizer, session pragma, and instruction budget are
  runtime controls.
- A test double that would have **violated its own type contract** to simulate
  malformed output. Malformed payloads now belong to adapter-boundary tests.
- A formatter that would have described a result as "net revenue after refunds"
  from the model's chosen alias. An alias states intent, not correctness.
- Logging defaults that would have captured raw user questions and exposed full
  prompts at debug level. Both were tightened.
- Two unfounded factual claims: a submission deadline inferred from repository
  metadata, and an assertion that both evaluation candidates could share one API
  key.

The complete cross-cutting correction record, including corrections that changed
framing rather than a single decision, is in
[`docs/planning/architecture-workshop.md`](docs/planning/architecture-workshop.md).
Decision-specific corrections are recorded inside the relevant entries in
[`docs/planning/decisions.md`](docs/planning/decisions.md).

### Validation performed during this phase

- The exercise PDF text was extracted locally and read in full; no requirement was
  inferred or guessed
- Local runtime versions were checked directly rather than assumed
- The architecture-review placeholder was inspected before removal and contained
  no unique content

### Explicitly not done in this phase

No application code was written, no dependencies were installed, no database was
created, no credentials were used, and no model evaluation was run. Everything
recorded so far is specification.
