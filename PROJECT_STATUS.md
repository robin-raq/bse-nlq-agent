# Project Status

Last updated: 2026-08-02

This is the operational handoff for coding agents. Read it before starting work to understand the verified repository state, the next implementation objective, and active constraints. Architecture authority remains in `docs/planning/decisions.md` and `ARCHITECTURE.md`.

## Current phase

U2 Slice 4D (function allowlist and machine-clock rejection) is implemented
and test-first verified offline on top of the committed `3dc1b45` checkpoint
(Slice 4C). `validate_sql` now authorizes every function call in the tree
against a fixed allowlist (`SUM`, `COUNT`, `COALESCE`) and rejects everything
else — including `CURRENT_DATE`/`CURRENT_TIME`/`CURRENT_TIMESTAMP` and every
`date`/`datetime`/`julianday`/`strftime`/`unixepoch(...)` form — by the same
default-deny path, so no separate date-argument parsing was needed. Allowed
names populate `referenced_functions`. **The complete SQL-safety static
policy (Slices 1-4D) is now implemented**; column authorization, star policy,
and function/date policy are all in place. All 14 executable development
anchors pass. No SQLite authorizer, progress/result limits, controlled
executor, QueryService, provider adapter, live model request for SQL quality,
or product CLI is implemented.

Design artifacts: `docs/planning/schema-design.md` (physical contract), `docs/planning/seed-manifest.md` (exact deterministic literals), `docs/diagrams/schema-erd.md` (ERD), `src/bse_nlq/metadata/schema.json` (semantic sidecar).

No end-to-end application feature path exists yet: a user cannot submit a question through a service/CLI that calls a provider or executes generated SQL. A developer may build a local untracked database file and open it read-only; that is not the product ask path.

**All 14 development anchors have been executed successfully against the real seeded in-memory database.** A13 returns E11 only; A14 returns zero rows. Invariants I-1 through I-8 and the published reconciliations pass against that seed. This does not claim model-generated SQL or application query-execution services have been tested.

## Completed work

