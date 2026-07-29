# Schema and Seed Design

> Approved implementation contract for the physical SQLite schema, deterministic
> seed, and semantic metadata. Frozen 2026-07-29.
>
> Physical DDL is implemented through `apply_schema` in `src/bse_nlq/db/schema.py`.
> Deterministic seed loading is implemented through `load_seed_data` in
> `src/bse_nlq/db/seed.py` (literals in `seed_data.py`). All 14 development
> anchors, I-1 through I-8, and the published reconciliations have been executed
> successfully against the seeded in-memory database. The semantic metadata
> sidecar and persistent application database artifact remain pending.
>
> Rationale and rejected alternatives are not repeated here. `decisions.md` owns
> the decision record; `ARCHITECTURE.md` owns the system contract.

## Scope

Six tables, a deterministic 109-row seed, and a JSON metadata sidecar. Sufficient
to answer join, date, revenue, ambiguity, unsupported, and adversarial questions
through the planned pipeline.

Frozen: table set, column domains, revenue and refund formulas, ticket-count
metrics, attendance model, timestamp convention, unit and rounding rules, seed
totals, and the 14 development anchors.

## Tables and relationships

| Table | Responsibility | PK | FK |
|---|---|---|---|
| `venues` | Location and physical capacity | `venue_id` | — |
| `events` | One occurrence; status, category, capacity, attendance | `event_id` | `venue_id` |
| `ticket_tiers` | Price tier offered for one event | `tier_id` | `event_id` |
| `orders` | Purchase transaction | `order_id` | — |
| `order_items` | Quantity × price paid for one tier | `order_item_id` | `order_id`, `tier_id` |
| `refunds` | Money and tickets returned against one line item | `refund_id` | `order_item_id` |

Revenue path: `order_items → ticket_tiers → events → venues`.

An entity-relationship diagram of these tables is in
[`docs/diagrams/schema-erd.md`](../diagrams/schema-erd.md).

All tables are `STRICT`. Foreign keys use `ON UPDATE RESTRICT ON DELETE RESTRICT`.
`PRAGMA foreign_keys=ON` must be set on the seeding connection.

## Data dictionary

`Meta?` = documented in the metadata sidecar. `Prompt?` = exposed in model schema
context.

### `venues`

| Column | Type | Null | Key | CHECK | Meaning / unit | Meta? | Prompt? |
|---|---|---|---|---|---|---|---|
| `venue_id` | INTEGER | NO | PK | — | Identifier | no | yes |
| `name` | TEXT | NO | UNIQUE | `length(name) > 0` | Venue name | yes | yes |
| `district` | TEXT | NO | — | `length(district) > 0` | District label | yes | yes |
| `capacity` | INTEGER | NO | — | `capacity > 0` | Physical maximum; people | yes | yes |

### `events`

| Column | Type | Null | Key | CHECK | Meaning / unit | Meta? | Prompt? |
|---|---|---|---|---|---|---|---|
| `event_id` | INTEGER | NO | PK | — | Identifier | no | yes |
| `venue_id` | INTEGER | NO | FK→`venues` | — | Host venue | no | yes |
| `name` | TEXT | NO | — | `length(name) > 0` | Event title | yes | yes |
| `category` | TEXT | NO | — | `IN ('basketball','hockey','concert','comedy','family')` | Event type | yes | yes |
| `status` | TEXT | NO | — | `IN ('scheduled','completed','cancelled')` | Lifecycle state | yes | yes |
| `start_local` | TEXT | NO | — | `IS strftime('%Y-%m-%dT%H:%M:%S', start_local)` | Business-local start | yes | yes |
| `event_date` | TEXT | NO | — | GENERATED ALWAYS AS `date(start_local)` STORED | Business calendar date | yes | yes |
| `capacity` | INTEGER | NO | — | `capacity > 0` | Seats released for this event; people | yes | yes |
| `attendance` | INTEGER | YES | — | `attendance IS NULL OR (attendance >= 0 AND attendance <= capacity)` | Turnstile count; people | yes | yes |

Table-level: `CHECK ((status = 'completed') = (attendance IS NOT NULL))` —
attendance is present exactly for completed events.

### `ticket_tiers`

| Column | Type | Null | Key | CHECK | Meaning / unit | Meta? | Prompt? |
|---|---|---|---|---|---|---|---|
| `tier_id` | INTEGER | NO | PK | — | Identifier | no | yes |
| `event_id` | INTEGER | NO | FK→`events` | — | Owning event | no | yes |
| `tier_name` | TEXT | NO | UNIQUE(`event_id`,`tier_name`) | `IN ('premium','reserved','general','pit','lawn','floor_ga','balcony')` | Seating tier | yes | yes |
| `face_value_cents` | INTEGER | NO | — | `face_value_cents > 0` | List price; cents. **Descriptive only — never an input to any revenue metric.** | yes | yes |

### `orders`

