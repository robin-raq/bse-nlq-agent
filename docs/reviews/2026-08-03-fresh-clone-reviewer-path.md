# Fresh-clone reviewer path check — 2026-08-03

End-to-end verification that the README setup paths work from a clean clone of
`main` @ `f479d83` (post final-submission merge). Live GPT-5 mini calls were
used for the interactive and one-shot CLI paths. Secrets and host paths are
redacted in the snapshots below.

## Verdict

**PASS.** Fast reviewer path (`make dev`), standard one-shot path
(`make ask` / `uv run bse-nlq ask`), offline reference evaluation, missing-key
fail-closed behavior, and the offline pytest suite all behaved as documented.

| Step | Path | Result |
|---|---|---|
| 1 | `git clone` | Tip `f479d83`; no `.env` or `*.db` in tree |
| 2 | Offline `evaluation/run.py` (no key) | 8/8 + 4/4 + 1/1 PASS |
| 3 | `bse-nlq ask` without key | exit `2`, clear stderr, no network attempt |
| 4 | `.env` setup | gitignored; key presence-only |
| 5 | `python -m bse_nlq.db.build` | 109-row DB; gitignored |
| 6 | `make dev` → example 1 → quit | Live answer + Executed SQL; exit `0` |
| 7 | `make ask Q='…top 5…revenue…'` | Same answer shape; exit `0` |
| 8 | `uv run bse-nlq ask` (scheduled events) | `4` + SQL; exit `0` |
| 9 | `uv run pytest -q` | 1018 passed; exit `0` |

Clone used for this check (local only, not committed):
`bse-nlq-agent-fresh-reviewer-check` beside the primary checkout. The clone
`.env` was removed after capture.

---

## 1. Clone

```text
$ git clone https://github.com/robin-raq/bse-nlq-agent.git bse-nlq-agent-fresh-reviewer-check
Cloning into '<clone-root>'...

$ cd bse-nlq-agent-fresh-reviewer-check
$ git rev-parse --short HEAD && git log -1 --oneline
f479d83
f479d83 docs: note multi-domain reuse as a future analytics extension

$ test -f .env && echo present || echo '.env absent (expected)'
.env absent (expected)

$ test -f .env.example && echo '.env.example present'
.env.example present
```

Observed: clean tree with `Makefile`, `README.md`, `src/`, `evaluation/`,
`.env.example`. No committed credentials or database file.

---

## 2. Offline path (no API key)

README: *No API key yet? Run the offline reference demo.*

```text
$ env -u OPENAI_API_KEY uv sync --group dev
Using CPython 3.13.14
Creating virtual environment at: .venv
Resolved 34 packages in 1ms
… (dev dependencies installed) …

$ env -u OPENAI_API_KEY uv run python evaluation/run.py
Evaluation mode: REFERENCE (mocked, pipeline-only)
case                         tier        expected               actual                 pass        ms
count                        answerable  answered               answered               PASS      10.0
sum_tickets                  answerable  answered               answered               PASS       1.6
average_ticket_price         answerable  answered               answered               PASS       1.6
ranking_top_event            answerable  answered               answered               PASS       2.1
join_venue_tickets           answerable  answered               answered               PASS       1.7
net_revenue_top_venue        answerable  answered               answered               PASS       3.1
gross_revenue_total          answerable  answered               answered               PASS       1.2
explicit_date_range          answerable  answered               answered               PASS       1.8
clarification_bare_sales     behavioral  clarification_required clarification_required PASS       0.6
unsupported_current_time     behavioral  unsupported            unsupported            PASS       0.6
unsafe_injection_pressure    behavioral  query_rejected         query_rejected         PASS       0.7
empty_result_currently_sold_out behavioral  answered_empty         answered_empty         PASS       2.9
malformed_model_output       fault_injection invalid_model_output   invalid_model_output   PASS       0.6

Answerable SQL questions: 8/8 passed.
Behavioral cases: 4/4 passed.
Synthetic fault-injection cases: 1/1 passed.
```

---

## 3. Missing-key fail-closed

```text
$ env -u OPENAI_API_KEY uv run bse-nlq ask 'How many events?'
OPENAI_API_KEY is not set. See README.md for setup.
Without a key, you can still run the offline demo: uv run python evaluation/run.py
exit_code=2
```

---

## 4. Env setup (fast-path prerequisite)

```text
$ cp .env.example .env
$ # OPENAI_API_KEY set from local credentials (value not shown)
OPENAI_API_KEY is set (length=<n>, not displayed)

$ git check-ignore -v .env
.gitignore:2:.env	.env
```

---

## 5. Standard path — build database

```text
$ uv run python -m bse_nlq.db.build ./bse_nlq.db
built <clone-root>/bse_nlq.db rows=109 logical_sha256=428dae0b3d8d9b473a99be9606d9cd10e875ddcefc6e0a0f26d254778addf4d2 file_sha256=a1e46a5227539949d0863e9596d22637a3abf64c9956160ae342c5a11e4a3b34

$ ls -lh bse_nlq.db
-rw-r--r-- 1 <user> <user> 92K … bse_nlq.db

$ git check-ignore -v bse_nlq.db
.gitignore:31:*.db	bse_nlq.db
```

