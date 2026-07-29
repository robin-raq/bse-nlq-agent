"""Cross-table invariant queries I-1 through I-8 against the seeded database."""

from __future__ import annotations

import sqlite3

# Each query returns violating rows; an empty result means the invariant holds.

I1_VIOLATIONS = """
SELECT oi.order_item_id
FROM order_items oi
LEFT JOIN (
    SELECT order_item_id, SUM(refund_amount_cents) AS refunded_cents
    FROM refunds
    GROUP BY order_item_id
) r ON r.order_item_id = oi.order_item_id
WHERE COALESCE(r.refunded_cents, 0) > oi.line_gross_cents
"""

I2_VIOLATIONS = """
SELECT oi.order_item_id
FROM order_items oi
LEFT JOIN (
    SELECT order_item_id, SUM(refunded_qty) AS refunded_qty
    FROM refunds
    GROUP BY order_item_id
) r ON r.order_item_id = oi.order_item_id
WHERE COALESCE(r.refunded_qty, 0) > oi.quantity
"""

I3_VIOLATIONS = """
SELECT e.event_id
FROM events e
JOIN venues v ON v.venue_id = e.venue_id
WHERE e.capacity > v.capacity
"""

I4_VIOLATIONS = """
SELECT DISTINCT o.order_id, e.event_id
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
JOIN events e ON e.event_id = tt.event_id
WHERE o.purchased_at >= e.start_local
"""

I5_VIOLATIONS = """
SELECT r.refund_id
FROM refunds r
JOIN order_items oi ON oi.order_item_id = r.order_item_id
JOIN orders o ON o.order_id = oi.order_id
WHERE r.refunded_at <= o.purchased_at
"""

I6_VIOLATIONS = """
SELECT oi.order_item_id
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
JOIN events e ON e.event_id = tt.event_id AND e.status = 'cancelled'
LEFT JOIN (
    SELECT order_item_id,
           SUM(refunded_qty) AS refunded_qty,
           SUM(refund_amount_cents) AS refunded_cents
    FROM refunds
    GROUP BY order_item_id
) r ON r.order_item_id = oi.order_item_id
WHERE COALESCE(r.refunded_qty, 0) != oi.quantity
   OR COALESCE(r.refunded_cents, 0) != oi.line_gross_cents
"""

I7_VIOLATIONS = """
SELECT oi.order_id
FROM order_items oi
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
GROUP BY oi.order_id
HAVING COUNT(DISTINCT tt.event_id) != 1
"""

I8_VIOLATIONS = """
SELECT e.event_id
FROM events e
LEFT JOIN (
    SELECT tt.event_id, SUM(oi.quantity) AS tickets_sold
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
    GROUP BY tt.event_id
) s ON s.event_id = e.event_id
WHERE COALESCE(s.tickets_sold, 0) > e.capacity
"""


def _violations(connection: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    connection.row_factory = sqlite3.Row
    return list(connection.execute(sql))


def test_i1_refund_amount_within_line_gross(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert _violations(seeded_connection, I1_VIOLATIONS) == []


def test_i2_refund_qty_within_line_quantity(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert _violations(seeded_connection, I2_VIOLATIONS) == []


def test_i3_event_capacity_within_venue(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert _violations(seeded_connection, I3_VIOLATIONS) == []


def test_i4_purchase_before_event_start(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert _violations(seeded_connection, I4_VIOLATIONS) == []


def test_i5_refund_after_purchase(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert _violations(seeded_connection, I5_VIOLATIONS) == []


def test_i6_cancelled_event_fully_refunded(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert _violations(seeded_connection, I6_VIOLATIONS) == []


def test_i7_order_items_single_event(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert _violations(seeded_connection, I7_VIOLATIONS) == []


def test_i8_tickets_sold_within_capacity(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert _violations(seeded_connection, I8_VIOLATIONS) == []


def test_i8_e11_equality_boundary(
    seeded_connection: sqlite3.Connection,
) -> None:
    row = seeded_connection.execute(
        """
        SELECT e.capacity, COALESCE(s.tickets_sold, 0) AS tickets_sold
        FROM events e
        LEFT JOIN (
            SELECT tt.event_id, SUM(oi.quantity) AS tickets_sold
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
            JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
            GROUP BY tt.event_id
        ) s ON s.event_id = e.event_id
        WHERE e.event_id = 11
        """
    ).fetchone()
    assert row == (33, 33)


def test_i8_e11_ignores_cancelled_order_tickets(
    seeded_connection: sqlite3.Connection,
) -> None:
    # Cancelled-order sale against E11's unsold general tier (tier_id 28).
    seeded_connection.execute(
        "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
        "VALUES (99, 'ORD-10999', 'web', 'cancelled', '2026-03-01T10:00:00')"
    )
    seeded_connection.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (99, 99, 28, 5, 6000)"
    )

    completed_only = seeded_connection.execute(
        """
        SELECT COALESCE(SUM(oi.quantity), 0)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        WHERE tt.event_id = 11
        """
    ).fetchone()[0]
    all_orders = seeded_connection.execute(
        """
        SELECT COALESCE(SUM(oi.quantity), 0)
        FROM order_items oi
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        WHERE tt.event_id = 11
        """
    ).fetchone()[0]
    assert completed_only == 33
    assert all_orders == 38
    assert _violations(seeded_connection, I8_VIOLATIONS) == []


def test_i1_detects_over_refund(
    seeded_connection: sqlite3.Connection,
) -> None:
    seeded_connection.execute(
        "INSERT INTO refunds "
        "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
        "refunded_at, reason) "
        "VALUES (99, 1, 1, 999999, '2026-01-01T10:00:00', 'customer_request')"
    )
    assert [row[0] for row in _violations(seeded_connection, I1_VIOLATIONS)] == [1]


def test_i3_detects_event_over_venue_capacity(
    seeded_connection: sqlite3.Connection,
) -> None:
    seeded_connection.execute("UPDATE events SET capacity = 999999 WHERE event_id = 12")
    assert [row[0] for row in _violations(seeded_connection, I3_VIOLATIONS)] == [12]


def test_i8_detects_oversell(
    seeded_connection: sqlite3.Connection,
) -> None:
    # Event 12 is scheduled with NULL attendance, so capacity can be lowered.
    seeded_connection.execute("UPDATE events SET capacity = 1 WHERE event_id = 12")
    # Force tickets_sold > capacity by attaching a completed sale to its tier.
    seeded_connection.execute(
        "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
        "VALUES (99, 'ORD-10999', 'web', 'completed', '2026-01-01T10:00:00')"
    )
    seeded_connection.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (99, 99, 29, 5, 1000)"
    )
    assert 12 in {row[0] for row in _violations(seeded_connection, I8_VIOLATIONS)}