| Column | Type | Null | Key | CHECK | Meaning / unit | Meta? | Prompt? |
|---|---|---|---|---|---|---|---|
| `order_id` | INTEGER | NO | PK | — | Identifier | no | yes |
| `order_ref` | TEXT | NO | UNIQUE | `length(order_ref) = 9` | Reference `ORD-NNNNN` | yes | **no** |
| `channel` | TEXT | NO | — | `IN ('web','mobile_app','box_office','partner')` | Sales channel | yes | yes |
| `status` | TEXT | NO | — | `IN ('completed','cancelled')` | Order state | yes | yes |
| `purchased_at` | TEXT | NO | — | `IS strftime('%Y-%m-%dT%H:%M:%S', purchased_at)` | Business-local purchase time | yes | yes |

`order_ref` is excluded from prompt context: display-only, no analytic value.

### `order_items`

| Column | Type | Null | Key | CHECK | Meaning / unit | Meta? | Prompt? |
|---|---|---|---|---|---|---|---|
| `order_item_id` | INTEGER | NO | PK | — | Identifier | no | yes |
| `order_id` | INTEGER | NO | FK→`orders` | — | Parent order | no | yes |
| `tier_id` | INTEGER | NO | FK→`ticket_tiers` | — | Tier purchased | no | yes |
| `quantity` | INTEGER | NO | — | `quantity > 0` | Tickets on this line | yes | yes |
| `unit_price_cents` | INTEGER | NO | — | `unit_price_cents >= 0` | **Actual price paid per ticket; cents. 0 = complimentary. The only price input to revenue.** | yes | yes |
| `line_gross_cents` | INTEGER | NO | — | GENERATED ALWAYS AS `unit_price_cents * quantity` STORED | Line total; cents | yes | yes |

Table-level: `UNIQUE(order_id, tier_id)`.

### `refunds`

| Column | Type | Null | Key | CHECK | Meaning / unit | Meta? | Prompt? |
|---|---|---|---|---|---|---|---|
| `refund_id` | INTEGER | NO | PK | — | Identifier | no | yes |
| `order_item_id` | INTEGER | NO | FK→`order_items` | — | Line refunded | no | yes |
| `refunded_qty` | INTEGER | NO | — | `refunded_qty > 0` | Tickets returned | yes | yes |
| `refund_amount_cents` | INTEGER | NO | — | `refund_amount_cents >= 0` | Money returned; cents | yes | yes |
| `refunded_at` | TEXT | NO | — | `IS strftime('%Y-%m-%dT%H:%M:%S', refunded_at)` | Business-local refund time | yes | yes |
| `reason` | TEXT | NO | — | `IN ('customer_request','event_cancelled','duplicate_purchase')` | Refund reason | yes | yes |

### Date CHECK form — required

There are exactly three explicit timestamp CHECKs — `events.start_local`,
`orders.purchased_at`, and `refunds.refunded_at` — and all three use `IS`,
never `=`. With `=`, `strftime` returns NULL for malformed input, `d = NULL`
evaluates to NULL, and SQLite treats NULL as a passing CHECK — so
`'not-a-date'` is silently accepted. Verified: the `IS` form rejects
`'not-a-date'`, `'2026-02-30'`, `'2026-2-14'`, `''`, and a trailing `Z`.

`events.event_date` is not a fourth CHECK. It is a `GENERATED ALWAYS AS
(date(start_local)) STORED` column derived from the already-validated
`start_local`, so it inherits that column's validity rather than needing an
independent CHECK of its own.

SQLite also *accepts* `date('now')` inside a CHECK. A test must assert the schema
DDL contains no `now`, `CURRENT_DATE`, `CURRENT_TIME`, `CURRENT_TIMESTAMP`, or
`localtime`.

## Indexes

`events(event_date)` · `events(venue_id)` · `events(category)` · `events(status)`
· `ticket_tiers(event_id)` · `order_items(tier_id)` · `order_items(order_id)` ·
`orders(purchased_at)` · `orders(status)` · `refunds(order_item_id)`

At 109 rows these are not a performance measure. They make introspected access
paths match documented query patterns and give the progress-handler budget a
realistic plan to be measured against.

## Business definitions

### Revenue

Ticket fees are **not modeled**; no fee column exists. Revenue is computed from
actual paid price. `face_value_cents` never appears in a revenue expression.

Base for every revenue metric:

```sql
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
```

| Metric | Formula | Unit |
|---|---|---|
| Line gross | `unit_price_cents * quantity` (generated) | cents |
| Gross ticket revenue | `SUM(line_gross_cents)` over the base | cents |
| Refunded amount | `SUM(refund_amount_cents)`, **pre-aggregated per line item before joining** | cents |
| Net ticket revenue | gross − refunded amount | cents |
| Average ticket price | Quantity-weighted actual paid price, rounded to the nearest integer cent | cents_per_item |

Grouping keys: `tt.event_id` (per event), `e.venue_id` (per venue),
`e.category` (per category).