---

## 6. Fast reviewer path — `make dev`

Inputs fed to the interactive menu: `1` (top-5 revenue example), then `q`.

```text
$ make dev
uv sync --group dev
Resolved 34 packages in 1ms
Checked 33 packages in 0.35ms
bse_nlq.db already present
Database: bse_nlq.db
Each turn makes one live model call. Press q at the menu to exit.

BSE NLQ — pick an example or type your own

  1. Show me the top 5 event categories by total revenue.
  2. How many events are still scheduled?
  3. How many tickets have been sold in total?
  4. What is the average ticket price?
  5. Which event generated the most revenue?
  6. How many tickets were sold for events at Ironworks Music Hall?
  7. What is our total gross ticket revenue?
  8. How much gross revenue came from events in February 2026?
  0. Type your own question
  q. Quit

Choice:
> Show me the top 5 event categories by total revenue.

category | all_time_gross_ticket_revenue_cents
concert | $21,900.00
basketball | $18,000.00
family | $17,000.00
comedy | $9,800.00
hockey | $6,000.00

Executed SQL:
SELECT
  events.category AS category,
  SUM(order_items.line_gross_cents) AS all_time_gross_ticket_revenue_cents
FROM order_items
JOIN orders ON order_items.order_id = orders.order_id
JOIN ticket_tiers ON order_items.tier_id = ticket_tiers.tier_id
JOIN events ON ticket_tiers.event_id = events.event_id
WHERE orders.status = 'completed'
GROUP BY events.category
ORDER BY all_time_gross_ticket_revenue_cents DESC
LIMIT 5;

BSE NLQ — pick an example or type your own
  … (menu returns) …
Choice:
exit_code=0
```

Notes:

- Live model SQL used qualified table names; answer values match the README /
  live-evaluation top-5 categories and dollar amounts.
- Label is **Executed SQL** (not generated-only), as expected after the
  final-submission CLI fix.

---

## 7. Standard path — `make ask`

```text
$ make ask Q='Show me the top 5 event categories by total revenue.'
uv sync --group dev
Resolved 34 packages in 1ms
Checked 33 packages in 0.35ms
bse_nlq.db already present
category | all_time_gross_ticket_revenue_cents
concert | $21,900.00
basketball | $18,000.00
family | $17,000.00
comedy | $9,800.00
hockey | $6,000.00

Executed SQL:
SELECT
  events.category AS category,
  SUM(order_items.line_gross_cents) AS all_time_gross_ticket_revenue_cents
FROM order_items
JOIN orders ON order_items.order_id = orders.order_id
JOIN ticket_tiers ON order_items.tier_id = ticket_tiers.tier_id
JOIN events ON ticket_tiers.event_id = events.event_id
WHERE orders.status = 'completed'
GROUP BY events.category
ORDER BY all_time_gross_ticket_revenue_cents DESC
LIMIT 5;
exit_code=0
```

---

## 8. Standard path — direct `uv run bse-nlq ask`

```text
$ set -a && source .env && set +a   # key loaded; not printed
$ uv run bse-nlq ask "How many events are still scheduled?"
4

Executed SQL:
SELECT COUNT(*) AS scheduled_events_count
FROM events
WHERE status = 'scheduled'
  AND event_date >= '2026-03-15';
exit_code=0
```

Matches the seeded inventory (14 events; 4 still scheduled as of the frozen
`as_of` date).

---

## 9. Offline test suite (README Testing)

```text
$ uv run pytest -q
........................................................................ [  7%]
… (progress) …
..........                                                               [100%]
exit_code=0
```

**1018** tests collected and passed in the fresh clone environment
(Python 3.13.14 via `uv`).

---

## Expectations vs observed

| Documented expectation | Observed |
|---|---|
| Clone + `make dev` is the fastest reviewer path | Menu, live example 1, quit — exit 0 |
| One-shot `make ask` / `uv run bse-nlq ask` | Exit 0; answer + Executed SQL |
| Offline eval without credentials | 8/8 + 4/4 + 1/1 |
| Missing key fails before network | exit 2 + README pointer |
| DB and `.env` stay untracked | both gitignored |
| Top-5 revenue matches published live result | same five categories and dollar amounts |

## Limitations of this check

- Live model SQL text can vary slightly across calls (aliases/qualification)
  while preserving answer equivalence; both live runs here matched the
  published dollar amounts.
- Only example 1 and one additional scheduled-events question were exercised
  live (not the full 13-case live suite).
- Provider latency is network-bound; not asserted numerically here.

## Cleanup

- Removed the clone’s `.env` after capture.
- Local clone directory may be deleted; it is not part of the git repository.
