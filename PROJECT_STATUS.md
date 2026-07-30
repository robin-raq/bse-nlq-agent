# Project Status

Last updated: 2026-07-29

This is the operational handoff for coding agents. Read it before starting work to understand the verified repository state, the next implementation objective, and active constraints. Architecture authority remains in `docs/planning/decisions.md` and `ARCHITECTURE.md`.

## Current phase

The SQLite physical schema, the deterministic 109-row seed, and the JSON semantic metadata sidecar are implemented and test-first verified against the frozen contracts in `docs/planning/schema-design.md` and `docs/planning/seed-manifest.md`. Physical structure remains SQLite-owned; business meaning remains JSON-owned. Runtime prompt construction remains pending. The next implementation step is a persistent application database artifact and build/distribution commands.

Design artifacts: `docs/planning/schema-design.md` (physical contract), `docs/planning/seed-manifest.md` (exact deterministic literals), `docs/diagrams/schema-erd.md` (ERD), `src/bse_nlq/metadata/schema.json` (semantic sidecar).

No application feature path exists yet: a user cannot submit a question, generate SQL, or query through a service/CLI. No persistent database file exists.

**All 14 development anchors have been executed successfully against the real seeded in-memory database.** A13 returns E11 only; A14 returns zero rows. Invariants I-1 through I-8 and the published reconciliations pass against that seed. This does not claim model-generated SQL or application query-execution services have been tested.

## Completed work

- Architecture, trust boundaries, terminal states, and evaluation approach were agreed and documented.
- The project uses a single `src/bse_nlq/` package with a `src/` layout.
- Python and dependency management were configured with `.python-version`, `pyproject.toml`, and `uv.lock`.
- Direct dependencies were limited to `openai` and `sqlglot`; development tooling includes pytest, pytest-cov, Ruff, and mypy.
- Speculative empty packages were removed.
- SQLite capabilities required by the design were behaviorally checked in the pinned runtime.
- OpenAI and Groq endpoints were smoke-tested for authentication, model access, strict response-shape compatibility, and local `ModelDecision` invariants.
- Reviewer and agent documentation was consolidated to remove duplicated planning history.
- The schema and seed design was worked through and approved: six tables, revenue and refund formulas, ticket-count metrics, attendance model, timestamp convention, unit and rounding rules, a 109-row deterministic seed with reconciliation totals, and 14 development anchors. Recorded in `docs/planning/schema-design.md` and `docs/planning/decisions.md`.
- Ambiguity policy, time-of-day limits, refund-measure independence, and an executable I-6 were frozen after independent review. Exact seed literals were completed in `docs/planning/seed-manifest.md`, and an ERD was added at `docs/diagrams/schema-erd.md`.
- The SQLite physical schema was implemented test-first at `src/bse_nlq/db/schema.py`: six `STRICT` tables, all approved `CHECK` domains and numeric constraints, the two `STORED` generated columns (`events.event_date`, `order_items.line_gross_cents`), all foreign keys with `ON UPDATE RESTRICT ON DELETE RESTRICT`, and the ten approved indexes. The public API is `apply_schema(connection: sqlite3.Connection) -> None`.
- The deterministic seed was implemented test-first at `src/bse_nlq/db/seed.py` and `src/bse_nlq/db/seed_data.py`. The public API is `load_seed_data(connection: sqlite3.Connection) -> None`. It inserts exactly the manifest literals (4 + 14 + 36 + 20 + 28 + 7 = 109 rows) into a caller-supplied connection after schema application, never calls `apply_schema`, rejects an already-active caller transaction, verifies `PRAGMA foreign_keys`, inserts atomically, rolls back on any escaping exception after its transaction begins (including non-`sqlite3.Error`), and leaves no open transaction on success or failure. `apply_schema` uses the same BaseException cleanup contract.
- The JSON semantic metadata sidecar was implemented test-first at `src/bse_nlq/metadata/schema.json` with typed loading/validation in `src/bse_nlq/metadata/`. The public API is `load_semantic_metadata(connection: sqlite3.Connection) -> SemanticMetadata`. It loads packaged UTF-8 JSON via `importlib.resources`, validates structure fail-closed (including duplicate JSON object keys), freezes nested mappings with `MappingProxyType`, reconciles every physical application column and exact FK join guidance against SQLite introspection, and does not restate types, primary keys, foreign keys, or nullability. Prompt visibility is complete for all physical columns except `orders.order_ref`. Installed-wheel resource loading is covered by an offline packaging regression test. Runtime prompt construction remains pending.

## Verified state

