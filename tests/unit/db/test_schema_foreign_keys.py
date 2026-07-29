"""Foreign-key contract and enforcement tests.

Revenue path: order_items -> ticket_tiers -> events -> venues; refunds ->
order_items. Every FK uses ON UPDATE RESTRICT ON DELETE RESTRICT.
"""

import sqlite3

GOOD_TIMESTAMP = "2026-01-01T10:00:00"

# (child_table, [(from_column, to_table, to_column, on_update, on_delete), ...])
EXPECTED_FOREIGN_KEYS: dict[str, list[tuple[str, str, str, str, str]]] = {
    "events": [("venue_id", "venues", "venue_id", "RESTRICT", "RESTRICT")],
    "ticket_tiers": [("event_id", "events", "event_id", "RESTRICT", "RESTRICT")],
    "order_items": [
        ("order_id", "orders", "order_id", "RESTRICT", "RESTRICT"),
        ("tier_id", "ticket_tiers", "tier_id", "RESTRICT", "RESTRICT"),
    ],
    "refunds": [
        ("order_item_id", "order_items", "order_item_id", "RESTRICT", "RESTRICT")
    ],
}


def test_foreign_keys_enabled_after_apply(connection: sqlite3.Connection) -> None:
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_foreign_key_contracts_match(connection: sqlite3.Connection) -> None:
    for table, expected in EXPECTED_FOREIGN_KEYS.items():
        rows = connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        actual = {
            (row[3], row[2], row[4], row[5], row[6]) for row in rows
        }  # from, table, to, on_update, on_delete
        expected_set = {
            (from_col, to_table, to_col, on_update, on_delete)
            for from_col, to_table, to_col, on_update, on_delete in expected
        }
        assert actual == expected_set, table


def test_orders_and_venues_have_no_foreign_keys(connection: sqlite3.Connection) -> None:
    assert connection.execute("PRAGMA foreign_key_list(orders)").fetchall() == []
    assert connection.execute("PRAGMA foreign_key_list(venues)").fetchall() == []


def test_valid_parent_child_chain_inserts_succeed(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        "INSERT INTO venues (venue_id, name, district, capacity) "
        "VALUES (1, 'V', 'D', 1000)"
    )
    connection.execute(
        "INSERT INTO events "
        "(event_id, venue_id, name, category, status, start_local, "
        "capacity, attendance) "
        "VALUES (1, 1, 'E', 'concert', 'completed', ?, 500, 100)",
        (GOOD_TIMESTAMP,),
    )
    connection.execute(
        "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
        "VALUES (1, 1, 'general', 5000)"
    )
    connection.execute(
        "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
        "VALUES (1, 'ORD-00001', 'web', 'completed', ?)",
        (GOOD_TIMESTAMP,),
    )
    connection.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (1, 1, 1, 2, 5000)"
    )
    connection.execute(
        "INSERT INTO refunds "
        "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
        "refunded_at, reason) "
        "VALUES (1, 1, 1, 5000, ?, 'customer_request')",
        (GOOD_TIMESTAMP,),
    )
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_event_rejects_missing_venue(connection: sqlite3.Connection) -> None:
    try:
        connection.execute(
            "INSERT INTO events "
            "(event_id, venue_id, name, category, status, start_local, "
            "capacity, attendance) "
            "VALUES (1, 999, 'E', 'concert', 'completed', ?, 500, 100)",
            (GOOD_TIMESTAMP,),
        )
        raise AssertionError("event with missing venue was accepted")
    except sqlite3.IntegrityError:
        pass


def test_ticket_tier_rejects_missing_event(connection: sqlite3.Connection) -> None:
    try:
        connection.execute(
            "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
            "VALUES (1, 999, 'general', 5000)"
        )
        raise AssertionError("ticket tier with missing event was accepted")
    except sqlite3.IntegrityError:
        pass


def test_order_item_rejects_missing_order(
    seeded_tier: sqlite3.Connection,
) -> None:
    try:
        seeded_tier.execute(
            "INSERT INTO order_items "
            "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
            "VALUES (1, 999, 1, 2, 5000)"
        )
        raise AssertionError("order item with missing order was accepted")
    except sqlite3.IntegrityError:
        pass


def test_order_item_rejects_missing_tier(
    seeded_order: sqlite3.Connection,
) -> None:
    try:
        seeded_order.execute(
            "INSERT INTO order_items "
            "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
            "VALUES (1, 1, 999, 2, 5000)"
        )
        raise AssertionError("order item with missing tier was accepted")
    except sqlite3.IntegrityError:
        pass


def test_refund_rejects_missing_order_item(
    seeded_order: sqlite3.Connection,
) -> None:
    try:
        seeded_order.execute(
            "INSERT INTO refunds "
            "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
            "refunded_at, reason) "
            "VALUES (1, 999, 1, 100, ?, 'customer_request')",
            (GOOD_TIMESTAMP,),
        )
        raise AssertionError("refund with missing order item was accepted")
    except sqlite3.IntegrityError:
        pass


def test_foreign_key_check_empty_for_valid_fixture(
    seeded_order_item: sqlite3.Connection,
) -> None:
    assert seeded_order_item.execute("PRAGMA foreign_key_check").fetchall() == []
