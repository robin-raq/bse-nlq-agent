"""Financial and ticket reconciliation tests against the seeded database."""

from __future__ import annotations

import sqlite3

GROSS_BASE = """
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
"""

# Refunded money is a revenue metric: only refunds on completed-order lines.
COMPLETED_REFUNDED = """
SELECT COALESCE(SUM(r.refund_amount_cents), 0)
FROM refunds r
JOIN order_items oi ON oi.order_item_id = r.order_item_id
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
"""

LINE_REFUNDS_CTE = """
WITH line_refunds AS (
    SELECT r.order_item_id, SUM(r.refund_amount_cents) AS refunded_cents
    FROM refunds r
    JOIN order_items oi ON oi.order_item_id = r.order_item_id
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    GROUP BY r.order_item_id
)
"""


def test_overall_reconciliation(seeded_connection: sqlite3.Connection) -> None:
    gross = seeded_connection.execute(
        f"SELECT SUM(oi.line_gross_cents) {GROSS_BASE}"
    ).fetchone()[0]
    refunded = seeded_connection.execute(COMPLETED_REFUNDED).fetchone()[0]
    tickets = seeded_connection.execute(
        f"SELECT SUM(oi.quantity) {GROSS_BASE}"
    ).fetchone()[0]
    assert gross == 7_270_000
    assert refunded == 810_000
    assert gross - refunded == 6_460_000
    assert tickets == 957


def test_channel_reconciliation(seeded_connection: sqlite3.Connection) -> None:
    rows = {
        channel: (gross, tickets)
        for channel, gross, tickets in seeded_connection.execute(
            f"""
            SELECT o.channel,
                   SUM(oi.line_gross_cents),
                   SUM(oi.quantity)
            {GROSS_BASE}
            GROUP BY o.channel
            """
        )
    }
    assert rows == {
        "web": (2_750_000, 277),
        "mobile_app": (1_790_000, 325),
        "box_office": (1_380_000, 180),
        "partner": (1_350_000, 175),
    }
    assert sum(g for g, _ in rows.values()) == 7_270_000
    assert sum(t for _, t in rows.values()) == 957


def test_venue_reconciliation(seeded_connection: sqlite3.Connection) -> None:
    rows = {
        name: (gross, net)
        for name, gross, net in seeded_connection.execute(
            f"""
            {LINE_REFUNDS_CTE}
            SELECT v.name,
                   SUM(oi.line_gross_cents) AS gross,
                   SUM(oi.line_gross_cents)
                       - COALESCE(SUM(lr.refunded_cents), 0) AS net
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
            JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
            JOIN events e ON e.event_id = tt.event_id
            JOIN venues v ON v.venue_id = e.venue_id
            LEFT JOIN line_refunds lr ON lr.order_item_id = oi.order_item_id
            GROUP BY v.venue_id, v.name
            """
        )
    }
    assert rows == {
        "Kings Harbor Arena": (3_130_000, 3_045_000),
        "Marsh Hollow Field": (1_940_000, 1_940_000),
        "Ironworks Music Hall": (1_200_000, 1_050_000),
        "Tidewater Amphitheater": (1_000_000, 425_000),
    }
    assert sum(g for g, _ in rows.values()) == 7_270_000
    assert sum(n for _, n in rows.values()) == 6_460_000


def test_category_gross_reconciliation(
    seeded_connection: sqlite3.Connection,
) -> None:
    rows = dict(
        seeded_connection.execute(
            f"""
            SELECT e.category, SUM(oi.line_gross_cents)
            {GROSS_BASE}
            JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
            JOIN events e ON e.event_id = tt.event_id
            GROUP BY e.category
            """
        )
    )
    assert rows == {
        "concert": 2_190_000,
        "basketball": 1_800_000,
        "family": 1_700_000,
        "comedy": 980_000,
        "hockey": 600_000,
    }
    assert sum(rows.values()) == 7_270_000


def test_january_2026_purchase_gross(
    seeded_connection: sqlite3.Connection,
) -> None:
    gross = seeded_connection.execute(
        f"""
        SELECT SUM(oi.line_gross_cents)
        {GROSS_BASE}
        WHERE o.purchased_at >= '2026-01-01' AND o.purchased_at < '2026-02-01'
        """
    ).fetchone()[0]
    assert gross == 2_000_000


def test_direct_refund_join_fanout_on_e5(
    seeded_connection: sqlite3.Connection,
) -> None:
    naive = seeded_connection.execute(
        """
        SELECT SUM(oi.line_gross_cents)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        JOIN refunds r ON r.order_item_id = oi.order_item_id
        WHERE e.event_id = 5
        """
    ).fetchone()[0]
    correct = seeded_connection.execute(
        f"""
        {LINE_REFUNDS_CTE}
        SELECT SUM(oi.line_gross_cents)
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        LEFT JOIN line_refunds lr ON lr.order_item_id = oi.order_item_id
        WHERE e.event_id = 5
        """
    ).fetchone()[0]
    # L11 has two refunds: naive join doubles that line's 300_000 gross.
    # L12 has no refunds so it is dropped by the INNER JOIN entirely.
    assert naive != correct
    assert correct == 500_000
    assert naive == 600_000


A9_COMPLETED = """
SELECT e.name AS event_name, SUM(r.refund_amount_cents) AS refunded_cents
FROM refunds r
JOIN order_items oi ON oi.order_item_id = r.order_item_id
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
JOIN events e ON e.event_id = tt.event_id
GROUP BY e.event_id, e.name
ORDER BY refunded_cents DESC, e.event_id
"""


def test_cancelled_order_refund_excluded_from_revenue(
    seeded_connection: sqlite3.Connection,
) -> None:
    """A refund on a cancelled-order line must not change revenue metrics."""
    # Order 7 / line 10 is the cancelled-order fixture already in the seed.
    gross_before = seeded_connection.execute(
        f"SELECT SUM(oi.line_gross_cents) {GROSS_BASE}"
    ).fetchone()[0]
    refunded_before = seeded_connection.execute(COMPLETED_REFUNDED).fetchone()[0]
    a9_before = list(seeded_connection.execute(A9_COMPLETED))
    raw_before = seeded_connection.execute(
        "SELECT SUM(refund_amount_cents) FROM refunds"
    ).fetchone()[0]

    seeded_connection.execute(
        "INSERT INTO refunds "
        "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
        "refunded_at, reason) "
        "VALUES (99, 10, 1, 50_000, '2026-01-01T12:00:00', 'customer_request')"
    )

    gross_after = seeded_connection.execute(
        f"SELECT SUM(oi.line_gross_cents) {GROSS_BASE}"
    ).fetchone()[0]
    refunded_after = seeded_connection.execute(COMPLETED_REFUNDED).fetchone()[0]
    a9_after = list(seeded_connection.execute(A9_COMPLETED))
    raw_after = seeded_connection.execute(
        "SELECT SUM(refund_amount_cents) FROM refunds"
    ).fetchone()[0]

    assert gross_after == gross_before == 7_270_000
    assert refunded_after == refunded_before == 810_000
    assert gross_after - refunded_after == 6_460_000
    assert a9_after == a9_before
    assert raw_after == raw_before + 50_000
