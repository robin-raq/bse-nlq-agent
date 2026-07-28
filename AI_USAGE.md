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

## 2026-07-28 — Repository restructuring (prepared, uncommitted)

### Tools used

- Claude Code (Claude Opus) for restructuring assistance and validation
- `uv` 0.11.28 for interpreter management, dependency resolution, and locking

### Package and dependency decisions

The single application package is `src/bse_nlq/`, using a `src/` layout so that
accidental working-directory imports cannot mask packaging errors. Hatchling was
chosen as the build backend because it supports the `src/` layout with minimal
configuration and adds no runtime dependency.

Direct runtime dependencies were limited to the two already justified by the
approved architecture: the OpenAI SDK for the OpenAI-compatible provider path,
and SQLGlot for dialect-aware AST validation. Direct development dependencies
were limited to `pytest`, `pytest-cov`, `ruff`, and `mypy`.

Deliberately not added: LangChain or any agent framework, an ORM, a YAML parser,
a CLI framework, a logging or telemetry library, a retry library, a provider
abstraction library, and any additional security or analysis tooling. Pydantic is
present only as a transitive dependency of the OpenAI SDK; whether to use it for
the `ModelDecision` contract remains an open implementation choice rather than a
new dependency.

Project metadata was kept minimal and factual. No author, licence, homepage, or
publication metadata was invented. No console entry point was declared, because
declaring one without a real callable CLI module would have been a fake.

### Files created

`src/bse_nlq/__init__.py` (package docstring only), `pyproject.toml`,
`.python-version`, `uv.lock`, `.env.example` (variable names only, no values),
`tests/unit/test_package_import.py`.

### Files removed

All speculative empty scaffolding: `src/agent/.gitkeep`,
`src/database/.gitkeep`, `src/sql/.gitkeep`, `src/response/.gitkeep`,
`src/evals/.gitkeep`, `tests/evals/.gitkeep`, `tests/integration/.gitkeep`, and
their now-empty directories. No replacement placeholders were created. No empty
speculative source or test directory remains.

### Files modified

`.gitignore` — removed only the dead "force-added seeded databases" comment,
which described a rule that did not exist. All existing ignore rules were
preserved.

### Manual review performed

Every `.gitkeep` was inspected individually before removal rather than assumed
empty: each was confirmed to be exactly 0 bytes, with no hidden entries, no
symlinks, and no unique content in any of the directories.

The resolved dependency tree was inspected for unexpected direct dependencies.
Direct dependencies matched the approved set exactly; everything else is
transitive through the OpenAI SDK.

### Validation commands and outcomes

| Command | Outcome |
|---|---|
| `uv run python --version` | Python 3.13.14 |
| `uv run ruff format --check .` | 12 files already formatted |
| `uv run ruff check .` | All checks passed |
| `uv run mypy src` | Success, no issues in 1 source file |
| `uv run pytest` | 1 passed |
| `uv lock --check` | Resolved 32 packages, lockfile current |
| `git diff --check` | clean |
| Package import from installed environment | `bse_nlq` imports successfully |
| Tracked-file secret scan | clean |

### Unexpected findings

A database-artifact check initially reported sixteen `*.db` files, which looked
like an accidental application database. Inspection showed all sixteen were
`.mypy_cache/3.13/cache.*.db` — mypy's own incremental cache, already covered by
the `.mypy_cache/` ignore rule and confirmed ignored via `git check-ignore`. No
application database exists, and none is tracked. Subsequent checks exclude tool
caches explicitly so the false alarm does not recur.

Separately, an incidental local observation was made while exploring the pinned
interpreter. Against three `sqlite3.connect(":memory:")` connections, issuing
`PRAGMA foreign_keys=ON` on a fresh connection returned `1`, but issuing the same
pragma after an `INSERT` had opened an implicit transaction returned `0` — the
setting was silently ignored, and took effect only after a commit. **No
application database was created; all three probes were in-memory.**

This was an incidental observation, **not** part of SQLite prerequisite
verification, which remains outstanding. It establishes nothing about
application foreign-key enforcement, `STRICT`-table support, or the database
trust boundary as a whole.

Its one narrow implication for the future connection factory: foreign-key
enforcement must be enabled before any statement opens a transaction, and the
resulting pragma value must be read back and asserted rather than assumed.

### Deferred work and blockers

`tests/integration/` was intentionally deferred and will be created when the
first real integration test exists; the D-012 integration-test category remains
approved. Adapter, CLI, and safety test directories are likewise deferred until
they hold real tests.

This change is **prepared but uncommitted**, pending review.

### Explicitly not done in this phase

No application feature code was written. No credentials were used, no model was
called, no application database was created, and no evaluation was run. The only
network activity was dependency resolution through `uv`.