`refunds` is many-per-line-item. Joining it flat alongside `order_items`
multiplies `line_gross_cents` by the refund count. Always pre-aggregate.

### Refunds

Partial and full refunds use one mechanism: a row carrying `refunded_qty` and
`refund_amount_cents`. "Full" means the sums equal the line's quantity and gross.
There is no `is_full` flag. Multiple refunds against one line item are permitted.

### Ticket counts

| Metric | Formula |
|---|---|
| `tickets_sold` | `SUM(quantity)` on completed orders — tickets issued |
| `tickets_net` | `tickets_sold − SUM(refunded_qty)` — tickets retained |

Both are preserved and must be named distinctly wherever either is used.

### Cancellation semantics

| Case | Treatment |
|---|---|
| Cancelled **order** (`orders.status='cancelled'`) | Excluded from every revenue and ticket metric |
| Cancelled **event** (`events.status='cancelled'`) | Counted in gross; refunds reduce net to zero. Gross and net deliberately disagree |

### Attendance

Nullable INTEGER on `events`, present only for completed events, constrained to
`[0, events.capacity]`. Attendance is a turnstile fact, independent of ticket
sales — it is deliberately not derived from line items.

### Capacity

`venues.capacity` is the physical maximum. `events.capacity` is the seats
released for that event and may be lower.

### Dates

| Date | Controls |
|---|---|
| `events.event_date` / `start_local` | Events in a period, upcoming, revenue **for** events in a period |
| `orders.purchased_at` | Sold or booked in a period |
| `refunds.refunded_at` | Refunds issued in a period |

Cancellation time is not modeled; cancellation is a status.

**Timestamps are America/New_York business-local wall-clock time** — events,
purchases, and refunds alike — formatted `YYYY-MM-DDTHH:MM:SS` with no offset.
The term is *business-local*, not venue-local: a web purchase has no venue and a
refund is a back-office action. Storing UTC would push evening events onto the
next calendar date, and SQLite has no IANA timezone database to correct for it.

Default `as_of` = **2026-03-15**. Ranges are half-open, `[start, end)`.
Date-only bounds apply directly to timestamp columns; lexicographic ISO ordering
makes `>= '2026-03-01' AND < '2026-04-01'` correct without `date()` wrapping.

| Phrase | Resolution at `as_of = 2026-03-15` |
|---|---|
| today | `[2026-03-15, 2026-03-16)` |
| this month | `[2026-03-01, 2026-04-01)` |
| last month | `[2026-02-01, 2026-03-01)` |
| this year | `[2026-01-01, 2027-01-01)` |
| last year | `[2025-01-01, 2026-01-01)` |
| **upcoming** | `event_date >= '2026-03-15' AND status = 'scheduled'` |

`upcoming` includes the `as_of` day because `as_of` is a date with no
time-of-day: a strict `>` would drop an event scheduled for tonight that has not
happened yet. The `status` conjunct prevents cancelled events reappearing on date
alone.

### Units and rounding

A closed rule set covering only the divisions the reference queries perform. Not
a general dimensional-analysis system.

| Rule | Statement |
|---|---|
| U-1 | `cents / count` → `cents_per_item` |
| U-2 | `count / count` → dimensionless |
| U-3 | Dimensionless × numeric scale → dimensionless |
| U-4 | A **proven** dimensionless expression with a `_bp` alias may display as basis points |
| U-5 | Any other division → unknown; value returned raw and unformatted |
| U-6 | **An alias never proves a unit.** An unprovable unit stays unknown; a proven unit contradicting its alias is rejected before execution |

Rounding stays in integer arithmetic — result comparison requires exact integer
cents with no float tolerance, so no reference query may introduce a float.
Round-half-up on positive integers is `(2a + b) / (2b)`. Verified exact for
600000/80→7500, 100/3→33, 101/3→34, 300/8→38, 700000/79→8861, 1700000/170→10000.

`AVG(unit_price_cents)` is wrong for average ticket price: it weights line items
rather than tickets.

### Ambiguity policy

Four question shapes are ambiguous by contract. Each must reach
`clarification_required`. **No default may be selected silently**, even when one
reading looks more common.

#### Bare revenue

Unqualified "revenue" or "ticket revenue" is ambiguous between **gross ticket
revenue** and **net ticket revenue after refunds**. The clarification must name
both. Defaulting to either is a defect: on this dataset the two differ by
810,000 cents overall, and for a cancelled event they differ by the entire
amount.

#### Best event

"Best event" requires clarification of the metric — gross revenue, net revenue,
tickets sold, attendance, or attendance rate. **Also request a period when none
is supplied.** The metrics disagree: the top event by gross revenue is not the
top by attendance rate.

#### How are sales doing?

Requires clarification of the **metric**, the **time period**, and — when a trend
judgment is requested — the **comparison or baseline** against which "doing well"
is being assessed. A bare trend question supplies none of the three.

