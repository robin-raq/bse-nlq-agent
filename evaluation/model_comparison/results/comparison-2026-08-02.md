# GPT-5 mini and Groq GPT-OSS 120B comparison

## Objective

Compare correctness, safe behavior, structured output reliability, and provider request latency without changing the product default.

## Frozen experiment configuration

- source commit: `feca15fd4061a33194ba1574a49af111e045ad3d`
- Python: `3.13.14`
- uv: `uv 0.11.28 (x86_64-unknown-linux-gnu)`
- prompt SHA-256: `b549ebc7245ded0c1587a6837510a81cf735a8a09c8e8986fd1b2ece62012c2e`
- schema SHA-256: `8cfbbaa67405a7ec6da148ff6b8af6daeaccb0ab93674fffbb471ccf8ca3efd5`
- database logical SHA-256: `428dae0b3d8d9b473a99be9606d9cd10e875ddcefc6e0a0f26d254778addf4d2`
- case set SHA-256: `85a1edbd0e4579c718738d44e7035a67d7a44c434f4dde354cceba4264fad3db`
- one excluded warm-up per provider, one semantic generation per attempt, no retries, no repair
- provider calls were sequential and provider order alternated by case and attempt

## Case taxonomy

Eight answerable SQL cases were each run three times per provider. Four behavioral cases were run once, with two extra attempts only when the first pair disagreed or differed from the expected behavior. The malformed-output fault injection remained offline and did not enter live percentages.

## Aggregate results

| provider | first attempt | stable cases | correct attempts | provider responses | structured valid | policy accepted | behavior |
|---|---:|---:|---:|---:|---:|---:|---:|
| openai | 8/8 | 8/8 | 24/24 | 100.0% | 100.0% | 100.0% | 4/4 |
| groq | 2/8 | 0/8 | 7/24 | 33.3% | 100.0% | 87.5% | 1/4 |

## Per-case disagreements

- `average_ticket_price`: OpenAI `answered:pass`, Groq `query_rejected:fail` (attempt 1 outcomes differed).
- `average_ticket_price`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 2 outcomes differed).
- `average_ticket_price`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 3 outcomes differed).
- `clarification_bare_sales`: OpenAI `clarification_required:pass`, Groq `provider_unavailable:fail` (attempt 1 outcomes differed).
- `count`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 2 outcomes differed).
- `empty_result_currently_sold_out`: OpenAI `answered_empty:pass`, Groq `provider_unavailable:fail` (attempt 1 outcomes differed).
- `empty_result_currently_sold_out`: OpenAI `answered_empty:pass`, Groq `provider_unavailable:fail` (attempt 3 outcomes differed).
- `explicit_date_range`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 1 outcomes differed).
- `explicit_date_range`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 2 outcomes differed).
- `explicit_date_range`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 3 outcomes differed).
- `gross_revenue_total`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 2 outcomes differed).
- `gross_revenue_total`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 3 outcomes differed).
- `join_venue_tickets`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 1 outcomes differed).
- `join_venue_tickets`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 3 outcomes differed).
- `net_revenue_top_venue`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 1 outcomes differed).
- `net_revenue_top_venue`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 3 outcomes differed).
- `ranking_top_event`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 1 outcomes differed).
- `sum_tickets`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 1 outcomes differed).
- `sum_tickets`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 2 outcomes differed).
- `sum_tickets`: OpenAI `answered:pass`, Groq `provider_unavailable:fail` (attempt 3 outcomes differed).
- `unsupported_current_time`: OpenAI `unsupported:pass`, Groq `provider_unavailable:fail` (attempt 1 outcomes differed).
- `unsupported_current_time`: OpenAI `unsupported:pass`, Groq `provider_unavailable:fail` (attempt 2 outcomes differed).
- `unsupported_current_time`: OpenAI `unsupported:pass`, Groq `provider_unavailable:fail` (attempt 3 outcomes differed).

## Failure classification

- groq `sum_tickets` attempt 1: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `average_ticket_price` attempt 1: `sql_policy_rejection` (`sanitized comparison failure`).
- groq `ranking_top_event` attempt 1: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `join_venue_tickets` attempt 1: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `net_revenue_top_venue` attempt 1: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `explicit_date_range` attempt 1: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `clarification_bare_sales` attempt 1: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `unsupported_current_time` attempt 1: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `empty_result_currently_sold_out` attempt 1: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `count` attempt 2: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `sum_tickets` attempt 2: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `sum_tickets` attempt 3: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `average_ticket_price` attempt 2: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `average_ticket_price` attempt 3: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `join_venue_tickets` attempt 3: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `net_revenue_top_venue` attempt 3: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `gross_revenue_total` attempt 2: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `gross_revenue_total` attempt 3: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `explicit_date_range` attempt 2: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `explicit_date_range` attempt 3: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `unsupported_current_time` attempt 2: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `unsupported_current_time` attempt 3: `provider_transport` (`provider_error_http_429_rate_limit`).
- groq `empty_result_currently_sold_out` attempt 3: `provider_transport` (`provider_error_http_429_rate_limit`).

## Latency comparison

| provider | paired responses | median ms | p95 ms | min ms | max ms | failed requests | failed median ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| openai | 8 | 8474 | 24577 | 3324 | 24577 | 0 | None |
| groq | 8 | 1550 | 2659 | 1123 | 2659 | 16 | 288 |

Latency comparisons use only answerable case and attempt pairs where both providers returned a response. Failed request latency is reported separately. The p95 is the nearest-rank sample percentile. Warm-ups are excluded.

## Token comparison

| provider | median input tokens | median output tokens |
|---|---:|---:|
| openai | 4382 | 797 |
| groq | 4534 | 458 |

## Limitations

This is a deliberately small paired experiment on one deterministic dataset and one machine. It supports a review recommendation, not a claim of statistical significance or an automatic product switch. GPT-5 mini Responses omits temperature while Groq uses temperature 0 because the provider controls are not identical.

Groq returned a provider response for only 8/24 answerable attempts; the other
16 were HTTP 429 failures. Its 100% structured-output validity therefore means
8/8 returned answerable responses were schema-valid, not that all 24 requests
succeeded. One of those eight responses generated `NULLIF`, which the unchanged
three-function SQL policy rejected. Comparative latency uses the eight matched
case and attempt pairs where both providers returned a response.

## Recommendation

`keep_openai`: Groq did not match GPT-5 mini on the conservative correctness or reliability gates, so latency cannot justify a switch.

Groq reduced paired median latency from 8,474 ms to 1,550 ms (81.7%), but it
passed only 7/24 answerable attempts, no answerable case was stable across all
three attempts, and it passed 1/4 behavioral cases. GPT-5 mini passed every
answerable attempt and every behavioral case.

The product default remains GPT-5 mini.
