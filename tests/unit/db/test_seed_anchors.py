"""Execute all 14 development anchors against the seeded in-memory database."""

from __future__ import annotations

import sqlite3

# A1
A1 = """
SELECT e.name AS event_name, SUM(oi.line_gross_cents) AS gross_revenue_cents
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
JOIN events e ON e.event_id = tt.event_id
GROUP BY e.event_id, e.name
ORDER BY gross_revenue_cents DESC, e.event_id
LIMIT 1
"""

# A2 — published reference SQL with completed-order refund grain
A2 = """
WITH line_refunds AS (
    SELECT r.order_item_id, SUM(r.refund_amount_cents) AS refunded_cents
    FROM refunds r
    JOIN order_items oi ON oi.order_item_id = r.order_item_id
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    GROUP BY r.order_item_id
)
SELECT e.name AS event_name,
       SUM(oi.line_gross_cents) - COALESCE(SUM(lr.refunded_cents), 0)
           AS net_revenue_cents
FROM order_items oi
JOIN orders o         ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt  ON tt.tier_id  = oi.tier_id
JOIN events e         ON e.event_id  = tt.event_id
LEFT JOIN line_refunds lr ON lr.order_item_id = oi.order_item_id
GROUP BY e.event_id, e.name
ORDER BY net_revenue_cents DESC, e.event_id
LIMIT 3
"""

A3 = """
SELECT SUM(oi.line_gross_cents) AS gross_revenue_cents
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
JOIN events e ON e.event_id = tt.event_id
WHERE e.event_date >= '2026-02-01' AND e.event_date < '2026-03-01'
"""

A4 = """
SELECT SUM(oi.line_gross_cents) AS booked_cents
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
WHERE o.purchased_at >= '2026-01-01' AND o.purchased_at < '2026-02-01'
"""

A5 = """
SELECT SUM(oi.quantity) AS tickets_sold
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
JOIN events e ON e.event_id = tt.event_id
JOIN venues v ON v.venue_id = e.venue_id
WHERE v.name = 'Ironworks Music Hall'
"""

A6 = """
WITH line_refunds AS (
    SELECT r.order_item_id, SUM(r.refund_amount_cents) AS refunded_cents
    FROM refunds r
    JOIN order_items oi ON oi.order_item_id = r.order_item_id
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    GROUP BY r.order_item_id
)
SELECT v.name AS venue_name,
       SUM(oi.line_gross_cents) - COALESCE(SUM(lr.refunded_cents), 0)
           AS net_revenue_cents
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
JOIN events e ON e.event_id = tt.event_id
JOIN venues v ON v.venue_id = e.venue_id
LEFT JOIN line_refunds lr ON lr.order_item_id = oi.order_item_id
GROUP BY v.venue_id, v.name
ORDER BY net_revenue_cents DESC, v.venue_id
LIMIT 1
"""

A7 = """
SELECT e.name AS event_name
FROM events e
LEFT JOIN (
    SELECT tt.event_id, SUM(oi.quantity) AS tickets_sold
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
    GROUP BY tt.event_id
) s ON s.event_id = e.event_id
WHERE COALESCE(s.tickets_sold, 0) = 0
ORDER BY e.event_id
"""

A8 = """
SELECT (SUM(oi.line_gross_cents) * 2 + SUM(oi.quantity))
           / (SUM(oi.quantity) * 2) AS avg_ticket_price_cents
FROM order_items oi
JOIN orders o        ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt ON tt.tier_id  = oi.tier_id
JOIN events e        ON e.event_id  = tt.event_id
WHERE e.category = 'hockey'
"""

A9 = """
SELECT e.name AS event_name, SUM(r.refund_amount_cents) AS refunded_cents
FROM refunds r
JOIN order_items oi ON oi.order_item_id = r.order_item_id
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
JOIN events e ON e.event_id = tt.event_id
GROUP BY e.event_id, e.name
ORDER BY refunded_cents DESC, e.event_id
"""

A10 = """
SELECT e.name AS event_name, e.event_date
FROM events e
WHERE e.event_date >= '2026-03-15'
  AND e.status = 'scheduled'
ORDER BY e.event_date, e.event_id
"""

A11 = """
SELECT o.channel,
       SUM(oi.line_gross_cents) AS gross_revenue_cents,
       SUM(oi.quantity) AS tickets_sold
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
GROUP BY o.channel
ORDER BY o.channel
"""

A12 = """
SELECT e.name AS event_name, e.attendance, e.capacity,
       (e.attendance * 10000 * 2 + e.capacity) / (e.capacity * 2)
           AS attendance_rate_bp
FROM events e
WHERE e.attendance IS NOT NULL
ORDER BY attendance_rate_bp DESC, e.event_id
LIMIT 1
"""