#### Sold out

The bare question "which events sold out?" is ambiguous between:

- **ever reached capacity** — `tickets_sold >= events.capacity`
- **currently at capacity** — `tickets_net >= events.capacity`

The seed makes the readings disagree (see E11 below), so a silent choice is
detectable rather than hidden behind two identical empty results.

### Time-of-day limits on `as_of`

`as_of` is a **date and carries no time of day**. The application therefore
cannot resolve any question that depends on the current moment within that day.

Questions such as "has tonight's show started?", "which events begin after 6 PM
today?", and "what is happening right now?" are **unsupported by the MVP** and
must reach `unsupported_question`.

No midnight or end-of-day convention is invented to make them answerable — any
such convention would produce confidently wrong answers rather than an honest
refusal.

A question that supplies an explicit absolute timestamp and does not depend on
"now" remains answerable, because `start_local` stores full wall-clock time.

## Seed

Row counts: `venues` 4 · `events` 14 · `ticket_tiers` 36 · `orders` 20 ·
`order_items` 28 · `refunds` 7 — **109 rows**. Sized for hand-auditability, since
every evaluation number inherits the seed's correctness.

All names, districts, and figures are invented. No real organization or dataset
is referenced.

The exact deterministic literals — every row of all six tables, including
identifiers, event names, order references, purchase timestamps, and
order-to-line packing — are frozen in
[`seed-manifest.md`](seed-manifest.md). The tables below are the
analytic summary; the manifest is what the seed module must reproduce.

**Paid-price divergence is intentional and limited to two cases.** Actual paid
price differs from tier list price only on the E7 hockey lines, where a
complimentary line (`unit_price_cents = 0` against a 12,000 list price) sits
alongside full-price lines. Those two cases together are the MVP's entire
paid-versus-list divergence surface: they are enough to make substituting
`face_value_cents` for `unit_price_cents` produce a detectably wrong answer
(A8 returns 7,500 correctly and 9,000 incorrectly). No additional discounted line
is introduced, because a third variant would change reconciliation totals without
testing a new failure mode.

### Venues

| id | name | district | capacity |
|---|---|---|---|
| 1 | Kings Harbor Arena | Harbor District | 18,000 |
| 2 | Tidewater Amphitheater | Northshore | 6,000 |
| 3 | Ironworks Music Hall | Ironworks | 1,200 |
| 4 | Marsh Hollow Field | Northshore | 25,000 |

### Events

Gross is over completed orders at actual paid price. `as_of = 2026-03-15`.

| id | venue | category | start_local | status | cap | att. | gross | refunded | net | tickets_sold |
|---|---|---|---|---|---|---|---|---|---|---|
| E1 | Kings Harbor | basketball | 2025-11-08T19:30:00 | completed | 18,000 | 16,420 | 700,000 | 0 | 700,000 | 79 |
| E2 | Kings Harbor | basketball | 2025-12-20T19:00:00 | completed | 18,000 | 17,100 | 600,000 | 60,000 | 540,000 | 70 |
| E3 | Ironworks | concert | 2025-12-31T21:00:00 | completed | 1,200 | 1,180 | 600,000 | 150,000 | 450,000 | 150 |
| E4 | Kings Harbor | concert | 2026-01-17T20:00:00 | completed | **16,000** | 15,200 | 550,000 | 0 | 550,000 | 35 |
| E5 | Tidewater | comedy | 2026-02-14T19:30:00 | completed | 6,000 | 5,200 | 500,000 | 75,000 | 425,000 | 60 |
| E6 | Ironworks | concert | 2026-02-14T20:00:00 | completed | 1,200 | 900 | 300,000 | 0 | 300,000 | 70 |
| E7 | Kings Harbor | hockey | 2026-02-28T18:00:00 | completed | 18,000 | 14,800 | 600,000 | 0 | 600,000 | 80 |
| E8 | Marsh Hollow | family | 2026-03-07T13:00:00 | completed | 25,000 | 21,000 | 1,700,000 | 0 | 1,700,000 | 170 |
| E9 | Ironworks | comedy | 2026-01-24T20:00:00 | completed | 1,200 | 1,050 | 300,000 | 0 | 300,000 | 80 |
| E10 | Tidewater | concert | 2026-04-11T19:00:00 | **cancelled** | 6,000 | NULL | 500,000 | 500,000 | **0** | 60 |
| E11 | Kings Harbor | basketball | 2026-04-04T19:30:00 | scheduled | **33** | NULL | 500,000 | 25,000 | 475,000 | 33 |
| E12 | Ironworks | family | 2026-05-09T11:00:00 | scheduled | 1,200 | NULL | **0** | 0 | **0** | 0 |
| E13 | Marsh Hollow | concert | 2026-06-20T18:00:00 | scheduled | 25,000 | NULL | 240,000 | 0 | 240,000 | 40 |
| E14 | Kings Harbor | comedy | **2026-03-15T20:00:00** | scheduled | 18,000 | NULL | 180,000 | 0 | 180,000 | 30 |
| | | | | | | **TOTAL** | **7,270,000** | **810,000** | **6,460,000** | **957** |

