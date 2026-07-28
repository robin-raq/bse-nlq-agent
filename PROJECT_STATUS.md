# Project Status

Last updated: 2026-07-28
Current phase: Repository restructuring complete; prerequisite verification next.

This is the repository's concise implementation handoff and persistent context
document for coding agents. It is **not architecture authority** — approved
decisions live in `docs/planning/decisions.md` and always take precedence.

## Last completed work

- Architecture documentation committed at `9e87d00`.
- Agent handoff contract committed at `51df1a6`.
- Pre-implementation contracts frozen at `e8051f5` — authority hierarchy,
  `bse_nlq` package name, the `ModelDecision` contract, the D-010 evaluation
  gate, Groq-or-blocked hosting disposition, and implementation freeze points.
- No push has occurred; the repository has no remote configured.

## Repository restructuring (D-012)

The approved restructuring is done. The repository now has a real Python project
with a reproducible toolchain and no speculative scaffolding.

- Package established at **`src/bse_nlq/`**, containing only `__init__.py` with
  a package docstring.
- Speculative placeholder packages removed: `src/agent/`, `src/database/`,
  `src/sql/`, `src/response/`, `src/evals/`, `tests/evals/`,
  `tests/integration/`. Every removed `.gitkeep` was verified to be 0 bytes
  before removal.
- Packaging created: `pyproject.toml` (hatchling, `src/` layout),
  `.python-version`, committed `uv.lock`, `.env.example` with names only.
- `.gitignore`: removed the dead force-add comment; all prior ignore rules
  preserved.
- One package-import smoke test exists at
  `tests/unit/test_package_import.py` and passes.
- No console entry point is declared, because no CLI module exists yet.

## Verified current state

- Branch: `main`
- Working tree: cleanliness is transient. Verify with `git status --short` at the
  start of each work session rather than relying on this file.
- Python: **3.13.14** through `uv` 0.11.28
- Direct runtime dependencies: `openai`, `sqlglot`
- Direct development dependencies: `pytest`, `pytest-cov`, `ruff`, `mypy`
- Application features: **none implemented**
- Provider smoke test: **not run**
- Application database: **not created**
- Evaluation: not run
- Credentials: none used

## Validation outcomes

Run from the pinned `uv` environment against the prepared working tree:

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

SQLite library version reported by the pinned interpreter is 3.53.1. **This is
version evidence only and is not a verified `STRICT`-table capability claim** —
that belongs to the prerequisite smoke-test phase.

## Current objective

Verify the pinned SQLite environment and run the provider prerequisite smoke
tests before feature implementation.

## Immediate next actions

1. Verify the pinned SQLite environment: `STRICT`-table enforcement and
   foreign-key behavior, as behavior rather than version numbers.
2. Verify OpenAI API billing and access to the selected GPT-5 mini model.
3. Run the minimal strict structured-output smoke test against that endpoint.
4. Attempt the optional Groq `openai/gpt-oss-120b` endpoint verification, without
   allowing it to block the MVP.
5. Implement the deterministic dataset seed, SQLite schema, and semantic
   metadata sidecar.

## Active blockers

- OpenAI billing and exact GPT-5 mini access have not been verified.
- Strict structured-output behavior has not been smoke-tested.
- Groq account and hosted GPT-OSS eligibility have not been verified.
- `STRICT`-table enforcement has not been verified as behavior.

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

## Not yet done

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
- CLI and its console entry point
- Adapter, integration, CLI, and safety test suites
- Provider smoke tests
- Development-set evaluation
- Locked holdout evaluation
- Final README setup, usage, testing, and evaluation content written from
  commands that actually ran

`tests/integration/` is intentionally deferred and will be created when the
first real integration test exists. The D-012 integration-test category remains
approved.
