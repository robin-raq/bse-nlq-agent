"""Artifact validation evidence for published databases."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bse_nlq.db.artifact import APPLICATION_TABLES, APPROVED_INDEXES
from bse_nlq.db.build import build_database


def test_invariants_and_reconciliation_on_artifact(tmp_path: Path) -> None:
    destination = tmp_path / "analytics.db"
    build_database(destination)
    conn = sqlite3.connect(destination)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        gross = conn.execute(
            """
            SELECT SUM(oi.line_gross_cents)
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
            """
        ).fetchone()[0]
        refunded = conn.execute(
            """
            SELECT COALESCE(SUM(r.refund_amount_cents), 0)
            FROM refunds r
            JOIN order_items oi ON oi.order_item_id = r.order_item_id
            JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
            """
        ).fetchone()[0]
        tickets = conn.execute(
            """
            SELECT SUM(oi.quantity)
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
            """
        ).fetchone()[0]
        assert gross == 7_270_000
        assert refunded == 810_000
        assert gross - refunded == 6_460_000
        assert tickets == 957

        a13 = conn.execute(
            """
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
        ).fetchall()
        assert a13 == [("Harbor Kings Preview Showcase",)]
        a14 = conn.execute(
            """
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
        ).fetchall()
        assert a14 == []
    finally:
        conn.close()


def test_index_inventory_and_no_views_or_triggers(tmp_path: Path) -> None:
    destination = tmp_path / "objects.db"
    build_database(destination)
    conn = sqlite3.connect(destination)
    try:
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert indexes == set(APPROVED_INDEXES)
        views = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'view'"
        ).fetchall()
        triggers = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        ).fetchall()
        assert views == []
        assert triggers == []
        assert set(APPLICATION_TABLES) == {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        conn.close()
