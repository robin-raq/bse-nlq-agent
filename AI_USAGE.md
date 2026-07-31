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

## Candidate ownership and review

I made the final design decisions and manually reviewed AI-generated proposals and artifacts. During review, I corrected issues including overly broad safety claims, SQL validation rules that would reject valid aliases and CTEs, unsafe logging defaults, unsupported factual assumptions, and formatting that could overstate result semantics.

The SQLite physical schema, deterministic 109-row seed, JSON semantic metadata sidecar, strict ModelDecision validation, deterministic prompt construction, persistent database builder, and read-only runtime database factory are implemented and test-verified. Generated database files remain untracked local artifacts. No query service, SQL safety validator beyond the runtime open boundary, product CLI, provider integration for SQL quality, or model-quality evaluation is complete yet. Provider smoke tests only verified endpoint access and structured-response compatibility; they do not establish SQL quality or model superiority.

Secrets and private exercise materials were not committed. API credentials were used only through ignored local environment configuration and were not printed or persisted.
