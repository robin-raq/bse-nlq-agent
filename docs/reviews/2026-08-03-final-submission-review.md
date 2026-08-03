# Final submission review — 2026-08-03

## Scope and candidate

- Branch: `cursor/final-submission-review` (four commits on `41d963b`:
  `2acf8c5`, `9e55079`, `b79185e`, and this review tip)
- Base: `main` @ `41d963b54455f36272e93bf4e73b848e6569f55f`
- Worktree: `/home/tulle/Development/worktrees/bse-final-submission`
- Comparison tip `77df600` is already an ancestor of main via merge `a7a63eb`
- No second merge of the comparison branch; eight comparison commits preserved
- No live provider calls; no push; primary checkout left at `41d963b` with its pre-existing dirty `AGENTS.md` / `README.md`

Runtime baseline: Python 3.13.14 (`uv` 0.11.28), SQLite 3.53.1.

## Baseline

Offline suite before edits: **1008** tests, green. Ruff, format, mypy, `uv lock --check`, and `git diff --check` passed. Comparison JSON/MD SHA-256 hashes recorded and later re-verified unchanged.

## Findings by severity

### P1 — Unqualified HAVING columns bypassed static authorization

- Evidence: `SELECT COUNT(*) FROM orders HAVING order_ref = 'secret'` validated with empty `referenced_columns`; authorizer denied. Qualified `HAVING o.order_ref = …` already rejected statically.
- Cause: SQLGlot `scope.columns` omits unqualified HAVING refs ([`column_policy.py`](../../src/bse_nlq/sql_policy/column_policy.py)).
- Not a demonstrated data leak (authorizer blocked). Defense-in-depth gap.
- Fix: authorize unqualified HAVING columns only; no broad alternate walker.
- Authorizer→`internal_error` mapping left unchanged as an architecture decision; SQL transparency preserved on that path.

### P2 — Raw OpenAI `APIError` text in `ProviderUnavailableError`

- [`provider_openai.py`](../../src/bse_nlq/provider_openai.py) used `str(error)`.
- Fix: fixed public message `"OpenAI provider request failed"`; offline tests cover exception string and CLI output.

### P2 — CLI labeled Executed SQL but printed `generated_sql`

- Outer whitespace trim means generated ≠ executed.
- Fix: print `executed_sql` under “Executed SQL”; `generated_sql` only when not executed.

### P1/P2 documentation

- `evaluation/results.md` claimed no Groq comparison (false).
- NULLIF/MAX presented as current limitation; evidence is prompt policy v1; PRD Barclays Q3 not re-run under v2.
- Stale suite inventory; D-010/D-011 drift; comparison README conflated v1 three-attempt schedule with v2 two-pass+targeted; holdout wording clarified.
- `docs/layers/` is gitignored local teaching material describing a pre-product codebase; not part of the submission tree (banner skipped as non-tracked).

### P3 deferred

- Leaf-symlink TOCTOU between `lstat` and `connect` (single-user CLI residual risk).
- No actionable local application performance gap found; provider latency dominates.

## Corrections made

1. Unqualified HAVING authorization + unit/e2e regressions.
2. Preserve `generated_sql` / `executed_sql` on unexpected authorizer denial (`internal_error` retained).
3. Sanitize OpenAI provider errors.
4. CLI executed-SQL rendering.
5. Doc reconciliation (results, live results historical framing, README/PROJECT_STATUS/ARCHITECTURE/decisions/comparison README/AI_USAGE/AGENTS).
6. Incorporated local primary WIP into `AGENTS.md` (agent operating rules) and README (transcript removed; extensions wording).

## Conclusions

| Area | Verdict |
|---|---|
| Security | Submission-adequate. Trust boundaries hold; HAVING gap closed statically; authorizer remains defense-in-depth; provider text sanitized. |
| Code quality | Material gaps fixed without scope expansion; no retries/routing/repair added. |
| Performance | No measured local hotspot requiring change. |
| Documentation | Material contradictions reconciled; historical vs current prompt evidence clarified. |

## Validation evidence

```text
uv run pytest -q                 → 1018 passed
uv run ruff check .              → All checks passed
uv run ruff format --check .     → 155 files already formatted
uv run mypy src                  → Success: no issues found in 43 source files
uv lock --check                  → ok
git diff --check                 → clean
comparison artifact SHA-256      → unchanged vs baseline
DEFAULT_MODEL                    → gpt-5-mini
bse-nlq ask without key          → exit 2, clear stderr, no network
Markdown links (touched docs)    → none broken
Secret scan (changed paths)      → clean
Primary checkout                 → still 41d963b; dirty AGENTS.md/README.md preserved
```

## Remaining limitations

- Compact 13-question evaluation; larger holdout out of scope.
- Prompt policy v2 Barclays PRD Q3 not revalidated live (approval required for live calls).
- Narrow SQL function allowlist unchanged by design.
- Synthetic 109-row dataset.
- Unexpected post-validation authorizer denial remains `internal_error` (intentional).
- Leaf-symlink TOCTOU deferred.

## Final verdict

**READY** — submission ready for merge into `main` while preserving comparison commit history (merge or fast-forward; do not squash `af1b09c`…`77df600`).

Not pushed. Not merged.
