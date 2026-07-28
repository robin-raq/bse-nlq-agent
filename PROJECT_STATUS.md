# Project Status

Last updated: 2026-07-28
Current phase: Architecture complete; implementation not started

This is the repository's concise implementation handoff and persistent context
document for coding agents. It is **not architecture authority** — approved
decisions live in `docs/planning/decisions.md` and always take precedence.

## Last completed work

- Architecture documentation committed at `9e87d00`
  ("docs: record approved NLQ-to-SQL architecture").
- Approved decisions D-001 through D-012 recorded in
  `docs/planning/decisions.md`.
- Architecture diagrams and reviewer-facing design documentation added.
- The empty `docs/planning/architecture-review.md` placeholder was removed.
- No push has occurred.

## Verified current state

- Branch: `main`
- Working tree: cleanliness is transient. Verify the current state with
  `git status --short` at the beginning of each work session rather than relying
  on this file.
- Source implementation: not started
- Dependencies: not installed
- Database: not created
- Automated tests: not implemented, none have run
- Provider smoke tests: not run
- Evaluation: not run
- Credentials: none used

## Current objective

Perform the isolated repository restructuring approved in D-012, together with
the environment and provider prerequisites that precede it.

## Immediate next actions

1. Verify OpenAI API billing and access to the selected GPT-5 mini model.
2. Run the minimal strict structured-output smoke test against that endpoint.
3. Attempt the optional Groq `openai/gpt-oss-120b` endpoint verification, without
   allowing it to block the MVP.
4. Verify the bundled SQLite version and `STRICT`-table support in the pinned
   environment.
5. Perform the isolated repository restructuring.
6. Establish `src/bse_nlq/`, packaging files, and entry-point skeletons
   containing real content only.
7. Implement the deterministic dataset seed, SQLite schema, and semantic
   metadata sidecar.

## Active blockers

- OpenAI billing and exact GPT-5 mini access have not been verified.
- Strict structured-output behavior has not been smoke-tested.
- Groq account and hosted GPT-OSS eligibility have not been verified.
- SQLite `STRICT` support has not been verified.

**Only the OpenAI live path blocks the model-backed MVP.** Groq eligibility and
`STRICT` support both have approved fallbacks and do not block delivery. Offline
implementation and tests can proceed regardless of provider access.

## Approved fallbacks

- If Groq is unavailable or ineligible, proceed with GPT-5 mini and record the
  comparison as blocked.
- If SQLite `STRICT` is unavailable, use ordinary SQLite tables with explicit
  `CHECK` constraints.
- If the REPL threatens the timebox, omit it and retain `ask`, stdin input, and
  JSON output.
- If advanced unit-lineage rules threaten the timebox, retain the minimum
  required rules and return `unknown` rather than guessing.

## Non-negotiable constraints

- One semantic model-generation attempt per request
- Bounded transport retries only
- No model-controlled SQL repair loop
- No runtime model selector or automatic provider failover
- The automated pytest suite remains offline
- Model output and generated SQL remain untrusted
- Essential SQL safety controls exist before the first model-generated query is
  executed
- `AI_USAGE.md` is updated at every completed implementation phase

## Validation commands and outcomes

No application validation commands exist yet. Documentation-only checks were run
against the architecture snapshot before `9e87d00`: Markdown fence balance,
relative-link resolution, Mermaid source structure, and a tracked-file secret
scan. Diagrams were not rendered.

Record real commands and their outcomes here once they exist.

## Not yet done

- Package restructuring into `src/bse_nlq/`
- Runtime and dependency setup (`pyproject.toml`, `uv.lock`, `.python-version`,
  `.env.example`)
- Deterministic seed script
- SQLite schema
- Semantic metadata sidecar
- Schema introspection and context renderer
- Prompt builder
- Provider adapter
- `QueryService`
- SQL validator
- SQLite authorizer
- Result-unit analyzer
- CLI
- Automated tests (unit, adapter, integration, CLI, safety)
- Provider smoke tests
- Development-set evaluation
- Locked holdout evaluation
- Final README setup, usage, testing, and evaluation content written from
  commands that actually ran
