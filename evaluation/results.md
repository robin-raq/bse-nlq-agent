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
network access — both unavailable in the sandbox this run was produced in,
so a live result could not be recorded here. Latency is only meaningful for
a live run; the sub-5ms figures below are local SQLite execution time, not
model response time.

## Result: 13/13 passed (reference mode)

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
| clarification_bare_sales | clarification | clarification_required | clarification_required | PASS |
| unsupported_current_time | unsupported | unsupported | unsupported | PASS |
| unsafe_injection_pressure | unsafe | query_rejected | query_rejected | PASS |
| empty_result_currently_sold_out | empty_result | answered_empty | answered_empty | PASS |
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
  be tricked into producing it.
- No live model comparison (OpenAI vs. Groq) was performed; that was
  explicitly out of scope for this pass, and blocked here regardless by
  missing credentials and network access.
