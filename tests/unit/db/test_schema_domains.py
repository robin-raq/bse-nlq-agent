"""Controlled-domain CHECK tests.

Each domain is tested independently so a failure is caused by the intended
constraint, not an unrelated one.
"""

import sqlite3

import pytest

GOOD_TIMESTAMP = "2026-01-01T10:00:00"


def _insert_event(
    connection: sqlite3.Connection, category: str = "concert", status: str = "scheduled"
) -> None:
    attendance = 100 if status == "completed" else None
    connection.execute(
        "INSERT INTO events "
        "(event_id, venue_id, name, category, status, start_local, "
        "capacity, attendance) "
        "VALUES (1, 1, 'E', ?, ?, ?, 500, ?)",
        (category, status, GOOD_TIMESTAMP, attendance),
    )


@pytest.mark.parametrize(
    "category", ["basketball", "hockey", "concert", "comedy", "family"]
)
def test_event_category_accepts_approved_values(
    seeded_venue: sqlite3.Connection, category: str
) -> None:
    _insert_event(seeded_venue, category=category)


@pytest.mark.parametrize("category", ["esports", "theater", "", "CONCERT"])
def test_event_category_rejects_unapproved_values(
    seeded_venue: sqlite3.Connection, category: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _insert_event(seeded_venue, category=category)


@pytest.mark.parametrize("status", ["scheduled", "completed", "cancelled"])
def test_event_status_accepts_approved_values(
    seeded_venue: sqlite3.Connection, status: str
) -> None:
    _insert_event(seeded_venue, status=status)


@pytest.mark.parametrize("status", ["pending", "postponed", "", "Scheduled"])
def test_event_status_rejects_unapproved_values(
    seeded_venue: sqlite3.Connection, status: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _insert_event(seeded_venue, status=status)


@pytest.mark.parametrize(
    "tier_name",
    ["premium", "reserved", "general", "pit", "lawn", "floor_ga", "balcony"],
)
def test_tier_name_accepts_approved_values(
    seeded_event: sqlite3.Connection, tier_name: str
) -> None:
    seeded_event.execute(
        "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
        "VALUES (1, 1, ?, 5000)",
        (tier_name,),
    )


@pytest.mark.parametrize("tier_name", ["vip", "standing", "", "General"])
def test_tier_name_rejects_unapproved_values(
    seeded_event: sqlite3.Connection, tier_name: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded_event.execute(
            "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
            "VALUES (1, 1, ?, 5000)",
            (tier_name,),
        )


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_order_status_accepts_approved_values(
    connection: sqlite3.Connection, status: str
) -> None:
    connection.execute(
        "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
        "VALUES (1, 'ORD-00001', 'web', ?, ?)",
        (status, GOOD_TIMESTAMP),
    )


@pytest.mark.parametrize("status", ["pending", "failed", "", "Completed"])
def test_order_status_rejects_unapproved_values(
    connection: sqlite3.Connection, status: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
            "VALUES (1, 'ORD-00001', 'web', ?, ?)",
            (status, GOOD_TIMESTAMP),
        )


@pytest.mark.parametrize("channel", ["web", "mobile_app", "box_office", "partner"])
def test_sales_channel_accepts_approved_values(
    connection: sqlite3.Connection, channel: str
) -> None:
    connection.execute(
        "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
        "VALUES (1, 'ORD-00001', ?, 'completed', ?)",
        (channel, GOOD_TIMESTAMP),
    )


@pytest.mark.parametrize("channel", ["phone", "kiosk", "", "Web"])
def test_sales_channel_rejects_unapproved_values(
    connection: sqlite3.Connection, channel: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
            "VALUES (1, 'ORD-00001', ?, 'completed', ?)",
            (channel, GOOD_TIMESTAMP),
        )


@pytest.mark.parametrize(
    "reason", ["customer_request", "event_cancelled", "duplicate_purchase"]
)
def test_refund_reason_accepts_approved_values(
    seeded_order_item: sqlite3.Connection, reason: str
) -> None:
    seeded_order_item.execute(
        "INSERT INTO refunds "
        "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
        "refunded_at, reason) "
        "VALUES (1, 1, 1, 100, ?, ?)",
        (GOOD_TIMESTAMP, reason),
    )


@pytest.mark.parametrize("reason", ["fraud", "chargeback", "", "Customer_Request"])
def test_refund_reason_rejects_unapproved_values(
    seeded_order_item: sqlite3.Connection, reason: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded_order_item.execute(
            "INSERT INTO refunds "
            "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
            "refunded_at, reason) "
            "VALUES (1, 1, 1, 100, ?, ?)",
            (GOOD_TIMESTAMP, reason),
        )
