"""Analytical trap regressions the frozen seed is designed to expose."""

from __future__ import annotations

import sqlite3


def test_face_value_vs_unit_price_hockey_average(
    seeded_connection: sqlite3.Connection,
) -> None:
    correct = seeded_connection.execute(
        """
        SELECT (SUM(oi.line_gross_cents) * 2 + SUM(oi.quantity))
                   / (SUM(oi.quantity) * 2)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        WHERE e.category = 'hockey'
        """
    ).fetchone()[0]
    wrong_face = seeded_connection.execute(
        """
        SELECT (SUM(tt.face_value_cents * oi.quantity) * 2 + SUM(oi.quantity))
                   / (SUM(oi.quantity) * 2)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        WHERE e.category = 'hockey'
        """
    ).fetchone()[0]
    wrong_avg = seeded_connection.execute(
        """
        SELECT AVG(oi.unit_price_cents)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        WHERE e.category = 'hockey'
        """
    ).fetchone()[0]
    assert correct == 7500
    assert wrong_face == 9000
    assert wrong_avg == 6000


def test_gross_vs_net_cancelled_event(
    seeded_connection: sqlite3.Connection,
) -> None:
    gross, net = seeded_connection.execute(
        """
        WITH line_refunds AS (
            SELECT r.order_item_id, SUM(r.refund_amount_cents) AS refunded_cents
            FROM refunds r
            JOIN order_items oi2 ON oi2.order_item_id = r.order_item_id
            JOIN orders o2 ON o2.order_id = oi2.order_id AND o2.status = 'completed'
            GROUP BY r.order_item_id
        )
        SELECT SUM(oi.line_gross_cents),
               SUM(oi.line_gross_cents) - COALESCE(SUM(lr.refunded_cents), 0)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        LEFT JOIN line_refunds lr ON lr.order_item_id = oi.order_item_id
        WHERE e.event_id = 10
        """
    ).fetchone()
    assert gross == 500_000
    assert net == 0


def test_cancelled_order_excluded_from_e4_gross(
    seeded_connection: sqlite3.Connection,
) -> None:
    completed = seeded_connection.execute(
        """
        SELECT SUM(oi.line_gross_cents)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        WHERE tt.event_id = 4
        """
    ).fetchone()[0]
    including_cancelled = seeded_connection.execute(
        """
        SELECT SUM(oi.line_gross_cents)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        WHERE tt.event_id = 4
        """
    ).fetchone()[0]
    assert completed == 550_000
    assert including_cancelled == 670_000


def test_e11_tickets_sold_vs_net(
    seeded_connection: sqlite3.Connection,
) -> None:
    sold, net = seeded_connection.execute(
        """
        WITH line_refunds AS (
            SELECT r.order_item_id, SUM(r.refunded_qty) AS refunded_qty
            FROM refunds r
            JOIN order_items oi2 ON oi2.order_item_id = r.order_item_id
            JOIN orders o2 ON o2.order_id = oi2.order_id AND o2.status = 'completed'
            GROUP BY r.order_item_id
        )
        SELECT SUM(oi.quantity),
               SUM(oi.quantity) - COALESCE(SUM(lr.refunded_qty), 0)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        LEFT JOIN line_refunds lr ON lr.order_item_id = oi.order_item_id
        WHERE tt.event_id = 11
        """
    ).fetchone()
    assert sold == 33
    assert net == 32


def test_event_date_vs_purchased_at_january(
    seeded_connection: sqlite3.Connection,
) -> None:
    by_purchase = seeded_connection.execute(
        """
        SELECT SUM(oi.line_gross_cents)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        WHERE o.purchased_at >= '2026-01-01' AND o.purchased_at < '2026-02-01'
        """
    ).fetchone()[0]
    by_event = seeded_connection.execute(
        """
        SELECT SUM(oi.line_gross_cents)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        WHERE e.event_date >= '2026-01-01' AND e.event_date < '2026-02-01'
        """
    ).fetchone()[0]
    assert by_purchase == 2_000_000
    assert by_event == 850_000


def test_venue_vs_event_capacity_sold_out(
    seeded_connection: sqlite3.Connection,
) -> None:
    by_event = seeded_connection.execute(
        """
        SELECT COUNT(*)
        FROM events e
        JOIN (
            SELECT tt.event_id, SUM(oi.quantity) AS tickets_sold
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
            JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
            GROUP BY tt.event_id
        ) s ON s.event_id = e.event_id
        WHERE s.tickets_sold >= e.capacity
        """
    ).fetchone()[0]
    by_venue = seeded_connection.execute(
        """
        SELECT COUNT(*)
        FROM events e
        JOIN venues v ON v.venue_id = e.venue_id
        JOIN (
            SELECT tt.event_id, SUM(oi.quantity) AS tickets_sold
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
            JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
            GROUP BY tt.event_id
        ) s ON s.event_id = e.event_id
        WHERE s.tickets_sold >= v.capacity
        """
    ).fetchone()[0]
    assert by_event == 1
    assert by_venue == 0


def test_global_tier_name_grouping_combines_offerings(
    seeded_connection: sqlite3.Connection,
) -> None:
    global_general = seeded_connection.execute(
        """
        SELECT SUM(oi.quantity)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        WHERE tt.tier_name = 'general'
        """
    ).fetchone()[0]
    e1_general = seeded_connection.execute(
        """
        SELECT SUM(oi.quantity)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        WHERE tt.event_id = 1 AND tt.tier_name = 'general'
        """
    ).fetchone()[0]
    assert e1_general == 50
    assert global_general > e1_general


def test_attendance_not_equal_tickets_sold(
    seeded_connection: sqlite3.Connection,
) -> None:
    row = seeded_connection.execute(
        """
        SELECT e.attendance, SUM(oi.quantity)
        FROM events e
        JOIN ticket_tiers tt ON tt.event_id = e.event_id
        JOIN order_items oi ON oi.tier_id = tt.tier_id
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        WHERE e.event_id = 1
        GROUP BY e.attendance
        """
    ).fetchone()
    assert row is not None
    assert row[0] == 16420
    assert row[1] == 79
    assert row[0] != row[1]