| Area | Verified evidence |
|---|---|
| Runtime | Python 3.13.14 through `uv` 0.11.28; SQLite 3.53.1 |
| Package | `bse_nlq` imports from the installed environment |
| Toolchain | Ruff formatting and linting, mypy, pytest, and `uv lock --check` passed after scaffolding |
| SQLite | STRICT enforcement, foreign keys, read-only URI, `query_only`, authorizer denial, and progress interruption behaved as required in isolated probes |
| Schema DDL | Contract tests pass against a fresh in-memory connection: object inventory, per-column contracts, foreign keys and `foreign_key_check`, domain/numeric/attendance/date CHECKs (including a static null-safe `IS strftime` DDL guard), generated-column behavior, uniqueness, exact approved-index inventory, static DDL clock-safety, I-1–I-8 enforcement-boundary documentation, and caller-owned / schema-owned transaction-boundary behavior |
| Seed data | Exact table counts 4/14/36/20/28/7 (109 total); primary-key and foreign-key integrity; domain inventories; generated `event_date` and `line_gross_cents`; nine unsold tiers; transaction success/rejection/second-load/mid-load/non-SQLite/`BaseException` failure contracts; FK-disabled rejection. I-1 through I-8 return zero violations on the complete seed; E11 equality uses completed-order grain with a cancelled-order regression. Overall reconciliation: gross 7,270,000 · refunded 810,000 · net 6,460,000 · tickets_sold 957 using completed-order refund filtering; channel/venue/category groupings and January 2026 purchase gross 2,000,000 match the published contract; cancelled-order refunds are excluded from refunded/net/A9; E5 direct-join fan-out regression passes. All 14 anchors execute with expected rows, columns, values, and ordering (A13 = E11 only; A14 = empty). Independent SHA-256 fingerprints pin `seed_data` tuples to the tracked manifest. Analytical trap regressions cover face vs unit price, gross vs net, refund fan-out, weighted average, capacities, E11 sold vs net, date fields, cancelled orders, attendance, and tier identity |
| Semantic metadata | Packaged JSON at `src/bse_nlq/metadata/schema.json`; `load_semantic_metadata` validates and reconciles against a seeded in-memory database. Exactly six application tables; every physical column has semantic coverage; generated columns identified via introspection; join guidance exactly matches the five application FKs; `orders.order_ref` is the sole prompt exclusion; returned nested mappings are `MappingProxyType` / tuple / frozenset and reject mutation; wheel packaging excludes `*.json` by default and force-includes `schema.json` so installed-wheel regression fails closed without that include; no structural override of types/keys/nullability; drift and completeness tests fail closed; content and leak/static-safety scans clean |
| Suite | 69 metadata-focused tests under `tests/unit/metadata/`; 235 tests under `tests/unit/db`; 305 tests in the full offline suite; Ruff lint and format; mypy strict; `uv lock --check`; `git diff --check`; secret-pattern scan clean on tracked and metadata paths |
| OpenAI | GPT-5 mini accepted the strict four-field decision schema and returned a locally valid response |
| Groq | `openai/gpt-oss-120b` accepted the same schema and returned a locally valid response |
| Secrets | Credentials and the private exercise document remain untracked |

Provider checks establish endpoint eligibility only. They do not establish SQL quality, comparative performance, or final model selection. Seed and anchor verification establish dataset correctness only; they do not establish model-generated SQL quality or an application query service. Metadata verification establishes business-meaning contracts only; it does not construct runtime prompts or call a model.

## Immediate next objective

Continue the data foundation. Schema DDL, deterministic seed loading, and the semantic metadata sidecar are complete; remaining steps:

1. Persistent application database artifact and any approved build/distribution commands.
2. Run the full formatting, linting, typing, test, lockfile, and secret checks after that work.
3. Reconcile `PROJECT_STATUS.md` with verified outcomes and update `AI_USAGE.md` only if the phase materially changes the reviewer-facing AI disclosure.

Do not begin provider integration, prompt iteration, or model-generated SQL execution during the remaining data-foundation work.

## Subsequent sequence

1. Read-only connection factory, authorizer, progress budget, and fetch cap.
2. SQLGlot policy and unit inference with isolated safety tests.
3. Schema-context renderer, date resolution, and prompt builder.
4. Provider adapters and shared `ModelDecision` validation.
5. `QueryService`, deterministic formatting, and terminal-state mapping.
6. CLI and JSON contract.
7. Development evaluation, frozen holdout, and final model selection.

## Active blockers

None.

Model quality and final selection are intentionally blocked on the frozen evaluation, not on missing access or endpoint compatibility.

## Non-negotiable constraints

- One semantic model-generation attempt per request; bounded transport retries only.
- No model repair loop, runtime provider selector, or automatic failover.
- Automated tests must run offline without credentials.
- Questions, model output, and generated SQL remain untrusted.
- All essential SQL safety controls must exist before the first model-generated query is executed.
- Unknown units remain raw rather than guessed.

## Approved fallbacks

- If Groq later becomes unavailable, continue with GPT-5 mini and report the comparison as blocked.
- If SQLite STRICT is unavailable in another environment, use ordinary tables with explicit `CHECK` constraints.
- If scope must be cut, remove the optional REPL and advanced unit inference before weakening the core CLI, safety boundary, or evaluation integrity.

## Not yet implemented

Application database factory / persistent database file, SQL policy, provider adapters, service, result formatting, CLI, integration and safety suites, evaluation cases, evaluation results, and final model selection.

The physical schema DDL (`apply_schema`), deterministic seed loader (`load_seed_data`), and semantic metadata sidecar (`load_semantic_metadata`) are implemented and test-verified (see Verified state). No persistent database file exists. Runtime prompt construction remains pending.