- Architecture, trust boundaries, terminal states, and evaluation approach were agreed and documented.
- The project uses a single `src/bse_nlq/` package with a `src/` layout.
- Python and dependency management were configured with `.python-version`, `pyproject.toml`, and `uv.lock`.
- Direct dependencies remain limited to `openai` and SQLGlot; SQLGlot is pinned
  to the reviewed 30.14.0 AST behavior. Development tooling includes pinned
  Hatchling 1.31.0, pytest, pytest-cov, Ruff, and mypy.
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
- U2 Slice 1 SQL-policy parsing foundation was implemented test-first at `src/bse_nlq/sql_policy/`. The public API is `validate_sql(...) -> ValidatedSql`. It trims outer whitespace into `original_sql`, parses with SQLGlot SQLite dialect, requires exactly one meaningful (non-`None`) statement, maps parse failures to `InvalidSqlError` with `__cause__`, rejects empty/semicolon-only and multi-statement input via `SqlRejectedError`, renders deterministic `normalized_sql` (`comments=False`), and fingerprints SHA-256 of UTF-8 normalized SQL. Inventories are accepted as frozensets but not authorized. No SQLite open/execute.
- U2 Slice 2 structure policy was implemented test-first in `src/bse_nlq/sql_policy/structure.py` and wired through `validate_sql`. Allowed roots: `Select` and `Union` (after unwrapping parenthesized `Subquery`). Every CTE body must unwrap to the same query roots; SQLGlot's rewritten `Values` shape is rejected explicitly. Whole-tree forbidden nodes include Insert/Update/Delete/Merge/Create/Drop/Alter/TruncateTable/Pragma/Attach/Detach/Command/Analyze/Transaction/Commit/Rollback/Grant/Revoke. Recursive `With(recursive=True)` is rejected. Parameters via `Placeholder`, `Parameter`, and unquoted `$…` columns are rejected; string literals and quoted `"$1"` identifiers are not. Precedence: unsupported root → forbidden construct (whole-tree nodes, then invalid CTE body) → recursive CTE → parameterized SQL. No table/column authorization, no SQLite open/execute.
- A focused post-Slice-2 audit correction narrowed explicit runtime `close()` normalization to `sqlite3.Error`; programming/resource/control-flow failures propagate unchanged and all failed closes remain open and retryable. The same pass added parser-reachability-driven CTE tests, exact SQL-policy `__all__` coverage, pinned SQLGlot/Hatchling, and locked the Slice 3 design in authoritative documentation.
- U2 Slice 3 physical-table authorization was implemented test-first in `src/bse_nlq/sql_policy/scope_policy.py` and wired through `validate_sql`. Authority is only `scope.sources` via `traverse_scope`: `exp.Table` with an identifier name is authorized against the ASCII-folded inventory (`A`–`Z` only; empty inventory sets allowed); nested `Scope` is skipped as CTE/derived; qualifiers and non-identifier table forms fail closed. Canonical inventory spellings populate `referenced_tables` without mutating the parsed AST or rewriting `normalized_sql`. Closure-review corrections (ASCII fold, AST non-mutation tests, empty-inventory coverage) passed an independent APPROVE re-review; offline suite 740.
- U2 Slice 4A canonical column inventories and internal output-name schemas were implemented test-first in `src/bse_nlq/sql_policy/column_inventory.py` and `output_schemas.py`. Inventories canonicalize through ASCII-only fold against `physical_tables`; visible ⊆ physical; internal CTE/derived/Union schemas detect duplicate folded outputs (`ambiguous_column`) and CTE/Union arity mismatches; star internals remain Strategy A incomplete (including non-first Union branches and SQLGlot `VALUES`→`SELECT *` rewrites); explicit CTE lists over Union bodies are covered.
- U2 Slice 4B qualified-column policy was implemented test-first in `src/bse_nlq/sql_policy/column_policy.py`. It resolves source qualifiers by ASCII fold through the nearest permitted lexical scope, stops at the first matching qualifier, treats aliases as replacing physical table qualifiers, blocks outer fallback after a near match, validates internal outputs without inventing physical pairs, rejects unknown qualifiers/columns and excluded physical columns with distinct reasons, records canonical physical `referenced_columns`, rejects authored stars except `COUNT(*)`, and preserves SQLGlot's synthetic `VALUES` wrapper. CTE/derived bodies do not gain lateral lookup.
- Untrusted parser work is bounded before and after SQLGlot parsing at 16,384 input characters and 512 AST nodes. SQLGlot `RecursionError` is narrowly normalized to `InvalidSqlError` with cause preservation; unrelated programming errors propagate.
- U2 Slice 4C unqualified-column policy was implemented test-first in `src/bse_nlq/sql_policy/column_policy.py` (`authorize_columns`, formerly `authorize_qualified_columns`). An unqualified reference binds only against sources local to its own scope (`scope.sources`): more than one local candidate is `ambiguous_column`; exactly one binds through the same physical/internal authorization as the qualified path (so exclusion and unknown-column reasons stay consistent); zero local candidates is `unknown_column` and never climbs to an outer scope. An unqualified name inside ORDER BY that matches the immediately enclosing SELECT's own projection alias resolves to that alias (SQLite's own precedence) without contributing a physical identity; WHERE, JOIN ON, GROUP BY, and HAVING do not see alias binding. All 14 executable development anchors (`tests/unit/sql_policy/test_anchor_compatibility.py`) pass the complete static validator using the real packaged schema/metadata inventory.
- U2 Slice 4D function/machine-clock policy was implemented test-first in `src/bse_nlq/sql_policy/function_policy.py`. Authorization is type-based, not name-based: only `exp.Sum`/`exp.Count`/`exp.Coalesce` are permitted; every other `exp.Func` node is rejected as `forbidden_function`, which covers every machine-clock form (`CURRENT_DATE`/`CURRENT_TIME`/`CURRENT_TIMESTAMP` and `date`/`datetime`/`julianday`/`strftime`/`unixepoch(...)`) without inspecting `'now'`/`'localtime'`/`'utc'` arguments. `exp.Binary` (this SQLGlot version multiply-inherits `And`/`Or` from both `Binary` and `Func`) and `exp.Exists` (the Slice 4B correlated-subquery predicate) are excluded from the walk as non-function syntax; nested function calls inside them are still checked independently. Allowed names populate `referenced_functions`. All 14 anchors pass.
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
| Read-only runtime factory | `open_readonly_database` returns a ready `ReadOnlyDatabase`; path guards (including literal-`?` filenames vs missing-path classification, exact sibling sidecars, suffix-named mains), `mode=ro` independent of `query_only`, metadata inventories, fail-closed cleanup, and lifecycle contracts covered by 92 offline runtime tests; no public execute surface. Error-contract coverage includes unresolvable `~user` expansion and embedded-NUL paths normalizing to `DatabaseRuntimeError` with preserved cause, exception normalization localized to the specific path/SQLite/metadata operation that can legitimately raise it (so same-type programming defects from unrelated helpers propagate, not just differently-typed ones), SQLite close failures normalized with explicit cause, programming/resource/control-flow close failures propagated unchanged, failed close remaining retryable, and `database_path` readable after close while connection-dependent properties reject use |
| Suite | Decision/prompt-focused tests: 92 under `tests/unit/decision/`; 69 metadata; 367 SQL-policy under `tests/unit/sql_policy/` (Slices 1–4D; 26 focused qualified-column/star cases, 25 unqualified-column/ORDER-BY-alias cases, 14 anchor-compatibility cases, 25 function/machine-clock cases); 385 under `tests/unit/db` (includes persistent-build and runtime coverage; 92 runtime); 916 in the full offline suite; Ruff lint and format; mypy strict; `uv lock --check`; `git diff --check`; credential-pattern scan clean on changed paths. |

