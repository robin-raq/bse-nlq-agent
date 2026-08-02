# AI Usage Disclosure

AI tools were used as design and implementation assistants for this take-home project.

## Tools

- Claude Code (Claude Opus), including the Compound Engineering plugin
- ChatGPT
- Cursor (Composer)

## Material assistance

AI assisted with:

- repository setup and project structure;
- comparing architecture options and documenting tradeoffs;
- designing the SQL-safety layers and evaluation approach;
- drafting architecture documentation and diagrams;
- dependency and runtime verification;
- provider smoke-test planning and review;
- test-first implementation of the SQLite physical schema and its contract test suite;
- test-first implementation of the deterministic seed loader, literal transcription from the tracked manifest, invariant/reconciliation/anchor SQL, and analytical trap regressions;
- translating frozen business meaning from `docs/planning/schema-design.md` and `docs/planning/decisions.md` into the structured JSON semantic metadata sidecar and typed load/validate/reconcile API, with schema-reconciliation and leak checks covered by offline tests; and
- translating the frozen ModelDecision contract and prompt architecture into typed validation, deterministic JSON Schema, schema/semantic rendering, and prompt construction, with offline tests for determinism, leakage, malformed output, and injection-boundary delimiting; and
- test-first implementation of the deterministic persistent SQLite builder (`build_database`), including atomic publication, artifact validation, logical fingerprinting, failure cleanup, developer module entry point, and installed-wheel regression coverage; and
- test-first implementation of U2 Slice 1 SQL-policy parsing (`bse_nlq.sql_policy.validate_sql` → immutable `ValidatedSql`), including SQLGlot probes, single-statement enforcement, fingerprinting, ten mutation checks, and installed-wheel import without SQLite execution; and
- test-first implementation of U2 Slice 2 structure policy (allowed SELECT/UNION roots, whole-tree forbidden constructs, recursive-CTE rejection, parameter rejection), including SQLGlot probes, red/green TDD, sixteen mutation checks, and installed-wheel validation without SQLite execution; and
- test-first implementation of U2 Slice 3 physical-table authorization via SQLGlot `scope.sources` / `traverse_scope`, including CTE-shadowing probes, qualifier/TVF probes, SQLite casing probes, red/green TDD, twenty mutation checks, and installed-wheel validation without SQLite execution; and
- test-first implementation of U2 Slice 4A canonical column inventories and internal CTE/derived/Union output-name schemas (single-writer lead plus read-only SQLGlot research, adversarial, and closure-audit agents), including SQLGlot/SQLite probes, red/green TDD, mutation checks, and installed-wheel validation without SQLite execution.
- test-first implementation of U2 Slice 4B qualified physical/internal column binding, lexical qualified correlation, exclusions, canonical physical `referenced_columns`, and `COUNT(*)`-only star policy, including red/green boundary tests and preservation of the pinned SQLGlot `VALUES` rewrite; and
- test-first implementation of U2 Slice 4C unqualified column binding (local-scope, ambiguity-first, no outer climbing) and ORDER BY projection-alias resolution, including updating prior Slice 4A/4B tests whose assertions encoded the now-superseded deferred behavior, and an anchor-compatibility suite proving all 14 executable development anchors pass the complete static validator against the real packaged schema/metadata; and
- test-first implementation of U2 Slice 4D, a type-based SQL function allowlist (`SUM`/`COUNT`/`COALESCE`) that default-denies every machine-clock form, including diagnosing and excluding a SQLGlot-version-specific `And`/`Or`/`Exists` multiple-inheritance quirk that would otherwise have misclassified ordinary boolean connectives and the Slice 4B correlated-subquery predicate as forbidden function calls. This completes the static SQL-safety foundation (Slices 1–4D); and
- test-first implementation of U3, the default-deny SQLite authorizer and controlled execution boundary (`bse_nlq.db.execution`), including diagnosing that SQLite's authorizer-denial exception gives no single reliable structured signal across denial paths (statement-level denial, column/table read denial, and function denial each surface differently) and combining `sqlite_errorcode` with message-text matching to classify them correctly; adversarial tests directly hand-construct malicious `ValidatedSql` (bypassing `validate_sql`) to prove the authorizer independently denies writes, schema changes, PRAGMA, ATTACH, recursive CTEs, and unauthorized tables/columns/functions; and
- test-first implementation of the end-to-end `QueryService` (`bse_nlq.service`), the `bse-nlq ask` CLI (`bse_nlq.cli`), and the one production OpenAI adapter (`bse_nlq.provider_openai`), wiring the project's frozen terminal-state contract (D-007) end to end. The mocked test suite exercises the real database, real SQL policy, and real execution boundary with only the model call faked, covering every terminal state (successful scalar/currency/multi-row answers, empty result, clarification, unsupported, malformed model output, rejected SQL, invalid SQL, execution-limit exceeded, provider-unavailable, and internal-error) plus exactly-one-generation and SQL-transparency assertions; and
- built a compact 13-question evaluation set (`evaluation/`) covering count/sum/average/ranking/join/gross/net/date-range plus one clarification, one unsupported, one unsafe-injection-pressure, one empty-result, and one malformed-output case, with a reference-mode runner that evaluates the real pipeline against hand-authored correct SQL (13/13 passed) and a `--live` mode for real credentials; and
- ran the live smoke test and the full live evaluation against the real OpenAI API. Before sourcing `.env`, key presence was checked with a boolean grep (`grep -q '^OPENAI_API_KEY=.\+' .env`) that never printed the value; the key was then exported only into one command subshell (`set -a && source .env && set +a && uv run ...`) and never echoed, logged, or written to any committed file. The first full-set live pass scored 9/13 blended; investigating the failures found one genuine product defect (a correct, business-rule-compliant `CASE`/`CAST` SQL expression for average ticket price was wrongly rejected as an "unrecognized function" — `exp.Case`/`exp.If`/`exp.Cast` are `Func`-derived in the pinned SQLGlot version, the same bug class already fixed once for `And`/`Or`/`Exists`), fixed narrowly with regression tests; and
- restructured evaluation scoring into three tiers (answerable SQL / behavioral / synthetic fault-injection) instead of one blended score, since a correct clarification and a correct SQL answer are both right answers for different question shapes; found and fixed a second genuine defect this surfaced — the frozen `bare_revenue` ambiguity rule applied unconditionally, so the PRD's own headline example ("top 5 event categories by total revenue") asked for clarification on every run. Fixed with a disclosed-default prompt-policy change (not a weakened rule: `silent_default_forbidden` forbids a *silent* default, and self-documenting column naming like `all_time_gross_ticket_revenue_cents` is not silent), scoped narrowly to explicit ranking/aggregation-by-revenue questions; genuinely open-ended questions are unchanged. Verified offline via `tests/unit/decision/test_prompt_ambiguity_policy.py` (prompt-text assertions, no network) and empirically via a full live rerun. Ran all three literal PRD assignment questions live (not rewritten or dataset-adapted): the revenue-ranking question now answers directly; the "Brooklyn Nets" question correctly asks how to resolve an out-of-dataset entity rather than guessing; the "average ticket price ... Barclays Center" question was safely rejected twice for two different legitimate reasons (`NULLIF` and `MAX()`, both genuine SQLite functions outside the deliberately narrow 3-function allowlist, confirmed via SQLite's own authorizer) — documented as an honest limitation, not expanded, per explicit scope. Final live result: 8/8 answerable + 4/4 behavioral. `evaluation/results_live.md` records the full breakdown, both fixes, and the PRD-question transcripts.

