"""Slice 4C closure: all 14 executable development anchors pass static policy.

SQL text mirrors ``tests/unit/db/test_seed_anchors.py`` (the execution-side
source of truth); it is duplicated here as literal fixture data rather than
imported so this file stays independently runnable — pytest's default import
mode does not make sibling test directories importable in isolation.

Reaching this phase means every anchor clears structure, table, and column
policy (Slices 1-4C). Function and date authorization are still deferred to
a later slice, so this test only asserts each anchor validates without error.
"""

from __future__ import annotations

import sqlite3

import pytest

from bse_nlq.db.schema import apply_schema
from bse_nlq.metadata import load_semantic_metadata
from bse_nlq.metadata.models import APPLICATION_TABLES
from bse_nlq.metadata.reconcile import prompt_visible_columns
from bse_nlq.sql_policy import ValidatedSql, validate_sql

ANCHORS: dict[str, str] = {
    "A1": """
        SELECT e.name AS event_name, SUM(oi.line_gross_cents) AS gross_revenue_cents
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        GROUP BY e.event_id, e.name
        ORDER BY gross_revenue_cents DESC, e.event_id
        LIMIT 1
    """,
    "A2": """
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
    """,
    "A3": """
        SELECT SUM(oi.line_gross_cents) AS gross_revenue_cents
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        WHERE e.event_date >= '2026-02-01' AND e.event_date < '2026-03-01'
    """,
    "A4": """
        SELECT SUM(oi.line_gross_cents) AS booked_cents
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        WHERE o.purchased_at >= '2026-01-01' AND o.purchased_at < '2026-02-01'
    """,
    "A5": """
        SELECT SUM(oi.quantity) AS tickets_sold
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        JOIN venues v ON v.venue_id = e.venue_id
        WHERE v.name = 'Ironworks Music Hall'
    """,
    "A6": """
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
    """,
    "A7": """
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
    """,
    "A8": """
        SELECT (SUM(oi.line_gross_cents) * 2 + SUM(oi.quantity))
                   / (SUM(oi.quantity) * 2) AS avg_ticket_price_cents
        FROM order_items oi
        JOIN orders o        ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id  = oi.tier_id
        JOIN events e        ON e.event_id  = tt.event_id
        WHERE e.category = 'hockey'
    """,
    "A9": """
        SELECT e.name AS event_name, SUM(r.refund_amount_cents) AS refunded_cents
        FROM refunds r
        JOIN order_items oi ON oi.order_item_id = r.order_item_id
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        GROUP BY e.event_id, e.name
        ORDER BY refunded_cents DESC, e.event_id
    """,
    "A10": """
        SELECT e.name AS event_name, e.event_date
        FROM events e
        WHERE e.event_date >= '2026-03-15'
          AND e.status = 'scheduled'
        ORDER BY e.event_date, e.event_id
    """,
    "A11": """
        SELECT o.channel,
               SUM(oi.line_gross_cents) AS gross_revenue_cents,
               SUM(oi.quantity) AS tickets_sold
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        GROUP BY o.channel
        ORDER BY o.channel
    """,
    "A12": """
        SELECT e.name AS event_name, e.attendance, e.capacity,
               (e.attendance * 10000 * 2 + e.capacity) / (e.capacity * 2)
                   AS attendance_rate_bp
        FROM events e
        WHERE e.attendance IS NOT NULL
        ORDER BY attendance_rate_bp DESC, e.event_id
        LIMIT 1
    """,
    "A13": """
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
    """,
    "A14": """
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
    """,
}


_AnchorInventory = tuple[
    frozenset[str], frozenset[tuple[str, str]], frozenset[tuple[str, str]]
]


@pytest.fixture(scope="module")
def anchor_inventory() -> _AnchorInventory:
    """Real physical-table, physical-column, and prompt-visible inventories.

    Built from the packaged schema/metadata the same way the runtime does
    (schema application plus semantic-metadata reconciliation), so this test
    validates against the actual committed physical contract rather than a
    hand-maintained duplicate.
    """
    connection = sqlite3.connect(":memory:")
    try:
        apply_schema(connection)
        metadata = load_semantic_metadata(connection)
    finally:
        connection.close()
    physical_tables = frozenset(APPLICATION_TABLES)
    physical_columns = frozenset(
        (table_name, column_name)
        for table_name, table in metadata.tables.items()
        for column_name in table.columns
    )
    visible = prompt_visible_columns(metadata)
    visible_columns = frozenset(
        (table, column) for table, columns in visible.items() for column in columns
    )
    return physical_tables, physical_columns, visible_columns


@pytest.mark.parametrize("anchor_id", sorted(ANCHORS))
def test_anchor_passes_static_sql_policy(
    anchor_id: str,
    anchor_inventory: _AnchorInventory,
) -> None:
    physical_tables, physical_columns, visible_columns = anchor_inventory
    result = validate_sql(
        ANCHORS[anchor_id],
        physical_tables=physical_tables,
        physical_columns=physical_columns,
        prompt_visible_columns=visible_columns,
    )
    assert isinstance(result, ValidatedSql)
