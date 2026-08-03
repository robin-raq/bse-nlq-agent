# Evaluation Results

Run with `uv run python evaluation/run.py`. See `evaluation/cases.py` for the
13 question definitions and `evaluation/run.py` for the harness.

## What this evaluates

**This is a reference-SQL (mocked) run, not a live model-quality
evaluation.** Each case supplies hand-authored SQL representing a *correct*
response to its question; a fake generator returns that SQL verbatim instead
of calling a real model. This proves the downstream pipeline — SQL policy,
the SQLite authorizer/execution boundary, rendering, and terminal-state
mapping — behaves correctly across a representative spread of question
shapes and outcomes. **It does not evaluate the model's own ability to write
correct SQL from an English question**, since no model was called.

A live run (`--live`) sends each question to the real OpenAI adapter and
scores the model's actual answer instead. It requires `OPENAI_API_KEY` and
network access. **A live run has since been recorded — see
[`evaluation/results_live.md`](results_live.md) (8/8 answerable, 4/4
behavioral; GPT-5 mini)**, kept as a separate document from this
reference-mode run rather than mixed into it. Latency in the table below is
not meaningful — it is local SQLite execution time against a mocked model
call, not real model response time; see the live results document for real
latency figures.

## Result: 8/8 answerable + 4/4 behavioral + 1/1 fault-injection (reference mode)

Cases are grouped into three tiers (see `evaluation/results_live.md` for the
full rationale): answerable SQL questions measure NLQ accuracy; behavioral
cases measure whether the outcome was safe/acceptable, not whether SQL was
generated; the one fault-injection case (malformed model output) is only
meaningfully testable in this reference mode, since a well-behaved live
model cannot be made to emit malformed JSON on demand.

### Answerable SQL questions: 8/8

| case | category | expected | actual | pass |
|---|---|---|---|---|
| count | count | answered | answered | PASS |
| sum_tickets | sum | answered | answered | PASS |
| average_ticket_price | average | answered | answered | PASS |
| ranking_top_event | ranking | answered | answered | PASS |
| join_venue_tickets | join | answered | answered | PASS |
| net_revenue_top_venue | net_revenue | answered | answered | PASS |
| gross_revenue_total | gross_revenue | answered | answered | PASS |
| explicit_date_range | date_range | answered | answered | PASS |

### Behavioral cases: 4/4

| case | category | expected | actual | pass |
|---|---|---|---|---|
| clarification_bare_sales | clarification | clarification_required | clarification_required | PASS |
| unsupported_current_time | unsupported | unsupported | unsupported | PASS |
| unsafe_injection_pressure | unsafe | query_rejected | query_rejected | PASS |
| empty_result_currently_sold_out | empty_result | answered_empty | answered_empty | PASS |

### Synthetic fault-injection case: 1/1 (reference mode only)

| case | category | expected | actual | pass |
|---|---|---|---|---|
| malformed_model_output | malformed_output | invalid_model_output | invalid_model_output | PASS |

Each `answered` case also passed its `expected_answer_contains` substring
check against the rendered text (e.g. `ranking_top_event` rendered
"Marsh Hollow Family Field Day"; `gross_revenue_total` rendered
"$72,700.00"), confirming rendering correctness, not just terminal-state
correctness. The reference values were computed by executing each case's SQL
directly against the seeded database and cross-checked against the
published reconciliation totals in `PROJECT_STATUS.md` (gross 7,270,000,
net 6,460,000, tickets_sold 957) where they overlap.

## Known limitations

- 13 cases is a small, hand-picked set, not a statistically powered sample.
- The reference-mode run does not exercise the model's SQL-generation
  quality at all; it exercises everything downstream of that.
- `unsafe_injection_pressure` proves the *static/authorizer* safety net
  rejects a destructive statement even if a model were tricked into
  producing one — it does not evaluate whether a real model would actually
  be tricked into producing it. In live mode, `unsupported`,
  `query_rejected`, and `invalid_sql` are all accepted safe outcomes for
  this case — refusing outright is at least as safe as generating-then-rejecting.
- A live OpenAI vs Groq comparison was later recorded under
  `evaluation/model_comparison/` (authoritative prompt policy v2 report:
  `results/comparison-2026-08-03-prompt-v2-paced.md`, recommendation
  `keep_openai`). This reference-mode document remains the offline pipeline
  check only; see `evaluation/results_live.md` for the GPT-5 mini live run.
