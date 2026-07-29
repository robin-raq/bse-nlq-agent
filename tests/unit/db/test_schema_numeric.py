"""Numeric CHECK constraint tests: capacities, attendance, quantities, prices,
face values, refunded quantities, and refund amounts.
"""

import sqlite3

import pytest

GOOD_TIMESTAMP = "2026-01-01T10:00:00"


@pytest.mark.parametrize("capacity", [0, -1, -1000])
def test_venue_rejects_nonpositive_capacity(
    connection: sqlite3.Connection, capacity: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO venues (venue_id, name, district, capacity) "
            "VALUES (1, 'V', 'D', ?)",
            (capacity,),
        )


def test_venue_accepts_positive_capacity(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO venues (venue_id, name, district, capacity) "
        "VALUES (1, 'V', 'D', 1)"
    )


@pytest.mark.parametrize("capacity", [0, -1, -500])
def test_event_rejects_nonpositive_capacity(
    seeded_venue: sqlite3.Connection, capacity: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded_venue.execute(
            "INSERT INTO events "
            "(event_id, venue_id, name, category, status, start_local, "
            "capacity, attendance) "
            "VALUES (1, 1, 'E', 'concert', 'scheduled', ?, ?, NULL)",
            (GOOD_TIMESTAMP, capacity),
        )


@pytest.mark.parametrize("attendance", [-1, -100])
def test_event_rejects_negative_attendance(
    seeded_venue: sqlite3.Connection, attendance: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded_venue.execute(
            "INSERT INTO events "
            "(event_id, venue_id, name, category, status, start_local, "
            "capacity, attendance) "
            "VALUES (1, 1, 'E', 'concert', 'completed', ?, 500, ?)",
            (GOOD_TIMESTAMP, attendance),
        )


def test_event_rejects_attendance_above_capacity(
    seeded_venue: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded_venue.execute(
            "INSERT INTO events "
            "(event_id, venue_id, name, category, status, start_local, "
            "capacity, attendance) "
            "VALUES (1, 1, 'E', 'concert', 'completed', ?, 500, 501)",
            (GOOD_TIMESTAMP,),
        )


def test_event_accepts_attendance_equal_to_capacity(
    seeded_venue: sqlite3.Connection,
) -> None:
    seeded_venue.execute(
        "INSERT INTO events "
        "(event_id, venue_id, name, category, status, start_local, "
        "capacity, attendance) "
        "VALUES (1, 1, 'E', 'concert', 'completed', ?, 500, 500)",
        (GOOD_TIMESTAMP,),
    )


@pytest.mark.parametrize("quantity", [0, -1, -10])
def test_order_item_rejects_nonpositive_quantity(
    seeded_order: sqlite3.Connection, quantity: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded_order.execute(
            "INSERT INTO order_items "
            "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
            "VALUES (1, 1, 1, ?, 5000)",
            (quantity,),
        )


@pytest.mark.parametrize("price", [-1, -5000])
def test_order_item_rejects_negative_unit_price(
    seeded_order: sqlite3.Connection, price: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded_order.execute(
            "INSERT INTO order_items "
            "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
            "VALUES (1, 1, 1, 10, ?)",
            (price,),
        )


def test_order_item_accepts_zero_price_complimentary_line(
    seeded_order: sqlite3.Connection,
) -> None:
    seeded_order.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (1, 1, 1, 10, 0)"
    )
    row = seeded_order.execute(
        "SELECT unit_price_cents, line_gross_cents "
        "FROM order_items WHERE order_item_id = 1"
    ).fetchone()
    assert row == (0, 0)


@pytest.mark.parametrize("face_value", [0, -1, -25000])
def test_ticket_tier_rejects_invalid_face_value(
    seeded_event: sqlite3.Connection, face_value: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded_event.execute(
            "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
            "VALUES (1, 1, 'general', ?)",
            (face_value,),
        )


@pytest.mark.parametrize("refunded_qty", [0, -1, -5])
def test_refund_rejects_invalid_refunded_quantity(
    seeded_order_item: sqlite3.Connection, refunded_qty: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded_order_item.execute(
            "INSERT INTO refunds "
            "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
            "refunded_at, reason) "
            "VALUES (1, 1, ?, 100, ?, 'customer_request')",
            (refunded_qty, GOOD_TIMESTAMP),
        )


@pytest.mark.parametrize("amount", [-1, -100])
def test_refund_rejects_negative_amount(
    seeded_order_item: sqlite3.Connection, amount: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded_order_item.execute(
            "INSERT INTO refunds "
            "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
            "refunded_at, reason) "
            "VALUES (1, 1, 1, ?, ?, 'customer_request')",
            (amount, GOOD_TIMESTAMP),
        )


def test_refund_accepts_zero_amount(seeded_order_item: sqlite3.Connection) -> None:
    seeded_order_item.execute(
        "INSERT INTO refunds "
        "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
        "refunded_at, reason) "
        "VALUES (1, 1, 1, 0, ?, 'customer_request')",
        (GOOD_TIMESTAMP,),
    )
