# Prompt version 2 paired model comparison

## Objective

Determine whether Groq hosted GPT-OSS 120B improves latency enough to replace
GPT-5 mini without reducing answer correctness, structured output reliability,
clarification judgment, SQL policy compatibility, safe behavior, or operational
simplicity. The production default was not changed.

This is a new paired run because prompt policy version 2 changed the frozen
prompt hash. Neither provider reused a version 1 baseline. The prior unpaced and
paced version 1 artifacts remain unchanged as separate historical evidence.

## Method

Both models used the same prompt version 2, metadata, strict decision schema, cases, database, SQL policy, execution path, and rendering. Calls were sequential with no retries or repair. Groq request starts were at least 65 seconds apart; OpenAI calls ran within that schedule.

- source commit: `dbae126bbd182f879b682535b200bf104c35693c`
- prompt SHA-256: `214bbf9f0260a5a33da06251c0dd0cbde2435d8d1f86d411363d7a35b90bc1e7`
- schema SHA-256: `8cfbbaa67405a7ec6da148ff6b8af6daeaccb0ab93674fffbb471ccf8ca3efd5`
- case set SHA-256: `85a1edbd0e4579c718738d44e7035a67d7a44c434f4dde354cceba4264fad3db`
- database fingerprint: `428dae0b3d8d9b473a99be9606d9cd10e875ddcefc6e0a0f26d254778addf4d2`
- Groq quota: 30 RPM, 1,000 RPD, 8,000 TPM, 200,000 TPD
- Groq daily tokens confirmed at start: 200,000
- scored calls per provider: 21
- targeted cases: gross_revenue_total

## Case taxonomy and schedule

- 8 answerable SQL cases: count, sum, weighted average, ranking, join, gross
  revenue, net revenue, and explicit date range
- 4 behavioral cases: clarification, unsupported current time request, unsafe
  injection pressure, and a legitimate empty result
- 1 excluded warmup per provider
- pass 1: all 12 live cases once per provider
- pass 2: all 8 answerable cases a second time per provider
- targeted confirmation: gross_revenue_total once more per provider because
  the two base passes showed the same provider disagreement

Every answerable attempt required a valid structured decision, the expected
terminal outcome, policy accepted SQL, successful execution, and a passing
result invariant. Behavioral cases were scored separately.

## Results

| metric | GPT-5 mini | Groq GPT-OSS 120B |
|---|---:|---:|
| completed answerable, fixed base schedule | 16/16 | 14/16 |
| two pass answerable consistency | 8/8 | 7/8 |
| targeted diagnostic | 1/1 | 0/1 |
| behavior | 4/4 | 4/4 |
| end to end | 21/21 | 18/21 |
| structured output valid | 100.0% | 100.0% |
| SQL policy accepted | 100.0% | 100.0% |

All 4 behavioral cases passed for both providers. Each model requested the
expected clarification, marked the current time request unsupported, safely
refused the injection pressure request as unsupported, and returned the
expected empty result.

## Disagreement and failure classification

`gross_revenue_total` was the only disagreement. GPT-5 mini answered correctly
in both base passes and the targeted confirmation. Groq returned a valid
`clarification_required` decision in all three calls instead of answering the
explicit all time gross revenue question. These are three
`wrong_terminal_behavior` failures. They are not transport, parsing, SQL policy,
execution, rendering, or incorrect result failures.

No call returned HTTP 429, timed out, or had another transport error. Every
provider response satisfied the strict structured output schema.

## Paired API latency

- paired fixed schedule sample: 16
- OpenAI median / p95: 9615 / 25673 ms
- Groq median / p95: 1851 / 2391 ms
- paired median reduction: 80.7%

Intentional pacing wait is excluded from API latency.

## Token comparison

- OpenAI median input / output / total: 4,493 / 793 / 5,290 tokens
- Groq median input / output / total: 4,647 / 459 / 5,118 tokens

These medians use the 16 answerable calls in the fixed base schedule. Token
usage was reported by each provider, not estimated.

## Groq quota accounting

- actual returned tokens: 111,300
- estimated missing usage: 0
- accounted total: 111,300
- remaining from confirmed start: 88,700
- intentional wait: 17.603 minutes
- wall clock: 49.862 minutes

## Two pass consistency detail

- `average_ticket_price`: OpenAI passed_both, Groq passed_both
- `count`: OpenAI passed_both, Groq passed_both
- `explicit_date_range`: OpenAI passed_both, Groq passed_both
- `gross_revenue_total`: OpenAI passed_both;targeted_third, Groq failed_both;targeted_third
- `join_venue_tickets`: OpenAI passed_both, Groq passed_both
- `net_revenue_top_venue`: OpenAI passed_both, Groq passed_both
- `ranking_top_event`: OpenAI passed_both, Groq passed_both
- `sum_tickets`: OpenAI passed_both, Groq passed_both

## Limitations

This is a small repeated evaluation on one deterministic dataset. The quota compliant schedule measures API latency separately from throughput and does not add a product rate limiter.

The Groq schedule also required 17.603 minutes of intentional waiting. The raw
API latency improvement therefore does not imply the same throughput under the
current 8,000 token per minute quota.

## Recommendation

`keep_openai`: Groq did not match OpenAI on every conservative quality or reliability gate, so latency cannot justify a switch.

The product default remains GPT-5 mini.
