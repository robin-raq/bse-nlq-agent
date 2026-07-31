# Project Status

Last updated: 2026-07-30

This is the operational handoff for coding agents. Read it before starting work to understand the verified repository state, the next implementation objective, and active constraints. Architecture authority remains in `docs/planning/decisions.md` and `ARCHITECTURE.md`.

## Current phase

The read-only runtime database factory (U1) is implemented and test-first
verified offline. `open_readonly_database` returns a context-managed
`ReadOnlyDatabase` that privately owns a `mode=ro` SQLite connection with
verified `foreign_keys` / `query_only`, exact sibling sidecar rejection,
metadata reconciliation before readiness, and immutable physical/visible/
excluded schema inventories. Schema, seed, semantic metadata, ModelDecision
validation, deterministic prompt construction, and the persistent builder
remain in place. No SQLGlot validator, authorizer, progress/result limits,
controlled executor, QueryService, provider adapter, live model request for
SQL quality, or product CLI is implemented.

Design artifacts: `docs/planning/schema-design.md` (physical contract), `docs/planning/seed-manifest.md` (exact deterministic literals), `docs/diagrams/schema-erd.md` (ERD), `src/bse_nlq/metadata/schema.json` (semantic sidecar).

No end-to-end application feature path exists yet: a user cannot submit a question through a service/CLI that calls a provider or executes generated SQL. A developer may build a local untracked database file and open it read-only; that is not the product ask path.

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
- The JSON semantic metadata sidecar was implemented test-first at `src/bse_nlq/metadata/schema.json` with typed loading/validation in `src/bse_nlq/metadata/`. The public API is `load_semantic_metadata(connection: sqlite3.Connection) -> SemanticMetadata`. It loads packaged UTF-8 JSON via `importlib.resources`, validates structure fail-closed (including duplicate JSON object keys), freezes nested mappings with `MappingProxyType`, reconciles every physical application column and exact FK join guidance against SQLite introspection, and does not restate types, primary keys, foreign keys, or nullability. Prompt visibility is complete for all physical columns except `orders.order_ref`. Installed-wheel resource loading is covered by an offline packaging regression test.
- Strict `ModelDecision` validation was implemented test-first at `src/bse_nlq/decision/`. The public API is `parse_model_decision_json` / `validate_model_decision` → immutable `ModelDecision`. Fail-closed parsing rejects malformed JSON, duplicate keys, unknown keys, wrong types, and contradictory status/field combinations, mapping all envelope failures to `InvalidModelOutputError` (`terminal_state=invalid_model_output`). A deterministic provider-neutral JSON Schema is exposed via `model_decision_json_schema`.
- Deterministic prompt construction was implemented test-first at `src/bse_nlq/prompt/`. The public API is `build_prompt(PromptInput) -> BuiltPrompt`. It renders physical structure from SQLite introspection, business meaning from validated semantic metadata, frozen application rules, and the ModelDecision response schema. Default `as_of` is the frozen `2026-03-15` date when omitted. A provider-neutral `RawModelGenerator` protocol and `decide_from_raw_generator` one-shot helper live in `src/bse_nlq/generator.py` for offline boundary tests. No provider call or SQL execution is performed.
- The deterministic persistent database builder was implemented test-first at `src/bse_nlq/db/build.py` with artifact validation in `src/bse_nlq/db/artifact.py`. The public API is `build_database(destination, *, overwrite=False) -> DatabaseBuildResult`. It validates destination preconditions (non-symlink regular files only when overwriting), builds into a unique temporary sibling via `apply_schema` then `load_seed_data`, computes file evidence before publication, publishes with atomic no-clobber `os.link` when `overwrite=False` or `os.replace` when `overwrite=True`, removes exact destination `-wal`/`-shm`/`-journal` sidecars only after successful publication, and distinguishes post-publication hygiene failures from pre-publication failures. Concurrent external use of the destination during publication is unsupported. Generated `*.db` / `*.sqlite` / `*.sqlite3` paths remain gitignored. Developer utility: `python -m bse_nlq.db.build PATH [--overwrite]`.
- The read-only runtime database factory was implemented test-first at `src/bse_nlq/db/runtime.py`. The public API is `open_readonly_database(database_path: Path | str) -> ReadOnlyDatabase`. It opens an existing nonsymlink regular file via `Path.as_uri()` with `mode=ro`, enables and verifies `foreign_keys` and `query_only`, rejects exact sibling `-wal`/`-shm`/`-journal` sidecars without deleting them, reconciles packaged semantic metadata before readiness, exposes immutable physical/visible/excluded inventories, privately owns the connection (no public arbitrary-SQL surface), and fail-closes with idempotent close. Existing filenames containing `?`, `#`, `%`, spaces, or Unicode are supported; missing ordinary paths are missing-path errors. No SQLGlot policy, authorizer, progress handler, executor, or QueryService was added.
- A follow-up hardening pass closed an independent audit of the runtime factory. All path preconditions (including `~` expansion and filesystem inspection) now evaluate inside the factory's exception boundary, so `RuntimeError` from unresolvable `~user` and `ValueError` from embedded NUL surface as `DatabaseRuntimeError` with `__cause__` preserved; `KeyboardInterrupt` / `SystemExit` still propagate unwrapped after cleanup. `close()` no longer swallows an underlying close failure — it raises `DatabaseRuntimeError` and leaves the wrapper open so a failed close is never reported as success. Three unreachable post-reconciliation checks (already guaranteed by `reconcile_metadata` and by constructing the visible/excluded inventories from the same metadata columns) were removed. `database_path` is documented and tested as immutable identity that remains readable after close.
- A focused exception-boundary review follow-up narrowed ordinary open normalization from bare `except Exception` to `OSError | RuntimeError | ValueError | TypeError | sqlite3.Error` (with `MetadataError` still dedicated), so programming defects propagate after cleanup; removed the unreachable `os.fspath` guard; documented context-manager double-failure chaining and failed-open cleanup asymmetry.
- An independent post-baseline audit found that the narrowed tuple above was still scoped by exception *type* across the whole open sequence rather than by the specific *operation* that can legitimately raise it, so a `RuntimeError`/`TypeError`/`ValueError` from a bug inside a metadata/inventory helper or the PRAGMA setup helper was silently normalized as an ordinary `DatabaseRuntimeError`, contradicting the documented contract. Normalization is now localized: `sqlite3.connect` and post-connect SQLite setup (`_disable_load_extension`, `_enable_and_verify_pragma`) each normalize only `sqlite3.Error` at their own call sites; the metadata step normalizes only `MetadataError` and `sqlite3.Error`; path preconditions remain self-contained inside `_validate_database_path` as before. Programming defects from those same helpers now propagate unwrapped after cleanup. Three pre-existing tests that had injected a bare `RuntimeError` as a stand-in "primary failure" through `_enable_and_verify_pragma`/`_disable_load_extension`/`load_semantic_metadata` and asserted it should normalize were corrected to inject a genuine `sqlite3.Error` instead, since a bare `RuntimeError` from those call sites is a programming defect under the corrected contract, not an expected failure mode.

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
| ModelDecision + prompt | Offline decision/prompt suite covers raw JSON parsing, duplicate keys, status invariants, immutability/source isolation, JSON Schema inventory alignment, schema/semantic rendering, prompt determinism, leak inventory, injection-boundary delimiting, and fake-generator one-shot parsing. No provider network call; no SQL execution |
| Persistent database build | `build_database` publishes a validated six-table / 109-row SQLite file; evidence is precomputed from the closed temporary artifact; `overwrite=False` uses atomic no-clobber `os.link`; `overwrite=True` uses `os.replace` then removes exact destination `-wal`/`-shm`/`-journal` sidecars before success; only non-symlink regular files may be overwritten; destination refusal/race/special-file/failure-preservation, logical fingerprint reproducibility, developer module entry point, gitignore coverage, and installed-wheel build regression pass offline. Concurrent destination mutation during publication is unsupported. File SHA-256 is same-environment evidence only; `PRAGMA foreign_keys` remains connection-local |
| Read-only runtime factory | `open_readonly_database` returns a ready `ReadOnlyDatabase`; path guards (including literal-`?` filenames vs missing-path classification, exact sibling sidecars, suffix-named mains), `mode=ro` independent of `query_only`, metadata inventories, fail-closed cleanup, and lifecycle contracts covered by 88 offline runtime tests; no public execute surface. Error-contract coverage includes unresolvable `~user` expansion and embedded-NUL paths normalizing to `DatabaseRuntimeError` with preserved cause, exception normalization localized to the specific path/SQLite/metadata operation that can legitimately raise it (so same-type programming defects from unrelated helpers propagate, not just differently-typed ones), a stubbed close failure that raises and stays retryable, `KeyboardInterrupt` from close propagating unwrapped, and `database_path` readable after close while connection-dependent properties reject use |
| Suite | Decision/prompt-focused tests: 92 under `tests/unit/decision/`; 69 metadata under `tests/unit/metadata/`; 377 under `tests/unit/db` (includes persistent-build and runtime coverage); 539 in the full offline suite; Ruff lint and format; mypy strict; `uv lock --check`; `git diff --check`; secret-pattern scan clean on tracked and new paths |
| OpenAI | GPT-5 mini accepted the strict four-field decision schema and returned a locally valid response |
| Groq | `openai/gpt-oss-120b` accepted the same schema and returned a locally valid response |
| Secrets | Credentials and the private exercise document remain untracked |

