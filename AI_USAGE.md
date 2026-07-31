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
- test-first implementation of the deterministic persistent SQLite builder (`build_database`), including atomic publication, artifact validation, logical fingerprinting, failure cleanup, developer module entry point, and installed-wheel regression coverage.

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

## Candidate ownership and review

I made the final design decisions and manually reviewed AI-generated proposals and artifacts. During review, I corrected issues including overly broad safety claims, SQL validation rules that would reject valid aliases and CTEs, unsafe logging defaults, unsupported factual assumptions, and formatting that could overstate result semantics.

The SQLite physical schema, deterministic 109-row seed, JSON semantic metadata sidecar, strict ModelDecision validation, deterministic prompt construction, persistent database builder, and read-only runtime database factory are implemented and test-verified. Generated database files remain untracked local artifacts. No query service, SQL safety validator beyond the runtime open boundary, product CLI, provider integration for SQL quality, or model-quality evaluation is complete yet. Provider smoke tests only verified endpoint access and structured-response compatibility; they do not establish SQL quality or model superiority.

Secrets and private exercise materials were not committed. API credentials were used only through ignored local environment configuration and were not printed or persisted.