A13 = """
SELECT e.name AS event_name
FROM events e
JOIN (
    SELECT tt.event_id, SUM(oi.quantity) AS tickets_sold
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
    GROUP BY tt.event_id
) s ON s.event_id = e.event_id
WHERE s.tickets_sold >= e.capacity
ORDER BY e.event_id
"""

A14 = """
WITH line_refunds AS (
    SELECT r.order_item_id, SUM(r.refunded_qty) AS refunded_qty
    FROM refunds r
    JOIN order_items oi ON oi.order_item_id = r.order_item_id
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    GROUP BY r.order_item_id
),
sold AS (
    SELECT tt.event_id,
           SUM(oi.quantity) AS tickets_sold,
           COALESCE(SUM(lr.refunded_qty), 0) AS refunded_qty
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
    LEFT JOIN line_refunds lr ON lr.order_item_id = oi.order_item_id
    GROUP BY tt.event_id
)
SELECT e.name AS event_name
FROM events e
JOIN sold s ON s.event_id = e.event_id
WHERE (s.tickets_sold - s.refunded_qty) >= e.capacity
ORDER BY e.event_id
"""


def _rows(connection: sqlite3.Connection, sql: str) -> list[tuple]:
    return list(connection.execute(sql))


def _colnames(connection: sqlite3.Connection, sql: str) -> list[str]:
    cursor = connection.execute(sql)
    assert cursor.description is not None
    return [col[0] for col in cursor.description]


def test_a1_highest_gross(seeded_connection: sqlite3.Connection) -> None:
    assert _colnames(seeded_connection, A1) == [
        "event_name",
        "gross_revenue_cents",
    ]
    assert _rows(seeded_connection, A1) == [
        ("Marsh Hollow Family Field Day", 1_700_000)
    ]


def test_a2_top3_net(seeded_connection: sqlite3.Connection) -> None:
    assert _rows(seeded_connection, A2) == [
        ("Marsh Hollow Family Field Day", 1_700_000),
        ("Harbor Kings vs Northshore Tide", 700_000),
        ("Harbor Ice vs Foundry Sevens", 600_000),
    ]


def test_a3_february_event_gross(seeded_connection: sqlite3.Connection) -> None:
    assert _rows(seeded_connection, A3) == [(1_400_000,)]


def test_a4_january_bookings(seeded_connection: sqlite3.Connection) -> None:
    assert _rows(seeded_connection, A4) == [(2_000_000,)]


def test_a5_ironworks_tickets(seeded_connection: sqlite3.Connection) -> None:
    assert _rows(seeded_connection, A5) == [(300,)]


def test_a6_top_venue_net(seeded_connection: sqlite3.Connection) -> None:
    assert _rows(seeded_connection, A6) == [("Kings Harbor Arena", 3_045_000)]


def test_a7_no_sales_events(seeded_connection: sqlite3.Connection) -> None:
    assert _rows(seeded_connection, A7) == [("Ironworks Family Morning",)]


def test_a8_hockey_avg_ticket(seeded_connection: sqlite3.Connection) -> None:
    assert _rows(seeded_connection, A8) == [(7500,)]


def test_a9_refunded_by_event(seeded_connection: sqlite3.Connection) -> None:
    assert _rows(seeded_connection, A9) == [
        ("Tidewater Spring Concert", 500_000),
        ("Ironworks New Year Session", 150_000),
        ("Tidewater Comedy Night", 75_000),
        ("Harbor Kings vs Marsh Hollow Herons", 60_000),
        ("Harbor Kings Preview Showcase", 25_000),
    ]


def test_a10_upcoming(seeded_connection: sqlite3.Connection) -> None:
    assert _rows(seeded_connection, A10) == [
        ("Harbor Comedy Gala", "2026-03-15"),
        ("Harbor Kings Preview Showcase", "2026-04-04"),
        ("Ironworks Family Morning", "2026-05-09"),
        ("Marsh Hollow Summer Concert", "2026-06-20"),
    ]


def test_a11_channel_gross_and_tickets(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert _colnames(seeded_connection, A11) == [
        "channel",
        "gross_revenue_cents",
        "tickets_sold",
    ]
    assert _rows(seeded_connection, A11) == [
        ("box_office", 1_380_000, 180),
        ("mobile_app", 1_790_000, 325),
        ("partner", 1_350_000, 175),
        ("web", 2_750_000, 277),
    ]


def test_a12_best_attendance_rate(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert _rows(seeded_connection, A12) == [
        ("Ironworks New Year Session", 1180, 1200, 9833)
    ]


def test_a13_ever_sold_out(seeded_connection: sqlite3.Connection) -> None:
    assert _rows(seeded_connection, A13) == [("Harbor Kings Preview Showcase",)]


def test_a14_currently_sold_out_empty(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert _rows(seeded_connection, A14) == []
