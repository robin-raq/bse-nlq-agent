# Model comparison

This directory contains the bounded live comparison between OpenAI GPT-5 mini
and Groq hosted GPT-OSS 120B. It is evaluation tooling, not product provider
selection. The `bse-nlq` CLI still constructs the existing OpenAI adapter and
still defaults to `gpt-5-mini`.

## Frozen design

Shared across comparison runners:

- Both providers receive the same deterministic application prompt, schema
  metadata, as-of date, and strict `ModelDecision` JSON Schema.
- Each attempt goes through `answer_question`, including local decision
  validation, SQL policy, read-only execution, and rendering.
- The four behavioral cases are scored separately. A behavioral case receives
  two more paired attempts only when the first pair disagrees or differs from
  the expected behavior.
- The synthetic malformed-output case remains in offline reference testing and
  is excluded from live accuracy.
- One unscored warm-up is made per provider. Scored calls are sequential and
  provider order alternates by case and attempt.
- Both SDK clients use a 60 second timeout and zero retries. GPT-5 mini uses the
  Responses API without a temperature parameter. Groq uses its OpenAI
  compatible Chat Completions endpoint with temperature 0. Both request strict
  JSON Schema output.
- Comparative latency uses only answerable case and attempt pairs where both
  providers returned a response. Failed-request latency and provider response
  rate are reported separately, so fast failures cannot look like latency wins.
- Structured-output validity is measured among provider responses. SQL-policy
  acceptance is measured among generated-SQL decisions. Sanitized provider
  failure notes retain only fixed HTTP or connection categories, never provider
  text.

**Attempt schedule differs by runner:**

- Version 1 (`compare_models.py` / `compare_groq_paced.py`): eight answerable
  cases use execution-result invariants and run **three times** per provider.
- Version 2 (`compare_models_v2_paced.py`, authoritative): two fixed base
  passes per answerable case, plus an optional targeted confirmation when the
  base passes disagree or miss the expected outcome.

The case taxonomy and semantic invariant identifiers are frozen in
`manifest.json`. The runner records a source commit, prompt hash, schema hash,
database logical fingerprint, and case-set hash before scored calls begin.

## Runners (historical evidence)

Three near-duplicate scripts record successive comparison stages. Keep all
three; each matches a committed results artifact and is not interchangeable:

| Script | Role | Artifact |
|---|---|---|
| `compare_models.py` | Original paired run (unpaced) | `results/comparison-2026-08-02.*` |
| `compare_groq_paced.py` | Quota-compliant Groq rerun reusing a frozen OpenAI baseline | `results/comparison-2026-08-02-groq-paced.*` |
| `compare_models_v2_paced.py` | Prompt policy v2 paired paced comparison (authoritative for the current default) | `results/comparison-2026-08-03-prompt-v2-paced.*` |

Provider-availability failures (HTTP/connection/`provider_unavailable`) are
reported separately from model-quality evidence (answer correctness, behavior,
SQL-policy acceptance among generated decisions). Fast transport failures must
not be read as latency wins.

## Run

Commit the harness first so the worktree is clean and the source commit is
frozen. Then run from a secret-safe subshell, sourcing the primary checkout's
local environment without copying it. Example for the original runner:

```bash
(
  set -a
  source /path/to/primary/.env
  set +a
  uv run python evaluation/model_comparison/compare_models.py \
    --json-output evaluation/model_comparison/results/comparison-YYYY-MM-DD.json \
    --markdown-output evaluation/model_comparison/results/comparison-YYYY-MM-DD.md
)
```

Use `compare_groq_paced.py` or `compare_models_v2_paced.py` the same way when
reproducing those specific artifacts. Each runner refuses an unclean worktree
or existing output path. It records each attempt immediately in a sanitized
JSON checkpoint. It never stores API keys, provider headers, raw response
objects, request identifiers, reasoning text, exception details, or complete
provider payloads.

The sample is intentionally small. Its strongest positive conclusion is
`recommend_groq_for_review`; it never changes the product default. The
prompt-v2 paced run kept OpenAI.
