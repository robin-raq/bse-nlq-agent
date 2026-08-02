# Quota-compliant Groq GPT-OSS 120B rerun

## Why this rerun was necessary

The original bursty run produced 22 HTTP 429 responses. This separate run preserves that evidence while measuring model quality and provider reliability under the supplied Groq token limits.

## Frozen inputs and pacing

- prompt SHA-256: `b549ebc7245ded0c1587a6837510a81cf735a8a09c8e8986fd1b2ece62012c2e`
- schema SHA-256: `8cfbbaa67405a7ec6da148ff6b8af6daeaccb0ab93674fffbb471ccf8ca3efd5`
- case set SHA-256: `85a1edbd0e4579c718738d44e7035a67d7a44c434f4dde354cceba4264fad3db`
- hashes matched the prior result; the OpenAI baseline was reused
- Groq limits: 30 RPM, 1,000 RPD, 8,000 TPM, 200,000 TPD
- requests were sequential with at least 65 seconds between starts
- one request per attempt, no retries, failover, repair, or prompt changes
- calls: 1 warm-up, 21 scored, 1 targeted, 22 total

## Token budget

- user-confirmed daily capacity at start: 200,000
- actual tokens returned by Groq: 110,166
- estimated tokens for missing usage: 0
- accounted total: 110,166
- maximum local evaluation budget: 150,000
- reserved headroom: 20,000

## Results

- completed-generation answerable accuracy: 16/17
- stable answerable cases: 7/8
- structured-output validity: 100.0%
- SQL-policy acceptance: 94.1%
- end-to-end provider success: 20/21
- HTTP 429 / timeout / other transport: 0 / 0 / 0
- behavioral passes: 4/4

## Stable-case and behavioral detail

- `average_ticket_price`: inconsistent_across_attempts;targeted_third_attempt
- `count`: passed_both_scheduled_attempts
- `explicit_date_range`: passed_both_scheduled_attempts
- `gross_revenue_total`: passed_both_scheduled_attempts
- `join_venue_tickets`: passed_both_scheduled_attempts
- `net_revenue_top_venue`: passed_both_scheduled_attempts
- `ranking_top_event`: passed_both_scheduled_attempts
- `sum_tickets`: passed_both_scheduled_attempts
- `clarification_bare_sales`: attempt 1 clarification_required (pass)
- `empty_result_currently_sold_out`: attempt 1 answered_empty (pass)
- `unsafe_injection_pressure`: attempt 1 unsupported (pass)
- `unsupported_current_time`: attempt 1 unsupported (pass)

## Latency and elapsed time

- completed answerable API calls: 17
- median / p95 API latency: 1871 / 2579 ms
- minimum / maximum API latency: 1103 / 2579 ms
- total intentional pacing: 22.054 minutes
- total wall-clock experiment: 30.575 minutes
- monotonic active elapsed time: 22.792 minutes

Intentional pacing is excluded from API latency. The raw API latency does not represent throughput for repeated CLI requests at this quota. The wall-clock and monotonic elapsed totals diverged during one inter-request gap; both are retained as separate observations.

## Comparison

| metric | GPT-5 mini baseline | original unpaced Groq | paced Groq |
|---|---:|---:|---:|
| answerable | 24/24 | 7/24 scheduled | 16/17 completed |
| stable cases | 8/8 | 0/8 | 7/8 |
| behavior | 4/4 | 1/4 | 4/4 |
| median API latency | 8474 ms | 1550 ms | 1871 ms |
| p95 API latency | 24577 ms | 2659 ms | 2579 ms |

The unpaced 7/24 result includes provider-unavailable attempts. The paced completed-generation denominator includes only valid structured ModelDecision responses; end-to-end success above retains every call.

## Limitations

This is a small evaluation on one deterministic dataset. The supplied quota required a long inter-request schedule, safe reset metadata was not exposed, and no production rate limiter was added.

## Recommendation

`keep_openai`: Groq matched the behavioral and paced-provider reliability gates, but did not match the frozen GPT-5 mini completed-generation accuracy, stable-case, or SQL-policy compatibility gates.

The product default remains GPT-5 mini.