Provider checks establish endpoint eligibility only. They do not establish SQL quality, comparative performance, or final model selection. Seed and anchor verification establish dataset correctness only; they do not establish model-generated SQL quality or an application query service. Metadata verification establishes business-meaning contracts only. Decision/prompt verification establishes envelope validation and deterministic prompt assembly only; they do not call a model or execute SQL. Persistent-build verification establishes artifact construction only. Read-only runtime verification establishes safe open/reconcile/close only; it does not validate, authorize, or execute model-generated SQL.

## Immediate next objective

U2: SQLGlot parsing and static SQL validation producing immutable `ValidatedSql`.

## Subsequent sequence

1. Default-deny SQLite authorizer (U3).
2. Progress budget, result caps, and controlled low-level execution (U4).
3. Integration packaging/docs for the SQL-safety foundation (U5), then provider adapters behind `QueryGenerator`.
4. `QueryService`, deterministic formatting, and terminal-state mapping.
5. CLI and JSON contract.
6. Development evaluation, frozen holdout, and final model selection.

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

SQLGlot static validation / `ValidatedSql`, SQLite authorizer, progress and
result limits, controlled query execution, provider adapters, QueryService,
result formatting, product CLI, integration and safety suites beyond the
runtime open boundary, evaluation cases, evaluation results, and final model
selection.

The physical schema DDL (`apply_schema`), deterministic seed loader
(`load_seed_data`), persistent builder (`build_database`), read-only runtime
factory (`open_readonly_database`), semantic metadata sidecar
(`load_semantic_metadata`), ModelDecision validation
(`parse_model_decision_json`), and deterministic prompt builder
(`build_prompt`) are implemented and test-verified. Generated database files
remain local and untracked. No provider adapter or model-SQL execution path
exists.
