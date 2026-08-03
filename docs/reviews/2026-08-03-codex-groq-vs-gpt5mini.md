# Review, codex/groq-vs-gpt5mini, 2026-08-03

**Reviewed by**: GPT 5.6 (author on the GPT 5 family)
**Review independence**: Fresh agent review, model family independence was not established, so this is not a cross family guarantee
**Scope**: 11 files, commits `bfc1331` and `dbae126` plus uncommitted result and documentation artifacts
**Verdict**: Changes requested

## Summary

The prompt policy change is narrow and its contract tests are clear. The paired runner correctly preserves provider order, uses monotonic pacing, and records sanitized evidence. Two conservative experiment gates are not actually enforced, and the result summary omits material evidence required to interpret the failed attempts.

## Major

### 🟠 The recommendation ignores the required p95 latency gate, `evaluation/model_comparison/compare_models_v2_paced.py:468`

**Problem**: The runner computes paired p95 values at lines 433 to 436, but `latency_ok` checks only whether median latency improved by at least 50 percent. A run with a faster median and a worse p95 can therefore return `recommend_groq_for_review`.

**Why it matters**: The frozen conservative rule requires both the median threshold and improved p95 latency. Omitting the tail latency gate can produce a recommendation that contradicts the experiment contract. The current artifact happens to have a better Groq p95, but the reusable scorer is still incorrect.

**Suggested fix**: Require the paired Groq p95 to be lower than the paired OpenAI p95 before recommending Groq. Add focused recommendation tests for a passing case and for a faster median with a worse p95.

### 🟠 The token budget can spend past both stated ceilings, `evaluation/model_comparison/compare_groq_paced.py:122`

**Problem**: `can_start_next` reserves only the greater of the latest observed request size and 6,000 tokens. The next request has no configured output token bound, so its actual usage can exceed that projection. `account` then adds the larger amount without detecting that the 150,000 token evaluation ceiling or the reserved daily headroom was crossed.

**Why it matters**: The version 2 runner imports this budget as its quota guard and reports the limits as enforced maxima. Near either boundary, one larger response can consume the promised reserve or exceed the stated evaluation cap before the runner can stop. Existing tests use fixed 6,000 token calls and do not exercise an underestimate.

**Suggested fix**: Reserve a true per request upper bound before each Groq call, with provider output limited to that bound, then reconcile actual usage afterward. Add a test where the next actual call is larger than the recent projection and prove neither ceiling can be crossed.

## Minor

### 🟡 The standalone report hides the primary failure classification, `evaluation/model_comparison/results/comparison-2026-08-03-prompt-v2-paced.md:17`

**Problem**: The aggregate shows Groq at 14 of 17 completed answerable attempts, and the stable detail only says `failed_both;targeted_third`. It does not state that all three failures were `wrong_terminal_behavior` clarifications, list the paired disagreements, or provide the comparative token medians already computed by the runner.

**Why it matters**: A reviewer cannot determine from the committed Markdown evidence whether the gap was incorrect SQL, policy rejection, execution failure, or clarification judgment. This weakens the report as a concise standalone experiment record and leaves required failure and disagreement evidence discoverable only by manually mining the JSON attempts.

**Suggested fix**: Add compact disagreement and failure classification sections, plus the OpenAI and Groq median token comparison, generated from the sanitized attempt data.

## Strengths

* Prompt policy version 2 names the exact SQL function inventory and supplies policy compatible integer arithmetic without weakening SQL validation.
* The paired schedule uses one pacer for all Groq starts, alternates provider order, freezes prompt, schema, case, and database hashes before live calls, and preserves sanitized checkpoints.

## Test coverage

The prompt contract, base schedule, targeted selection, pacing interval, no retry behavior, and ordinary token accounting have focused offline tests. The new metric and recommendation branches have no direct tests, which allowed the missing p95 gate. The quota tests also cover only calls whose actual size equals the projection, so they do not verify the claimed hard ceiling under usage variance.

## Closure

Both major findings are resolved. The recommendation now enforces improved paired p95 latency, and the quota guard reserves 8,000 tokens per Groq call with an explicit overage check and regression coverage. The report finding is also resolved through separate targeted diagnostic reporting, failure classification, and comparative token evidence. No new blocker was found.

**Final verdict**: Approve