Two events have a capacity below their venue's: **E4** (16,000 of 18,000, reduced
arena configuration) and **E11** (33 of 18,000, limited-capacity basketball
preview showcase — the venue's physical capacity is unchanged).

**E11 is the only event reaching its capacity**, and it separates the two
sold-out readings: `tickets_sold` 33 = capacity 33, while one refunded ticket
leaves `tickets_net` at 32. It remains `scheduled` with `attendance IS NULL`.

Among completed events the highest attendance rate is E3 at 98.33%; none reaches
capacity.

### Line items

`unit ¢` is actual paid price. `list ¢` is the tier's `face_value_cents`, shown
only to make the comp on L17 legible; it never enters a revenue figure.

| L | event | tier | unit ¢ | list ¢ | qty | line gross | order status | channel |
|---|---|---|---|---|---|---|---|---|
| L1 | E1 | premium | 25,000 | 25,000 | 4 | 100,000 | completed | web |
| L2 | E1 | reserved | 12,000 | 12,000 | 25 | 300,000 | completed | web |
| L3 | E1 | general | 6,000 | 6,000 | 50 | 300,000 | completed | web |
| L4 | E2 | reserved | 12,000 | 12,000 | 30 | 360,000 | completed | box_office |
| L5 | E2 | general | 6,000 | 6,000 | 40 | 240,000 | completed | box_office |
| L6 | E3 | floor_ga | 4,500 | 4,500 | 100 | 450,000 | completed | web |
| L7 | E3 | balcony | 3,000 | 3,000 | 50 | 150,000 | completed | mobile_app |
| L8 | E4 | premium | 25,000 | 25,000 | 10 | 250,000 | completed | partner |
| L9 | E4 | reserved | 12,000 | 12,000 | 25 | 300,000 | completed | partner |
| **L10** | E4 | general | 6,000 | 6,000 | 20 | 120,000 | **cancelled** | web |
| L11 | E5 | pit | 15,000 | 15,000 | 20 | 300,000 | completed | web |
| L12 | E5 | lawn | 5,000 | 5,000 | 40 | 200,000 | completed | mobile_app |
| L13 | E6 | floor_ga | 4,500 | 4,500 | 60 | 270,000 | completed | mobile_app |
| L14 | E6 | balcony | 3,000 | 3,000 | 10 | 30,000 | completed | mobile_app |
| L15 | E7 | reserved | 12,000 | 12,000 | 30 | 360,000 | completed | box_office |
| L16 | E7 | general | 6,000 | 6,000 | 40 | 240,000 | completed | box_office |
| **L17** | E7 | reserved | **0** | 12,000 | 10 | 0 | completed | box_office |
| L18 | E8 | premium | 25,000 | 25,000 | 20 | 500,000 | completed | web |
| L19 | E8 | reserved | 12,000 | 12,000 | 50 | 600,000 | completed | web |
| L20 | E8 | general | 6,000 | 6,000 | 100 | 600,000 | completed | mobile_app |
| L21 | E9 | floor_ga | 4,500 | 4,500 | 40 | 180,000 | completed | partner |
| L22 | E9 | balcony | 3,000 | 3,000 | 40 | 120,000 | completed | partner |
| L23 | E10 | pit | 15,000 | 15,000 | 20 | 300,000 | completed | partner |
| L24 | E10 | lawn | 5,000 | 5,000 | 40 | 200,000 | completed | partner |
| L25 | E11 | premium | 25,000 | 25,000 | 8 | 200,000 | completed | web |
| L26 | E11 | reserved | 12,000 | 12,000 | 25 | 300,000 | completed | mobile_app |
| L27 | E13 | general | 6,000 | 6,000 | 40 | 240,000 | completed | mobile_app |
| L28 | E14 | general | 6,000 | 6,000 | 30 | 180,000 | completed | box_office |

### Refunds

| R | line | event | qty | amount ¢ | refunded_at | reason |
|---|---|---|---|---|---|---|
| R1 | L4 | E2 | 5 | 60,000 | 2025-12-28T10:15:00 | customer_request |
| R2 | L7 | E3 | 50 | 150,000 | 2026-01-06T09:00:00 | customer_request |
| R3 | L11 | E5 | 2 | 30,000 | 2026-02-20T14:30:00 | customer_request |
| R4 | L11 | E5 | 3 | 45,000 | 2026-02-24T11:00:00 | duplicate_purchase |
| R5 | L23 | E10 | 20 | 300,000 | 2026-03-02T09:00:00 | event_cancelled |
| R6 | L24 | E10 | 40 | 200,000 | 2026-03-02T09:00:00 | event_cancelled |
| R7 | L25 | E11 | 1 | 25,000 | 2026-03-02T16:45:00 | customer_request |

### Purchase-date constraint

Exactly three orders fall in `[2026-01-01, 2026-02-01)` — L18+L19 (2026-01-10),
L20 (2026-01-22), L21+L22 (2026-01-05) — totalling **2,000,000**. No other order
is purchased in that window.

Every order's `purchased_at` precedes its event's `start_local`; every refund's
`refunded_at` follows its order's `purchased_at`.

### Scenario inventory

| Scenario | Records | Purpose |
|---|---|---|
| Clean baseline, no refunds | E1 | Gross without refund interaction |
| Partial refund | E2 / R1 | Net ≠ gross |
| Full-line refund + year boundary | E3 / R2 | Whole line returned across 2025→2026 |
| Cancelled order excluded | E4 / L10 | Gross 550,000 not 670,000; 35 tickets not 55 |
| Two refunds on one line | E5 / R3, R4 | Breaks naive refund joins |
| Same-day pair | E5 + E6 | Two events on 2026-02-14 |
| Complimentary tickets | E7 / L17 | Paid 0 against 12,000 list |
| Top-revenue event | E8 | Ranking head |
| Revenue tie | E6 = E9 = 300,000 | Tie-aware grading |
| Utilization tie | E2 = E4 = 9,500 bp | Tie-aware grading |
| Cancelled event | E10 / R5, R6 | Gross 500,000, net 0 |
| Future event with sales | E11 / R7 | Advance sales before as_of |
| **Sold-out divergence** | E11 (cap 33) | sold 33 ≥ cap; net 32 < cap |
| No sales at all | E12 | True empty result |
| Far-future advance sales | E13 | Beyond as_of |
| Event on as_of | E14 | Included in "upcoming" |
| Reduced capacity | E4 (16,000 < 18,000) | Event vs venue capacity |
| Limited capacity | E11 (33 < 18,000) | Event vs venue capacity |
| Month and year boundaries | E2→E3→E4 | Period arithmetic |

E10 and E12 are the sharpest pair: E10 has sales and zero net revenue; E12 has no
sales. "Events with **zero net ticket revenue**" returns both; "events with no
sales" returns only E12.

### Reconciliation totals

Assert all three; each independently sums to the gross total.

| Grouping | Values |
|---|---|
| **Overall** | gross 7,270,000 · refunded 810,000 · net 6,460,000 · tickets_sold 957 |
| **By channel** (gross / tickets) | web 2,750,000 / 277 · mobile_app 1,790,000 / 325 · box_office 1,380,000 / 180 · partner 1,350,000 / 175 |
| **By venue** (gross / net) | Kings Harbor 3,130,000 / 3,045,000 · Marsh Hollow 1,940,000 / 1,940,000 · Ironworks 1,200,000 / 1,050,000 · Tidewater 1,000,000 / 425,000 |
| **By category** (gross) | concert 2,190,000 · basketball 1,800,000 · family 1,700,000 · comedy 980,000 · hockey 600,000 |

## Cross-table invariants

SQLite prohibits subqueries in CHECK constraints, so these are enforced in
deterministic seed logic and asserted as post-seed test queries. Each must fail
loudly on a deliberately corrupted fixture.

| # | Invariant |
|---|---|
| I-1 | `SUM(refunds.refund_amount_cents) <= order_items.line_gross_cents` per line |
| I-2 | `SUM(refunds.refunded_qty) <= order_items.quantity` per line |
| I-3 | `events.capacity <= venues.capacity` |
| I-4 | `orders.purchased_at < events.start_local` |
| I-5 | `refunds.refunded_at > orders.purchased_at` |
| I-6 | Cancelled events are fully refunded — exact definition below |
| I-7 | All line items in one order belong to one event |
| I-8 | **`tickets_sold <= events.capacity`** |

### I-6 stated exactly

For **every `order_items` row whose order status is `completed` and whose event
status is `cancelled`**, both equalities must hold:

```
SUM(refunds.refunded_qty)         =  order_items.quantity
SUM(refunds.refund_amount_cents)  =  order_items.line_gross_cents
```

Lines belonging to **cancelled orders are excluded**, because such lines never
contributed to gross revenue or `tickets_sold` and so have nothing to return.

Both equalities are required because the two refund measures are independent
(see below). The quantity equality alone would accept a cancelled event whose
money was never returned; the amount equality alone would accept one whose
tickets were never released.

The rule holds for complimentary tickets without special-casing: a comp line has
positive `quantity` and `line_gross_cents = 0`, so full refund means positive
`refunded_qty` and `refund_amount_cents` summing to **zero**. Zero is the correct
full refund of nothing.

### Refund measures are independent

`refunded_qty` and `refund_amount_cents` measure different things and are
deliberately not tied to one another:

| Measure | Governs |
|---|---|
| `refunds.refunded_qty` | `tickets_net` — how many tickets came back |
| `refunds.refund_amount_cents` | net revenue — how much money went back |

Neither is derived from the other, and **no proportionality between them is
inferred**. A per-ticket refund value is not implied, and an alias resembling one
measure never establishes the other. A returned complimentary ticket is the
clearest case: `refunded_qty` is positive while `refund_amount_cents` is zero,
which is correct and must not be flagged as inconsistent.

`refunded_qty` and `refund_amount_cents` are intentionally independent measures.
No proportionality constraint connects them. Their aggregate upper bounds are
enforced by I-1 and I-2, in addition to the ordinary row-level DDL constraints on
each refund record.

There is no proportional-refund invariant and no I-9.

### I-8 comparison direction

**I-8 must be asserted as `<=`, not `<`.** E11 sits on the equality boundary
(`tickets_sold` 33 = capacity 33); a strict comparison would reject a
legitimately sold-out event. E11 is the regression case for that error.

No triggers. The database is written once by seed code and opened read-only
thereafter, so a trigger could only fire where the seed logic already runs, while
adding schema surface to introspection and prompt context.

`PRAGMA foreign_key_check` plus these eight assertions covers integrity.

## Development anchors

14 anchors. A1–A12 are answerable directly; A13–A14 are answerable only after the
sold-out clarification. Expected values were originally hand-computed from the
seed and are now database-verified: all 14 reference queries execute
successfully against the seeded in-memory database (A13 returns E11 only; A14
returns zero rows).

These are **development** artifacts and must be disjoint from the locked holdout
manifest.

All SQL uses fixed dates, half-open ranges, integer-only arithmetic, meaningful
aliases, and explicit ordering. None uses `CURRENT_DATE`, `date('now')`, or
`localtime`.

| # | Question | Unit | Expected result |
|---|---|---|---|
| A1 | Which event had the highest gross ticket revenue? | cents | E8, 1,700,000 |
| A2 | Top 3 events by net ticket revenue | cents | E8 1,700,000 · E1 700,000 · E7 600,000 |
| A3 | What was **gross** ticket revenue for events in February 2026? | cents | 1,400,000 |
| A4 | How much did we book in January 2026? | cents | 2,000,000 |
| A5 | Tickets sold for events at Ironworks Music Hall | tickets | 300 |
| A6 | Which venue generated the most net revenue? | cents | Kings Harbor Arena, 3,045,000 |
| A7 | Which events sold no tickets? | events | E12 only |
| A8 | Average ticket price for the hockey game | cents_per_item | 7,500 |
| A9 | Total refunded by event | cents | E10 500,000 · E3 150,000 · E5 75,000 · E2 60,000 · E11 25,000 |
| A10 | What events are coming up? | events | E14 · E11 · E12 · E13 (4 rows) |
| A11 | Gross revenue and tickets sold by sales channel | cents + tickets | `gross_revenue_cents` / `tickets_sold`: web 2,750,000 / 277 · mobile_app 1,790,000 / 325 · box_office 1,380,000 / 180 · partner 1,350,000 / 175 |
| A12 | Which event had the best attendance rate? | dimensionless (`_bp`) | E3, 9,833 bp |
| A13 | Which events **ever** sold out? | events | E11 only (1 row) |
| A14 | Which events are **currently** sold out? | events | **Empty result (0 rows)** |

### Anchors requiring specific SQL shapes

**A2, A6 — pre-aggregate refunds.** A direct `JOIN refunds` doubles E5's gross
(two refund rows on L11):

```sql
WITH line_refunds AS (
    SELECT order_item_id, SUM(refund_amount_cents) AS refunded_cents
    FROM refunds GROUP BY order_item_id
)
SELECT e.name AS event_name,
       SUM(oi.line_gross_cents) - COALESCE(SUM(lr.refunded_cents), 0) AS net_revenue_cents
FROM order_items oi
JOIN orders o         ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt  ON tt.tier_id  = oi.tier_id
JOIN events e         ON e.event_id  = tt.event_id
LEFT JOIN line_refunds lr ON lr.order_item_id = oi.order_item_id
GROUP BY e.event_id, e.name
ORDER BY net_revenue_cents DESC, e.event_id
LIMIT 3;
```

**A3 vs A4 — date semantics diverge.** A3 filters `e.event_date`; A4 filters
`o.purchased_at`. February by event date is 1,400,000; January by purchase date
is 2,000,000, against 850,000 by event date. The pair detects date confusion.

**A8 — quantity-weighted, integer-rounded.**

```sql
SELECT (SUM(oi.line_gross_cents) * 2 + SUM(oi.quantity))
           / (SUM(oi.quantity) * 2) AS avg_ticket_price_cents
FROM order_items oi
JOIN orders o        ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt ON tt.tier_id  = oi.tier_id
JOIN events e        ON e.event_id  = tt.event_id
WHERE e.category = 'hockey';
```

Two traps: `AVG(oi.unit_price_cents)` returns 6,000 (weights lines, not tickets);
substituting `tt.face_value_cents` returns 9,000 (prices the comp at list).

**A10 — upcoming includes the as_of day.**

```sql
SELECT e.name AS event_name, e.event_date
FROM events e
WHERE e.event_date >= '2026-03-15'
  AND e.status = 'scheduled'
ORDER BY e.event_date, e.event_id;
```

E14 (2026-03-15) is included; E10 is excluded by status despite its later date.

**A12 — dimensionless via U-2/U-3/U-4.**

```sql
SELECT e.name AS event_name, e.attendance, e.capacity,
       (e.attendance * 10000 * 2 + e.capacity) / (e.capacity * 2) AS attendance_rate_bp
FROM events e
WHERE e.attendance IS NOT NULL
ORDER BY attendance_rate_bp DESC, e.event_id
LIMIT 1;
```

E11 is excluded (`attendance IS NULL`). E2 and E4 tie at 9,500 bp, so a full
ranking needs tie-aware grading.

**A13 / A14 — the sold-out pair.** A13 filters `tickets_sold >= e.capacity`
(returns E11). A14 subtracts pre-aggregated `refunded_qty` and filters
`tickets_net >= e.capacity` (returns nothing). A14's **empty result is the
correct answer**; grading both is what detects a model conflating the readings.

## Metadata sidecar contract

Format: **JSON**, standard-library parsed, canonical serialization with sorted
keys so it hashes deterministically for the evaluation freeze.

Carries meaning only — description, synonyms, unit, status meanings, prompt
visibility, formula references, date semantics, and relationships not obvious
from foreign keys.

Must **not** restate SQLite data types, primary keys, or foreign keys;
introspection owns those. A test asserts every metadata table and column resolves
against introspection and that no key duplicates a schema-owned fact.

Required top-level content:

- `conventions` — timezone, integer cents, half-open ranges, integer rounding
- `formulas` — `gross_ticket_revenue`, `net_ticket_revenue`,
  `average_ticket_price`, `tickets_sold`, `tickets_net`, each with expression,
  unit, and usage notes
- `tables` — per-table and per-column descriptions, synonyms, units, `in_prompt`

Notes that must appear verbatim in effect:

- `face_value_cents` — "Descriptive only. Never used in any revenue metric."
- `unit_price_cents` — "The only price input to revenue."
- `line_gross_cents` — "Already the product of paid price and quantity. DO NOT
  multiply by quantity again."
- `order_ref` — `in_prompt: false`, display-only.

Model-facing distinctions the sidecar must carry, because introspection cannot
express them and a model will otherwise guess wrong:

- **`venues.capacity` is the venue's physical maximum**, across all
  configurations.
- **`events.capacity` is the capacity released for that specific event**, which
  may be far lower.
- **Sold-out calculations use `events.capacity`**, never `venues.capacity`.
- **`ticket_tiers.tier_name` is not globally unique.** It is unique only within
  one event, so the same name recurs across events at different list prices.
- **Grouping by `tier_name` across events combines distinct offerings** and must
  be a deliberate choice, not an accident of the name repeating.

The metadata must also state the ambiguity policy and the time-of-day limit above,
so the model can recognise when to ask rather than answer.

## Known limitations

- Synthetic data and hand-written metadata limit external validity.
- Business-local timestamps are correct for a single-timezone operation only; the
  design is not globally correct.
- `line_gross_cents` reduces but does not eliminate double-multiplication risk; a
  model may still write `SUM(line_gross_cents * quantity)`. Mitigated by metadata
  wording, not by the schema.
- I-1 through I-8 are seed-time and test-time guarantees, not database
  constraints. A hand-edited database could violate them undetected.
- Sold-out cases are ticket-based only. E11 reaches capacity by `tickets_sold`,
  but no completed event's *attendance* reaches its capacity, so a question
  framed as "sold out by turnout" has no positive case.
- Unsupported and adversarial question candidates currently number 3 and 2
  against a ≥4-per-slice holdout gate; more must be authored before the holdout
  is frozen.

## Implementation sequence

1. **Schema DDL** — complete (`apply_schema`).
2. **Seed data module** — complete (frozen literals in `seed_data.py`).
3. **Seed loader** — complete (`load_seed_data`; 109 rows; FK check empty).
4. **Invariant assertions** — complete (I-1…I-8 zero violations on the seed).
5. **Reconciliation tests** — complete (overall, channel, venue, category).
6. **Anchor verification** — complete (A1–A14 executed; A13 = E11 only;
   A14 = empty). Hand-computed expectations are now database-verified.
7. **Metadata sidecar** — pending. JSON per the contract. Test: resolves against
   introspection; restates no schema-owned fact.
8. **Full gate** — Ruff, mypy, pytest, `uv lock --check`, secret scan (rerun
   after each remaining step).
9. **Documentation reconciliation** — update `PROJECT_STATUS.md`; extend
   `decisions.md` only if a decision changes.

A seed producing different totals fails rather than silently redefining truth.