Claude Code also helped prepare the current Python package scaffolding, dependency configuration, and initial validation checks.

## Seed-phase review

For the seed foundation, AI transcribed the frozen literals from
`docs/planning/seed-manifest.md` into typed Python tuples and drafted the
loader and offline tests. An independent review then found and corrected:

- a non-SQLite/`BaseException` rollback gap in `load_seed_data` and the same
  pattern in `apply_schema`;
- an I-8 E11 boundary test that counted cancelled-order tickets;
- refunded-revenue queries that omitted the completed-order base (latent while
  the seed had no cancelled-order refunds); and
- circular literal checks against `seed_data`, replaced with SHA-256
  fingerprints of the production tuples plus retained database oracles.

Human review owned the final contracts, acceptance of exact financial totals,
and confirmation that schema application and seed loading remain separate
operations.

## Metadata-phase review

For the semantic metadata sidecar, AI translated already-frozen business
meaning into structured JSON and a standard-library typed loader. Schema
reconciliation against SQLite introspection and static leak checks were
exercised by offline tests. An independent review then identified and led to
corrections for nested mapping mutability, missing installed-package regression
coverage, weak duplicate-identifier coverage (now duplicate JSON-key rejection),
incomplete prompt-column and join-guidance enforcement, and weak negative
reconciliation tests. No provider request was made and no runtime model prompt
was constructed in this phase. Ambiguity and unsupported policies remain
encoded as explicit clarification/unsupported identifiers with silent defaults
forbidden.

## Decision-and-prompt-phase review

For ModelDecision validation and deterministic prompt construction, AI
translated already-frozen architecture and decision contracts into standard-
library typed models, fail-closed JSON parsing (including duplicate-key
rejection), status invariants, a provider-neutral JSON Schema, and prompt
assembly from SQLite introspection plus semantic metadata. Independent offline
tests cover determinism, seed/secret leakage, malformed and contradictory
model envelopes, question-as-data delimiting, and a one-shot fake-generator
boundary. No live provider call was made and no generated SQL was executed in
this phase. Review-driven corrections included excluding `order_ref` from
model-facing semantic notes, tightening physical-schema heading inventory
checks against H4 collisions, and keeping as-of resolution free of system-clock
reads. A later bounded review also required rejecting reserved question-
delimiter tokens, normalizing metadata reconciliation failures to
`PromptConstructionError`, deduplicating the PROJECT_STATUS backlog, and
restoring libc timezone state after determinism tests.

## Persistent-database-build-phase review

For the persistent SQLite artifact builder, AI implemented
`build_database` as a composition of the approved schema and seed APIs with
destination validation, unique-temporary sibling construction, pre-publication
artifact checks, atomic publication, failure cleanup, logical content
fingerprinting, a narrow `python -m bse_nlq.db.build` developer entry point,
and offline tests including installed-wheel invocation. An independent review
then found and led to corrections for: stale destination `-wal`/`-shm`/`-journal`
replay after overwrite, evidence calculation after publication (failure after
replace), `overwrite=False` check-then-replace races (now atomic no-clobber
`os.link`), and replacement of FIFOs/symlinks/nonregular destinations without
an explicit regular-file contract. Atomic publication, overwrite preservation,
temporary/sidecar cleanup, reproducibility, and packaging behavior were
independently exercised. No read-only runtime connection factory, SQL
parser/validator, authorizer, query executor, provider adapter, live model
request, product CLI, observability, or evaluation path was implemented in this
phase.

## Read-only-runtime-factory-phase review

For the read-only runtime database factory (U1 only), AI implemented
`open_readonly_database` / `ReadOnlyDatabase` test-first: path-to-`mode=ro` URI
opening via `Path.as_uri()`, nonsymlink regular-file guards, exact sibling
`-wal`/`-shm`/`-journal` rejection without suffix-only target bans, literal-`?`
filename support distinct from URI/query strings, `foreign_keys` and
`query_only` verification, semantic metadata load/reconcile before readiness,
immutable physical/visible/excluded column inventories, and idempotent
context-manager close with fail-closed cleanup. An independent review blocked
commit for blanket `?` rejection, missing sibling-sidecar checks, suffix-only
sidecar bans, and weak mutation coverage; those findings were fixed with
regression tests first (literal `?` open, exact sibling rejection, legitimate
`*-wal`/`*-shm`/`*-journal` targets, independent `mode=ro` proof, URI encoding
guards). A closure review then blocked character-based URI classification of
missing ordinary filesystem paths containing `?` or `#`; that path now always
reports missing-file errors while retaining explicit `:memory:` / `file:`
rejects. A final targeted closure review returned APPROVE after verifying path
classification, URI-sensitive filenames, sidecar contracts, independent
`mode=ro`, inventories/wrapper boundary, lifecycle/reconciliation coverage, and
all thirteen required mutations (restored). Validation: `uv run pytest` (full
suite, 505 tests), `ruff check .`, `ruff format --check .`, `mypy src`,
`uv lock --check`, `git diff --check`, and secret-pattern scan. Critical
mutations (URI misclassification, remove `file:` reject, blanket `?` ban,
unsafe URI interpolation, skip sibling rejection, suffix-only ban, remove
`mode=ro`, skip `query_only`/`foreign_keys`, skip reconcile, omit cleanup,
public `execute`, mutable allowlists) were exercised and restored. Docs
(`ARCHITECTURE.md`, `PROJECT_STATUS.md`, `README.md`, `AI_USAGE.md`) were
synced for truthful U1 status without claiming the full SQL-safety foundation.
No SQLGlot policy, authorizer, progress/row/column limits, query execution,
QueryService, provider adapter, CLI, or terminal-state mapping was added in
this slice. No live provider requests were made. U2–U5 remain deferred.

