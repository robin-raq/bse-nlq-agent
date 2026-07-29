"""Uniqueness constraint tests: single-column and composite."""

import sqlite3

import pytest

GOOD_TIMESTAMP = "2026-01-01T10:00:00"


def test_venue_name_is_unique(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO venues (venue_id, name, district, capacity) "
        "VALUES (1, 'V', 'D1', 100)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO venues (venue_id, name, district, capacity) "
            "VALUES (2, 'V', 'D2', 200)"
        )


def test_order_ref_is_unique(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
        "VALUES (1, 'ORD-00001', 'web', 'completed', ?)",
        (GOOD_TIMESTAMP,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
            "VALUES (2, 'ORD-00001', 'mobile_app', 'completed', ?)",
            (GOOD_TIMESTAMP,),
        )


def test_tier_name_unique_within_event(seeded_event: sqlite3.Connection) -> None:
    seeded_event.execute(
        "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
        "VALUES (1, 1, 'general', 5000)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        seeded_event.execute(
            "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
            "VALUES (2, 1, 'general', 6000)"
        )


def test_tier_name_may_repeat_across_events(seeded_event: sqlite3.Connection) -> None:
    seeded_event.execute(
        "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
        "VALUES (1, 1, 'general', 5000)"
    )
    seeded_event.execute(
        "INSERT INTO events "
        "(event_id, venue_id, name, category, status, start_local, "
        "capacity, attendance) "
        "VALUES (2, 1, 'E2', 'concert', 'scheduled', ?, 500, NULL)",
        (GOOD_TIMESTAMP,),
    )
    # Same tier_name, different event: must succeed.
    seeded_event.execute(
        "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
        "VALUES (2, 2, 'general', 5500)"
    )


def test_order_and_tier_unique_within_order(seeded_order: sqlite3.Connection) -> None:
    seeded_order.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (1, 1, 1, 4, 5000)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        seeded_order.execute(
            "INSERT INTO order_items "
            "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
            "VALUES (2, 1, 1, 2, 5000)"
        )


def test_same_tier_may_repeat_across_different_orders(
    seeded_order: sqlite3.Connection,
) -> None:
    seeded_order.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (1, 1, 1, 4, 5000)"
    )
    seeded_order.execute(
        "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
        "VALUES (2, 'ORD-00002', 'web', 'completed', ?)",
        (GOOD_TIMESTAMP,),
    )
    # Same tier, different order: must succeed.
    seeded_order.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (2, 2, 1, 3, 5000)"
    )
