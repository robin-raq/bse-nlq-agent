"""Exact row-count and literal-drift validation against the seeded database."""

from __future__ import annotations

import sqlite3

from bse_nlq.db import seed_data
from bse_nlq.db.seed_data import (
    EXPECTED_ROW_COUNTS,
    TOTAL_SEED_ROWS,
    UNSOLD_TIER_IDS,
)

APPLICATION_TABLES = (
    "venues",
    "events",
    "ticket_tiers",
    "orders",
    "order_items",
    "refunds",
)


def test_exact_table_row_counts(seeded_connection: sqlite3.Connection) -> None:
    counts = {
        table: seeded_connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in APPLICATION_TABLES
    }
    assert counts == EXPECTED_ROW_COUNTS
    assert sum(counts.values()) == TOTAL_SEED_ROWS


def test_primary_key_sets_match_manifest(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert {
        row[0] for row in seeded_connection.execute("SELECT venue_id FROM venues")
    } == {v[0] for v in seed_data.VENUES}
    assert {
        row[0] for row in seeded_connection.execute("SELECT event_id FROM events")
    } == {e[0] for e in seed_data.EVENTS}
    assert {
        row[0] for row in seeded_connection.execute("SELECT tier_id FROM ticket_tiers")
    } == {t[0] for t in seed_data.TICKET_TIERS}
    assert {
        row[0] for row in seeded_connection.execute("SELECT order_id FROM orders")
    } == {o[0] for o in seed_data.ORDERS}
    assert {
        row[0]
        for row in seeded_connection.execute("SELECT order_item_id FROM order_items")
    } == {i[0] for i in seed_data.ORDER_ITEMS}
    assert {
        row[0] for row in seeded_connection.execute("SELECT refund_id FROM refunds")
    } == {r[0] for r in seed_data.REFUNDS}


def test_event_names_and_order_refs(
    seeded_connection: sqlite3.Connection,
) -> None:
    names = {row[0] for row in seeded_connection.execute("SELECT name FROM events")}
    assert names == {e[2] for e in seed_data.EVENTS}
    refs = {row[0] for row in seeded_connection.execute("SELECT order_ref FROM orders")}
    assert refs == {o[1] for o in seed_data.ORDERS}


def test_purchase_timestamps_and_order_item_packing(
    seeded_connection: sqlite3.Connection,
) -> None:
    purchased = dict(
        seeded_connection.execute("SELECT order_id, purchased_at FROM orders")
    )
    assert purchased == {o[0]: o[4] for o in seed_data.ORDERS}

    packing = {
        order_id: tuple(
            item_id
            for (item_id,) in seeded_connection.execute(
                "SELECT order_item_id FROM order_items "
                "WHERE order_id = ? ORDER BY order_item_id",
                (order_id,),
            )
        )
        for order_id in purchased
    }
    expected: dict[int, tuple[int, ...]] = {}
    for item_id, order_id, *_rest in seed_data.ORDER_ITEMS:
        expected.setdefault(order_id, ())
        expected[order_id] = (*expected[order_id], item_id)
    assert packing == expected


def test_refund_mapping_and_unsold_tiers(
    seeded_connection: sqlite3.Connection,
) -> None:
    mapping = {
        row[0]: row[1]
        for row in seeded_connection.execute(
            "SELECT refund_id, order_item_id FROM refunds"
        )
    }
    assert mapping == {r[0]: r[1] for r in seed_data.REFUNDS}

    sold_tiers = {
        row[0]
        for row in seeded_connection.execute("SELECT DISTINCT tier_id FROM order_items")
    }
    all_tiers = {t[0] for t in seed_data.TICKET_TIERS}
    assert all_tiers - sold_tiers == UNSOLD_TIER_IDS


def test_domains_and_foreign_keys(
    seeded_connection: sqlite3.Connection,
) -> None:
    assert seeded_connection.execute("PRAGMA foreign_key_check").fetchall() == []

    categories = {
        row[0]
        for row in seeded_connection.execute("SELECT DISTINCT category FROM events")
    }
    assert categories == {
        "basketball",
        "hockey",
        "concert",
        "comedy",
        "family",
    }
    event_statuses = {
        row[0]
        for row in seeded_connection.execute("SELECT DISTINCT status FROM events")
    }
    assert event_statuses == {"scheduled", "completed", "cancelled"}
    order_statuses = {
        row[0]
        for row in seeded_connection.execute("SELECT DISTINCT status FROM orders")
    }
    assert order_statuses == {"completed", "cancelled"}
    channels = {
        row[0]
        for row in seeded_connection.execute("SELECT DISTINCT channel FROM orders")
    }
    assert channels == {"web", "mobile_app", "box_office", "partner"}
    reasons = {
        row[0]
        for row in seeded_connection.execute("SELECT DISTINCT reason FROM refunds")
    }
    assert reasons == {
        "customer_request",
        "event_cancelled",
        "duplicate_purchase",
    }


def test_generated_columns_match_inputs(
    seeded_connection: sqlite3.Connection,
) -> None:
    for event_id, _venue, _name, _cat, _status, start_local, *_rest in seed_data.EVENTS:
        row = seeded_connection.execute(
            "SELECT event_date, start_local FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        assert row is not None
        assert row[1] == start_local
        assert row[0] == start_local[:10]

    for item_id, _oid, _tid, qty, price in seed_data.ORDER_ITEMS:
        row = seeded_connection.execute(
            "SELECT line_gross_cents, quantity, unit_price_cents "
            "FROM order_items WHERE order_item_id = ?",
            (item_id,),
        ).fetchone()
        assert row == (qty * price, qty, price)


def test_six_tables_only_after_seed(
    seeded_connection: sqlite3.Connection,
) -> None:
    tables = {
        name
        for (name,) in seeded_connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert tables == set(APPLICATION_TABLES)


def test_seed_module_row_counts_match_expected_constants() -> None:
    assert len(seed_data.VENUES) == EXPECTED_ROW_COUNTS["venues"]
    assert len(seed_data.EVENTS) == EXPECTED_ROW_COUNTS["events"]
    assert len(seed_data.TICKET_TIERS) == EXPECTED_ROW_COUNTS["ticket_tiers"]
    assert len(seed_data.ORDERS) == EXPECTED_ROW_COUNTS["orders"]
    assert len(seed_data.ORDER_ITEMS) == EXPECTED_ROW_COUNTS["order_items"]
    assert len(seed_data.REFUNDS) == EXPECTED_ROW_COUNTS["refunds"]
    assert (
        len(seed_data.VENUES)
        + len(seed_data.EVENTS)
        + len(seed_data.TICKET_TIERS)
        + len(seed_data.ORDERS)
        + len(seed_data.ORDER_ITEMS)
        + len(seed_data.REFUNDS)
        == TOTAL_SEED_ROWS
    )