| OpenAI | GPT-5 mini accepted the strict four-field decision schema and returned a locally valid response |
| Groq | `openai/gpt-oss-120b` accepted the same schema and returned a locally valid response |
| Secrets | Credentials and the private exercise document remain untracked |

Provider checks establish endpoint eligibility only. They do not establish SQL quality, comparative performance, or final model selection. Seed and anchor verification establish dataset correctness only; they do not establish model-generated SQL quality or an application query service. Metadata verification establishes business-meaning contracts only. Decision/prompt verification establishes envelope validation and deterministic prompt assembly only; they do not call a model or execute SQL. Persistent-build verification establishes artifact construction only. Read-only runtime verification establishes safe open/reconcile/close only; it does not validate, authorize, or execute model-generated SQL.

## Immediate next objective

U3: the default-deny SQLite authorizer and controlled execution boundary —
the security-critical phase that turns `ValidatedSql` into an executed,
row/column-capped result under a progress-handler opcode budget.

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

SQLite authorizer, progress and result limits, controlled query execution,
provider adapters, QueryService, result formatting, product CLI, integration
and safety suites beyond the runtime open boundary and the now-complete
Slice 1–4D SQL-policy foundation, evaluation cases, evaluation results, and
final model selection.

The physical schema DDL (`apply_schema`), deterministic seed loader
(`load_seed_data`), persistent builder (`build_database`), read-only runtime
factory (`open_readonly_database`), semantic metadata sidecar
(`load_semantic_metadata`), ModelDecision validation
(`parse_model_decision_json`), deterministic prompt builder
(`build_prompt`), and the complete SQL-policy Slices 1–4D (`validate_sql` /
`ValidatedSql` with bounded parsing, structure/table policy, canonical column
inventories, internal output schemas, qualified/unqualified column binding
and correlation, ORDER BY projection aliases, exclusions, canonical physical
references, star policy, and a fixed function/machine-clock allowlist) are
implemented and test-verified. All 14 executable development anchors pass the
complete static validator. Generated database files remain local and
untracked. No provider adapter or model-SQL execution path exists.