## Read-only-runtime-factory hardening follow-up

An independent repository audit of the committed U1 factory raised five
findings, all addressed test-first in a follow-up pass before U2 began.

Two were public-exception-contract defects: `Path.expanduser()` and filesystem
inspection ran outside the factory's error-normalization boundary, so an
unresolvable `~user` reference escaped as a bare `RuntimeError` and an embedded
NUL as a bare `ValueError`, breaking the documented promise that path
preconditions surface as `DatabaseRuntimeError`. Both were reproduced as red
tests first; while writing them AI found a third unreported variant — a NUL in a
parent component escapes from `Path.resolve()` rather than `lstat()` — which is
now covered. Path construction, expansion, and validation moved inside one
boundary that preserves the original exception as `__cause__` and still lets
`KeyboardInterrupt` / `SystemExit` propagate unwrapped after cleanup.

The third finding was a swallowed close failure: `close()` marked the wrapper
closed before closing the connection and suppressed any error, so a failed
close could report success while the connection and its descriptor stayed open.
It now closes first, sets the flag only on success, raises
`DatabaseRuntimeError` with the cause preserved otherwise, and remains
retryable and idempotent. Close-failure behavior is tested with a narrow stub
connection rather than by forcing a real `sqlite3.Connection.close()` failure.

The fourth finding was three unreachable post-reconciliation checks. Verified
against `reconcile_metadata` (which already rejects any table set other than
the six application tables) and against the metadata parser (which always sets
each column dict key equal to `column.name`, making the visible/excluded
overlap and union checks tautological), they could not detect an independently
reachable failure and were removed. No metadata-layer validation was weakened.
The thirteen mutations recorded for the original U1 phase did not target these
three lines, so that earlier evidence is unaffected; no mutation claim rests on
unreachable code.

The fifth finding was lifecycle ambiguity on `database_path`. Human review
decided to keep it readable after close as immutable identity useful for
diagnostics; that is now an explicit documented contract with a test proving
the path survives close while metadata, inventories, and the package-private
`_connection` still reject use.

Validation: `uv run pytest` (full suite, 512 tests), 61 runtime tests, 350
under `tests/unit/db`, 69 metadata, 92 decision/prompt, plus `ruff check .`,
`ruff format --check .`, `mypy src`, `uv lock --check`, `git diff --check`, and
the tracked-and-untracked secret-pattern scan. Six mutations were exercised and
restored to an identical file digest: expanduser moved back outside the
boundary, `ValueError` no longer caught, close exception swallowed, closed flag
set before the close attempt, cause dropped from the normalized raise, and
`database_path` gated behind an open connection. Each failed its target test.
No SQLGlot validation, `ValidatedSql`, authorizer, progress handler, executor,
QueryService, provider adapter, CLI, observability, or evaluation path was
added; U2–U5 remain deferred and no live provider request was made.

## Read-only-runtime-factory exception-boundary narrowing

An independent review of the U1 hardening pass APPROVEd the work but required
four focused follow-ups before commit. Broad `except Exception` normalization
preserved causes but not behavior: a caller catching `DatabaseRuntimeError`
could treat an internal `AttributeError`, `AssertionError`, or `KeyError` as an
expected bad-database condition. The open boundary now normalizes only the
expected family `OSError | RuntimeError | ValueError | TypeError | sqlite3.Error`
(plus a dedicated `MetadataError` branch), re-raises existing
`DatabaseRuntimeError` unchanged, and leaves programming defects and
`KeyboardInterrupt` / `SystemExit` to propagate after failed-open cleanup.
`MemoryError` is intentionally not normalized. Red tests injected representative
defects before the production change; they failed while the broad catch
remained and passed after narrowing. The unreachable `os.fspath` TypeError /
ValueError guard after the `str | Path` type check was removed. Context-manager
double-failure keeps standard Python chaining (close failure primary; body
failure on the `__context__` chain) without `ExceptionGroup` or custom
suppression. Failed-open cleanup stays best-effort so a secondary close failure
cannot replace the primary open error — unlike explicit `close()`, which reports
close failure. Validation: focused exception-boundary tests (23), full runtime suite (84),
`tests/unit/db` (373), metadata (69), decision (92), full suite (535), plus
`ruff check .`, `ruff format --check .`, `mypy src`, `uv lock --check`,
`git diff --check`, and secret scan. Six mutations
(broad catch, omit `sqlite3.Error`, drop `from error`, wrap instead of
re-raising `DatabaseRuntimeError`, disable cleanup, suppress `__exit__` close
failure) each failed their target tests and were restored. Removing the
dedicated `DatabaseRuntimeError` re-raise alone is a no-op under the narrowed
tuple (that type is not a member), so the identity tests were also exercised
against an explicit wrap mutation. No U2 or later implementation was added.

## Read-only-runtime-factory exception-boundary localization

An independent post-baseline audit of the committed factory plus the
uncommitted narrowing pass above found that the narrowed
`OSError | RuntimeError | ValueError | TypeError | sqlite3.Error` tuple was
still scoped by exception *type* across the entire open sequence rather than
by the specific *operation* that can legitimately raise it. The audit
dynamically injected three defects and confirmed each was silently
reclassified as an ordinary `DatabaseRuntimeError`: a `RuntimeError` from a
metadata/inventory helper (`prompt_visible_columns`), a `TypeError` from the
PRAGMA setup helper (`_enable_and_verify_pragma`), and a `ValueError` from
another metadata/inventory helper (`prompt_excluded_columns`) — while cleanup
still correctly closed the connection in all three cases. This contradicted
the documented contract that programming defects propagate unchanged.

Before changing production code, five red tests were added or corrected in
`tests/unit/db/test_runtime_exception_boundary.py` reproducing the three
audit probes plus a PRAGMA-`TypeError` case, and confirmed to fail against the
unfixed code for the right reason (the exception arrived as
`DatabaseRuntimeError` instead of propagating). A dynamic probe first
established, empirically rather than by inspection alone, exactly where
`sqlite3.Error` can legitimately originate: for a malformed SQLite file,
`sqlite3.connect`, extension-loading, and both `PRAGMA` calls all succeed
(they never touch the file's schema), and the actual `sqlite3.DatabaseError`
only surfaces on the first schema-reading statement inside metadata
reconciliation — so the metadata step needed its own `sqlite3.Error` handling
alongside `MetadataError`, not just the connect/PRAGMA call sites.

Normalization is now three separately localized blocks instead of one
orchestration-wide tuple: `sqlite3.connect` and post-connect SQLite setup
(`_disable_load_extension`, both `_enable_and_verify_pragma` calls) each
normalize only `sqlite3.Error` at their own call sites; the metadata step
normalizes only `MetadataError` and `sqlite3.Error`; path preconditions remain
self-contained inside `_validate_database_path` as before (unchanged by this
pass). The outer function no longer has any catch-all — a `DatabaseRuntimeError`
raised anywhere propagates through the now-bare `finally` cleanup without
being caught or re-wrapped, and a `RuntimeError`/`TypeError`/`ValueError` from
any operation other than the three localized ones now propagates unwrapped.

Three pre-existing tests, beyond the one the audit named, encoded the same
masking as expected behavior by injecting a bare `RuntimeError` as a stand-in
"primary failure" through `_enable_and_verify_pragma`, `_disable_load_extension`,
or `load_semantic_metadata`:
`test_normalized_failures_preserve_cause` (rewritten into
`test_pragma_setup_sqlite_error_normalizes_with_cause` and
`test_pragma_setup_runtime_error_propagates_unchanged`),
`test_failed_pragma_setup_does_not_leak_connection`,
`test_metadata_failure_closes_connection`, and
`test_failed_open_cleanup_preserves_primary_even_if_close_fails`. Each was
corrected to inject a genuine `sqlite3.Error` instead, since a bare
`RuntimeError` from those call sites is a programming defect under the
corrected contract, not a documented failure mode of the helper being
patched; their original cleanup/ordering/identity assertions were preserved
unchanged.

Validation: the 3 target files (44 tests, up from 38), full runtime suite (88,
up from 84), `tests/unit/db` (377, up from 373), metadata (69, unchanged),
decision (92, unchanged), full suite (539, up from 535) — all passing, zero
failures — plus `ruff check .`, `ruff format --check .`, `mypy src`,
`uv lock --check`, `git diff --check`, and the tracked/untracked secret scan,
all clean. Seven mutations (restore the broad orchestration tuple; drop the
local `RuntimeError` handling around `Path.expanduser`; drop the local
`ValueError` handling around parent-resolve/lstat; omit `sqlite3.Error`
around connect/setup; broaden the metadata catch to include `RuntimeError`/
`ValueError`; disable failed-open cleanup; drop `from error` on the two new
localized raises) each failed exactly their target tests and were restored to
an identical file digest (verified by SHA-256 before, after each mutation's
revert, and at the end).

The duplicated `if connection.in_transaction:` guard (~25 lines apart) found
by the same audit was left untouched — deferred, non-blocking, no concrete
benefit to consolidating it in this narrowly scoped pass. No SQLGlot
validation, authorizer, progress handler, executor, `QueryService`, provider
adapter, CLI, observability, or evaluation path was added; U2–U5 remain
deferred and no live provider request was made.

## U2 Slice 1 — SQL-policy parsing foundation

Offline probes against installed SQLGlot **30.14.0** established:

- `sqlglot.parse(sql, read="sqlite")` returns `None` entries for empty
  statements (including `;` / `;;;` and trailing empty semis after a real
  statement);
- empty / whitespace-only inputs parse as `[None]` without raising;
- multi-statement input yields multiple non-`None` expressions;
- `ParseError` (`sqlglot.errors.ParseError`) is raised for true syntax
  failures such as `SELECT FROM` (default error level);
- bare `SELECT` is accepted as a `Select` without raising (root policy is
  Slice 2);
- deterministic render: `expression.sql(dialect="sqlite", comments=False)`
  uppercases keywords, collapses insignificant whitespace, and strips
  comments so comment-bearing and comment-free forms can share a fingerprint
  when SQLGlot removes comments.

Public API decision: package `bse_nlq.sql_policy` with `validate_sql(...) ->
ValidatedSql`, accepting immutable inventory frozensets for later
authorization without coupling to `ReadOnlyDatabase` or opening SQLite.
Immutable model decision: frozen slotted `ValidatedSql` with field
`original_sql` (not `sql`) — outer-trim only; later execution must run
`original_sql`, never `normalized_sql`. Fingerprint is SHA-256 of UTF-8
`normalized_sql`. Slice 1 referenced-object sets are empty frozensets.
Errors: `SqlPolicyError` → `InvalidSqlError` (parse; reason `parse_error`,
cause preserved) / `SqlRejectedError` (policy; reasons `empty_sql`,
`multiple_statements`). Non-string `sql` raises `TypeError` (documented;
no silent `str(...)` coercion). Inventories that are not the expected
frozenset shapes raise `TypeError`.

TDD: red import/model/parsing tests failed with `ImportError` before the
package existed. Ten mutations each failed their target tests and were
restored to matching SHA-256 digests (empty rejection removed; raw parser
list length; permit two statements; semicolon-split instead of SQLGlot;
mutable sets; unfrozen dataclass; fingerprint from `original_sql`;
`original_sql` replaced by normalized; swallow parse cause; export
`_normalize` via `__all__`). Validation: `tests/unit/sql_policy` (32),
metadata (69), runtime (88), decision (92), full suite (571), `ruff check .`,
`ruff format --check .`, `mypy src`, `uv lock --check`, `git diff --check`,
tracked/untracked secret scan clean, wheel build, and installed-wheel probe
of `validate_sql("SELECT 1")` with no SQLite connect. No provider or network
use for validation itself. Deferred: Slice 2–6
root/forbidden/parameter/table/column/star/function/date policy, authorizer,
execution, QueryService, terminal-state mapping.

## U2 Slice 2 — roots, forbidden constructs, recursive CTEs, parameters

Offline probes against installed SQLGlot **30.14.0** established:

- Roots: `Select`; `Union` (`distinct=True` for UNION, `False` for UNION ALL);
  `Intersect`; `Except`; `Values`; parenthesized `(SELECT …)` as `Subquery`
  wrapping `Select`; DML/DDL as typed nodes (`Insert`, `Update`, `Delete`,
  `Create`, `Drop`, `Alter`, `TruncateTable`, `Merge`, `Pragma`, `Attach`,
  `Detach`, `Analyze`, `Transaction`, `Commit`, `Rollback`, `Grant`,
  `Revoke`); `VACUUM` and SQLite `REPLACE INTO` as `Command` fallbacks;
  `SAVEPOINT`/`RELEASE` misparsed as `Alias` roots (still unsupported).
- Nested DML is representable inside CTE bodies (`WITH x AS (INSERT…)` /
  `DELETE…` / `PRAGMA…`) while the outer root remains `Select`.
- Recursive CTEs set `With.args["recursive"] = True`; ordinary CTEs are
  `False`.
- Parameters: `?` and `:name` → `Placeholder`; `@name` → `Parameter`; `$1` /
  `$name` → unquoted `Column`/`Identifier` whose name starts with `$`;
  quoted `"$1"` is a quoted identifier, not a parameter; string literals
  such as `'$1'` / `'?'` / `':value'` / `'DROP TABLE events'` remain
  `Literal` only.

Design: `structure.apply_structure_policy` after Slice 1 single-statement
selection. Allowed roots after unwrapping `Subquery`: `Select` and `Union`
only (covers nonrecursive CTEs and UNION/UNION ALL). Forbidden set is an
explicit tuple of SQLGlot expression classes (not `exp.Replace` string
function). Precedence: unsupported root → forbidden construct → recursive
CTE → parameterized SQL. New rejection reasons:
`unsupported_statement`, `forbidden_construct`, `recursive_cte`,
`parameterized_sql`.

TDD: red suite before implementation recorded **68 failed, 18 passed** on
roots/forbidden/parameters files (accept paths already green from Slice 1;
rejection paths genuinely red). Nested DELETE/PRAGMA CTE cases were added
so mutations that remove those classes from the forbidden set are observable
(root-only DELETE/PRAGMA stay `unsupported_statement` by precedence).
Shared test helper was named `policy_test_helpers.py` after a full-suite
collection collision with `tests/unit/decision/helpers.py` under bare
`from helpers import …`.

Sixteen mutations each failed a targeted test and restored to matching
SHA-256 digests for `structure.py` /
`d6d5347be5872a2c9739bc12947938ac8d71c11dba82c949763bcd4d28b16d82` and
`errors.py` /
`9846bea3ccb2fe5444575e99492e15d144723ef0129cd6c50ed8d19d9bc197b7`:
allow Values/Intersect/Except roots; remove Delete/Pragma from forbidden
(nested CTE tests); root-only forbidden walk; allow recursive CTEs; allow
`?`/`:name`/`@name`/`$1`; reject parameter-like literals; regex parameter
detection; reverse precedence; raise `InvalidSqlError` for unsupported
roots; drop `PARAMETERIZED_SQL` enum member.

Deferred: Slice 3+ table/column/star/function/date authorization, authorizer,
execution, QueryService, terminal-state mapping. No provider or network
calls for this slice validation.

## Post-Slice-2 independent corrective review

Codex performed an independent senior review after commit `10cef029` and found
three confirmed implementation gaps: explicit `ReadOnlyDatabase.close()`
normalized every `Exception`; SQLGlot fallback aliases allowed nested
`SAVEPOINT`/`RELEASE` CTE bodies; and the whole-tree forbidden tests did not
exercise all parser-reachable nested classes. The review also identified the
subset-only `sql_policy.__all__` assertion and unconstrained SQLGlot/Hatchling
declarations. Its claim that cold empty-cache offline construction blocked all
foundation work was treated as overclassified: an unseeded cache cannot supply
an unvendored PEP 517 backend, so the limitation is reported rather than hidden
or solved by vendoring.

Genuine pre-fix red tests showed two close failures (`RuntimeError` and
`MemoryError`) being wrapped as `DatabaseRuntimeError`, and four invalid CTEs
(`SAVEPOINT`, `RELEASE`, `VALUES`, and `INTERSECT`) being accepted. SQLGlot
30.14.0 probes found that `SAVEPOINT y` and `RELEASE y` are CTE-body `Alias`
nodes over `Column` and normalize respectively as `SAVEPOINT AS y` and
`RELEASE AS y`; ordinary `SELECT`, parenthesized `SELECT`, and `UNION` bodies
remain query roots. A `VALUES` CTE is rewritten to a `Select` containing a
`Values` descendant, while `INTERSECT` remains an `Intersect` body.

The correction normalizes only `sqlite3.Error` from explicit close and retains
it as `DatabaseRuntimeError.__cause__`; programming, resource, and control-flow
failures propagate as the same object, leave `closed=False`, and permit retry.
Structure policy now walks every `exp.CTE`, unwraps only `Subquery` root layers,
requires `Select` or `Union`, and rejects the parser's nested `Values` rewrite.
This is AST-only, does not mutate the expression, keeps ordinary projection and
table aliases (including `REPLACE(...) AS ...`), and preserves precedence:
unsupported root, whole-tree forbidden node, invalid CTE body as
`forbidden_construct`, recursive CTE, then parameter.

Parser reachability was classified from real SQL rather than manufactured
nodes. Nested CTE bodies can produce `Insert`, `Update`, `Delete`, `Merge`,
`Create`, `Drop`, `Pragma`, `Attach`, `Detach`, `Command` (`VACUUM`), `Analyze`,
`Transaction`, `Commit`, and `Rollback`; each now has a direct class-specific
whole-tree test. `Alter`, `TruncateTable`, `Grant`, and `Revoke` are produced as
top-level roots but their attempted nested forms fail parsing under this
dialect/version, so their retained tuple entries are defense in depth and
root-policy tests remain the observable protection. SQLite `REPLACE INTO`
falls back to `Command` at the root, while nested forms do not parse. Removing
each reachable class changes its test from the class-specific whole-tree
message to the generic CTE-body rejection; exact `Update` and `Command`
mutations were also run independently.

SQL-policy exports are locked to exactly `InvalidSqlError`, `SqlPolicyError`,
`SqlRejectedError`, `SqlRejectionReason`, `ValidatedSql`, and `validate_sql`.
SQLGlot is pinned to `30.14.0`. Hatchling is pinned to `1.31.0` in both the
build-system declaration and locked dev environment. Normal wheel construction,
cached isolated `--offline`, and synchronized no-build-isolation offline builds
pass. An intentionally empty uv cache correctly
fails isolated offline construction because Hatchling is absent. A clean-venv
offline install of all wheel dependencies also exposed the existing
unconstrained `openai` cache-resolution limitation; the SQL-policy wheel probe
therefore installed the wheel with `--no-deps` plus pinned cached SQLGlot and
proved the requested installed behavior without importing a provider, opening
SQLite, or using the network. Wheel metadata contains
`Requires-Dist: sqlglot==30.14.0`.

Mutations detected broad close catching, missing SQLite normalization, early
`closed=True`, missing explicit cause, disabled CTE validation, allowed Alias /
Values / Intersect bodies, every reachable forbidden-class removal, wrong CTE
reason, global Alias rejection, an extra private export, and removal of the
SQLGlot constraint. An accidental non-underscored helper export passed the old
subset assertion and failed the new equality assertion. Existing parsing tests
reconfirmed normalization and
fingerprint behavior. Final offline validation: 14 context-cleanup tests, 27
runtime exception-boundary tests, 92 runtime tests, 144 SQL-policy tests, 381
database tests, 69 metadata tests, 92 decision/prompt tests, and 689 full-suite
tests; Ruff check/format, strict mypy, lock check, diff check, secret scan,
wheel build/metadata, and installed-wheel SQL-policy probe pass.

The candidate manually reviewed the diff and kept deferred findings out of
scope: deep response-schema freezing, terminal-state removal from decision
errors, QueryRequest/PromptInput naming, prompt/runtime connection bridging,
FIFO/socket portability, stale teaching documentation, full provider
integration, Slice 3 authorization, authorizer, execution, QueryService, CLI,
and evaluation. The locked Slice 3 rules were documented but not implemented.
No provider request was made. Network use in this pass was limited to the
requested `git fetch origin`; dependency/build checks used the synchronized
environment and local uv cache.

## U2 Slice 3 — physical-table authorization via scope.sources

Offline probes against SQLGlot **30.14.0** established:

- Scope construction uses `sqlglot.optimizer.scope.traverse_scope`.
- Authority surface is `scope.sources`: values are either `exp.Table`
  (physical candidate) or nested `Scope` (CTE / derived / Values wrapper).
- Source keys are aliases when present (`events AS e` → key `e`) while the
  physical name remains on `Table.name` / `Table.this`.
- CTE shadowing (`WITH events AS (SELECT 1) SELECT 1 FROM events`) classifies
  the outer source as nested `Scope`; `scope.tables` and
  `expression.find_all(exp.Table)` still report an `events` table node and
  must not authorize.
- Union/Union All emit per-branch Select scopes plus a parent Union scope.
- Qualifiers appear as `Table.args["db"]` / `["catalog"]` Identifier nodes
  (`main.events`, `a.b.c`); unqualified tables leave both `None`.
- `json_each('[1,2]')` parses as `exp.Table` whose `this` is `exp.Anonymous`
  with empty `name` — unsupported table-source kind, not a physical inventory
  match.
- `SELECT 1 FROM (VALUES (1)) AS x` yields a nested Values `Scope` and no
  physical tables.
- SQLite ASCII identifier probes (SQLite 3.46.1) accepted `events` / `EVENTS` /
  `"events"` / `"EVENTS"` against a lowercase `events` table.
- Non-ASCII probes confirmed SQLite does **not** equate `straße`/`strasse`,
  `café`/`CAFÉ`, `Σ`/`σ`, or `İ`/`i`, while ASCII case inside an otherwise
  identical non-ASCII name (`Straße` vs `straße`) does match. Distinct
  `"straße"` and `"strasse"` tables can coexist.

Design: `scope_policy.authorize_physical_tables` after Slice 2 structure
checks. Build a folded→canonical lookup from `physical_tables`. An empty
inventory set is valid; empty or whitespace-padded inventory *entries* and
ASCII-fold collisions raise `TypeError`. Caller-owned frozensets are not
mutated. Traverse every scope once; skip nested `Scope` sources; authorize
identifier `exp.Table` nodes; reject qualified tables (`qualified_table`) and
non-identifier / empty-name tables (`unsupported_table_source`); reject
unknown names (`unknown_table`). Canonical inventory spellings populate
`referenced_tables`. Column inventories remain type-checked only.
`referenced_columns` and `referenced_functions` stay empty.
`original_sql` is never rewritten. The scope-policy pass reads SQLGlot nodes
only and must not mutate the parsed AST; `normalized_sql` / fingerprint stay
independent of canonical authorization.

Identifier folding uses `fold_sqlite_identifier`: ASCII `A`–`Z` → `a`–`z`
only, non-ASCII code points preserved, no Unicode normalization or
`str.casefold()` / `.lower()`.

Rejection precedence (first match wins):

1. unsupported top-level root
2. forbidden whole-tree construct
3. invalid CTE query body
4. recursive CTE
5. parameterized SQL
6. unsupported table-source kind
7. qualified physical table
8. unknown physical table

TDD: red suite recorded **32 failed, 8 passed** before implementation
(empty-FROM and some CTE-shadow/VALUES/literal/precedence paths already green
from Slice 1–2). Existing Slice 1 “unknown tables accepted” test was updated
to assert Slice 3 rejection; two Slice 2 alias tests that query `events` now
pass an inventory.

Mutations restored after focused failures: `find_all(exp.Table)` authority;
`scope.tables` authority; source-key authorization; nested Scope as physical;
skip nested scopes; allow unknown root/CTE/union-branch; strip qualifiers;
case-sensitive matching; SQL spelling instead of canonical; aliases in
`referenced_tables`; CTE names in `referenced_tables`; self-join alias
tagging; accept TVF; populate columns/functions; replace `original_sql`;
mutate AST identifiers; broad `except Exception` around traversal.

Validation: SQL-policy 184, runtime 92, database 381, metadata 69, decision
92, full suite 729; Ruff, format, mypy, lock, diff-check, secret scan, wheel
metadata (`sqlglot==30.14.0`), installed-wheel probe, and supported offline
builds. No provider calls and no SQLite execution in sql_policy. Deferred:
Slice 4 column/star policy, function/date policy, authorizer, execution,
QueryService, CLI, evaluation. Teaching docs under `docs/layers/` and
`docs/learn-site/` remain untracked and untouched.

### U2 Slice 3 closure-review corrections

Independent closure review confirmed three defects (severity labels inflated;
substance real):

1. **ASCII-only folding.** Production had used `str.casefold()`, which
   wrongly authorized `strasse` against inventory `straße` and equated other
   non-ASCII pairs SQLite keeps distinct. Genuine red tests failed before the
   fix. Replaced with `fold_sqlite_identifier` (ASCII A–Z translation only).
2. **AST non-mutation / normalized-SQL isolation.** Scope authorization must
   not rewrite identifiers in place. Added an internal render-before/after
   assertion on `authorize_physical_tables` plus a public
   `normalized_sql`/fingerprint test proving evidence stays the SQLGlot
   rendering of the original parse (`SELECT 1 FROM EVENTS`), while
   `referenced_tables` still returns inventory-canonical `events`.
3. **Empty inventory regression.** Explicit coverage that empty
   `physical_tables` accepts `SELECT 1` and rejects `FROM events`.

Twelve required mutations were applied and restored with focused failures
(casefold, `.lower()`, ß→ss collapse, case-sensitive ASCII, `table.this.set`,
quoted in-place rewrite, remove internal AST assertion with production
mutation, rewritten normalized SQL, rewritten fingerprint, reject empty
inventory, allow tables under empty inventory, SQL spelling instead of
canonical). Source hashes matched afterward.

Validation after corrections: SQL-policy 195, runtime 92, database 381,
metadata 69, decision 92, full suite 740; Ruff, format, mypy, lock,
diff-check, secret scan, wheel metadata (`sqlglot==30.14.0`), installed-wheel
probe outside the checkout, cached isolated `--offline` build, and
`--offline --no-build-isolation` build. No provider calls and no SQLite
execution in sql_policy. No Slice 4 behavior, authorizer, execution,
QueryService, providers, CLI, rendering, or evaluation was added. Nothing was
CLI, rendering, or evaluation was added. Teaching dirs `docs/layers/` and
`docs/learn-site/` remain untracked and untouched. Independent closure
re-review returned APPROVE; this material lands as
`feat: authorize physical SQL table sources`.

### U2 Slice 4A — column inventories and internal output schemas

Multi-agent mode used under a strict single-writer model:

| Agent | Role | Write access |
|---|---|---|
| Lead | production, tests, docs, validation, report | primary checkout only |
| Agent 2 | SQLGlot 30.14.0 / SQLite probes | read-only (scripts under `/tmp`) |
| Agent 3 | adversarial tests / mutations | read-only |
| Agent 4 | independent closure audit | read-only (after lead complete) |

Only the lead modified repository files. Specialists returned evidence; the lead
reproduced SQLGlot/SQLite probes before implementing output schemas.

Pinned: `sqlglot==30.14.0`. Probe SQLite: 3.53.1 (research) / runtime 3.53.1.

Probe findings (temporary scripts under `/tmp/bse-nlq-4a-probes`, not in-repo):

- CTE/derived `named_selects` / `alias_or_name` supply projection output names;
  explicit CTE lists appear as `scope.outer_columns` and override projections.
- Explicit CTE arity mismatch: SQLite `OperationalError`
  (`table x has N values for M columns`); SQLGlot still parses — Slice 4A
  rejects with `invalid_cte_column_list`.
- Duplicate CTE/derived outputs: SQLite renames (`id:1`); policy fails closed
  with `ambiguous_column` (never silently choose first).
- Union output names come from the first Select branch (`named_selects` on the
  parent Union); mismatched branch aliases do not rename; branch arity mismatch
  → SQLite error → Slice 4A `invalid_union_arity`.
- Unnamed expressions (`SELECT id + 1`): SQLGlot `named_selects=[]` /
  empty `alias_or_name`; SQLite exposes expression text — policy omits from
  bindable lookup and marks schema incomplete (does not invent `"id + 1"`).
- Stars inside CTE/derived: `named_selects=['*']`; Strategy A — `is_complete=False`,
  no inventory expansion, no SQLite expansion, no top-level star policy.
- `COUNT(*) AS total` is a named complete output (not projection-star deferral).
- AST render before/after schema extraction is unchanged; no `qualify()` authority.

Genuine red evidence: inventory suite initially failed collection with
`ModuleNotFoundError: column_inventory` before production module existed;
behavior assertions then drove canonicalization/subset/collision contracts.
Output-schema tests were written against probe-backed contracts and integrated
through `validate_sql`.

Implementation:

- `column_inventory.canonicalize_column_inventories` → immutable
  `CanonicalColumnInventory` (`MappingProxyType` / frozensets); TypeError for
  inventory-contract failures (never `SqlRejectedError`).
- `output_schemas.validate_internal_output_schemas` after table auth; reasons
  `ambiguous_column`, `invalid_cte_column_list`, `invalid_union_arity`.
- Public `__all__` unchanged; `referenced_columns` / `referenced_functions`
  remain empty; `orders.order_ref` SQL is not rejected for exclusion yet.

Rejection precedence after Slice 3 table checks:

9. internal output-schema construction (CTE list / Union arity)
10. duplicate internal output → `ambiguous_column`

Mutations (disposable copy `/tmp/bse-nlq-4a-mut`, `PYTHONPATH` isolation):
frozenset/set, whitespace, unknown table, case-sensitive tables, casefold/lower,
collision disable, visible-subset disable, SQL spelling, empty reject,
`find_all` outputs, ignore/truncate explicit CTE lists, keep-first duplicate,
case-sensitive dups, casefold aliases, wrong Union branch, invent unnamed names,
fake star expansion, populate referenced_columns/functions, broad except,
qualify import/call, in-place alias `.set`, original_sql replacement — all
killed by focused tests after isolation fix; no meaningful survivors.

Hardening continuation (same single-writer Cursor lead + fresh Agents 2–4):

- Agent 2 re-probed SQLGlot 30.14.0 / SQLite 3.53.1 and confirmed existing
  contracts; flagged that SQLite silently picks the first duplicate name and
  that `qualify()` mis-assigns names on CTE arity mismatch.
- Agent 3 adversarial review found a real Union false-accept/false-reject:
  `has_star` was computed only from the first branch, and SQLGlot's
  `VALUES → SELECT * FROM (VALUES …)` rewrite made expression-count arity
  unreliable. Lead fixed `_schema_for_union_scope` to scan all branches for
  stars/Values, skip false `invalid_union_arity` when incomplete, and keep
  Strategy A incompleteness. Added permanent tests for non-first-branch
  stars, VALUES unions, explicit CTE list over qualified star, visible
  ASCII collision, inventory-TypeError-before-empty-SQL precedence, and
  `column_inventory` source-scan guards.
- Disposable-copy mutations must use `uv run python3 -m pytest` (not
  `uv run pytest` after `cp -r`, which can re-test the primary checkout via
  shebang).

Validation counts are refreshed in PROJECT_STATUS after the full suite:
column-inventory 44, internal-output 49, physical-table 51, parsing 25,
SQL-policy 288, runtime 92, database 381, metadata 69, decision 92, full 833;
Ruff, format, mypy, lock, diff-check, credential scan, wheel
(`sqlglot==30.14.0`, SHA-256 `387212b1…`), installed-wheel probe outside
checkout (`uv run --python 3.13 --with wheel`), offline `--no-build-isolation`
and cached isolated offline builds. Required Agent-4 mutation set (casefold,
visible-subset remove, unknown table accept, keep-first duplicate, ignore
explicit CTE list including Union-CTE bodies, wrong Union branch, AST alias
`.set`, populate `referenced_columns`, qualify import, broad except) all
killed under `PYTHONPATH` isolation after adding permanent Union+explicit-CTE
tests that closed an Agent-4 coverage gap.
No provider calls and no application SQLite execution in sql_policy.
Nothing staged or committed. Deferred: Slice 4B/4C column binding, exclusions
in SQL, global stars, functions/dates, authorizer, execution, QueryService,
CLI, evaluation. `docs/layers/` and `docs/learn-site/` remain untracked and
untouched.

Independent closure: Agent 4 initially **BLOCK**ed for missing permanent
coverage of explicit CTE lists on Union CTE bodies; lead added four
`cte_union_*` tests that kill the Union-scope ignore-explicit mutation in
isolation. Agent 4 re-audit returned **APPROVE FOR EXTERNAL REVIEW**.

### U2 Slice 4B — qualified columns and star policy

Codex implemented the candidate-reviewed qualified binding contract on the
post-Slice-4A checkpoint. Permanent tests cover local physical and internal
sources, nearest-scope qualified correlation, alias shadowing, no outer fallback
after a qualifier match, unknown qualifier versus unknown column diagnostics,
prompt exclusions, canonical physical references, CTE/derived non-lateral
boundaries, and expression contexts beyond projection. Authored bare and
qualified stars are rejected while `COUNT(*)` and SQLGlot's pinned synthetic
`VALUES` wrapper remain supported. Unqualified binding was implemented in the
following Slice 4C pass. No provider call, SQLite execution, or AST mutation
was introduced. The focused suite is 26 tests; SQL-policy is 318 and the full
offline suite is 867.

### U2 Slice 4C — unqualified columns and ORDER BY aliases

Implemented the candidate-approved local-ambiguity-first contract on the
committed Slice 4B checkpoint. Unqualified references bind only against
sources local to their own scope, sharing the same physical/internal
authorization path as qualified binding so exclusion and unknown-column
diagnostics stay consistent; more than one local candidate is
`ambiguous_column`, zero never climbs to an outer scope. ORDER BY names
matching the enclosing SELECT's own projection alias resolve to that alias
without contributing a physical identity; WHERE/JOIN-ON/GROUP-BY/HAVING alias
support was explicitly excluded as unneeded by the take-home anchors. Several
Slice 4A/4B tests whose assertions encoded the prior "unqualified binding
stays a no-op" behavior were updated with a documented reason rather than
left to fail silently. A new anchor-compatibility suite runs all 14
executable development anchors through `validate_sql` with the real packaged
schema/metadata inventory. The focused suite is 25 tests (plus 14
anchor-compatibility cases); SQL-policy is 342 and the full offline suite is
891.

### U2 Slice 4D — function allowlist and machine-clock rejection

Implemented a type-based (not name-based) function allowlist on the committed
Slice 4C checkpoint: only `exp.Sum`/`exp.Count`/`exp.Coalesce` are permitted,
every other `exp.Func` node is rejected. This uniformly rejects every
machine-clock form without a separate date-argument parser. Implementation
surfaced a real SQLGlot-version quirk mid-pass — `exp.And`/`exp.Or` also
inherit from `exp.Func` in the pinned 30.14.0 release, so a naive walk flagged
ordinary `AND`/`OR` connectives as forbidden function calls, and `exp.Exists`
(load-bearing for the already-committed Slice 4B correlated-subquery tests)
was likewise caught; both are now explicitly excluded from the walk as
non-function syntax, with a comment recording why. One test that used
`REPLACE(...)` purely to prove alias-over-function-expression parsing was
updated to use an allowlisted function instead. The focused suite is 25
tests; SQL-policy is 367 and the full offline suite is 916. This completes
the static SQL-safety foundation (Slices 1–4D); the SQLite authorizer and
controlled execution boundary are next.

## Candidate ownership and review

I made the final design decisions and manually reviewed AI-generated proposals and artifacts. During review, I corrected issues including overly broad safety claims, SQL validation rules that would reject valid aliases and CTEs, unsafe logging defaults, unsupported factual assumptions, and formatting that could overstate result semantics.

The SQLite physical schema, deterministic 109-row seed, JSON semantic metadata sidecar, strict ModelDecision validation, deterministic prompt construction, persistent database builder, read-only runtime database factory, the complete SQL-policy Slices 1–4D, the default-deny SQLite authorizer plus controlled execution boundary (U3), the end-to-end `QueryService`, the `bse-nlq ask` CLI, and the OpenAI adapter are implemented and test-verified — **the full product vertical flow works, verified against both a mocked provider and the real GPT-5 mini model.** A full-scale statistical model-quality evaluation (beyond the 13-question set) and a Groq comparison remain out of scope for this pass. Generated database files remain untracked local artifacts.

Secrets and private exercise materials were not committed. API credentials were used only through ignored local environment configuration and were not printed or persisted.
