"""Date/timestamp CHECK tests for every date-bearing column.

Covers events.start_local, orders.purchased_at, refunds.refunded_at (each
CHECKed with `IS strftime(...)`, never `=`), and events.event_date (a STORED
generated column derived from start_local, not an independent CHECK).
"""

import sqlite3

import pytest

GOOD_TIMESTAMP = "2026-01-01T10:00:00"

# Malformed date/timestamp fixtures shared across every date/timestamp column.
BAD_TIMESTAMPS = (
    "not-a-date",
    "2026-02-30",  # impossible date
    "2026-2-14",  # malformed separator/padding
    "",
    "2026-01-01T10:00:00Z",  # trailing Z
    "2026-01-01T10:00:00+00:00",  # explicit offset
    "2026-01-01 10:00:00",  # malformed separator (space instead of T)
    "2026-01-01T10:00",  # missing seconds
    "2026-01-01T10:00:00extra",  # extra trailing content
)


@pytest.mark.parametrize("bad_value", BAD_TIMESTAMPS)
def test_events_start_local_rejects_malformed_values(
    seeded_venue: sqlite3.Connection, bad_value: str
) -> None:
    """Malformed start_local values must raise IntegrityError.

    Some fixtures are rejected via generated event_date NOT NULL rather than
    the start_local CHECK; see
    test_events_start_local_check_is_the_rejecting_constraint for CHECK-source
    coverage.
    """
    with pytest.raises(sqlite3.IntegrityError):
        seeded_venue.execute(
            "INSERT INTO events "
            "(event_id, venue_id, name, category, status, start_local, "
            "capacity, attendance) "
            "VALUES (1, 1, 'E', 'concert', 'scheduled', ?, 500, NULL)",
            (bad_value,),
        )


# Fixtures known to fire the start_local IS strftime CHECK itself (message
# contains that expression), not only the generated event_date NOT NULL path.
_START_LOCAL_CHECK_SOURCED = (
    "2026-02-30",
    "2026-01-01T10:00:00Z",
    "2026-01-01T10:00:00+00:00",
    "2026-01-01 10:00:00",
    "2026-01-01T10:00",
)


@pytest.mark.parametrize("bad_value", _START_LOCAL_CHECK_SOURCED)
def test_events_start_local_check_is_the_rejecting_constraint(
    seeded_venue: sqlite3.Connection, bad_value: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError, match=r"start_local IS strftime"):
        seeded_venue.execute(
            "INSERT INTO events "
            "(event_id, venue_id, name, category, status, start_local, "
            "capacity, attendance) "
            "VALUES (1, 1, 'E', 'concert', 'scheduled', ?, 500, NULL)",
            (bad_value,),
        )


def test_events_start_local_accepts_valid_value(
    seeded_venue: sqlite3.Connection,
) -> None:
    seeded_venue.execute(
        "INSERT INTO events "
        "(event_id, venue_id, name, category, status, start_local, "
        "capacity, attendance) "
        "VALUES (1, 1, 'E', 'concert', 'scheduled', ?, 500, NULL)",
        (GOOD_TIMESTAMP,),
    )


def test_events_event_date_equals_date_portion_of_start_local(
    seeded_venue: sqlite3.Connection,
) -> None:
    seeded_venue.execute(
        "INSERT INTO events "
        "(event_id, venue_id, name, category, status, start_local, "
        "capacity, attendance) "
        "VALUES (1, 1, 'E', 'concert', 'scheduled', '2026-07-04T20:15:30', 500, NULL)"
    )
    row = seeded_venue.execute(
        "SELECT event_date FROM events WHERE event_id = 1"
    ).fetchone()
    assert row == ("2026-07-04",)


@pytest.mark.parametrize("bad_value", BAD_TIMESTAMPS)
def test_orders_purchased_at_rejects_malformed_values(
    connection: sqlite3.Connection, bad_value: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
            "VALUES (1, 'ORD-00001', 'web', 'completed', ?)",
            (bad_value,),
        )


def test_orders_purchased_at_accepts_valid_value(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
        "VALUES (1, 'ORD-00001', 'web', 'completed', ?)",
        (GOOD_TIMESTAMP,),
    )


@pytest.mark.parametrize("bad_value", BAD_TIMESTAMPS)
def test_refunds_refunded_at_rejects_malformed_values(
    seeded_order_item: sqlite3.Connection, bad_value: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded_order_item.execute(
            "INSERT INTO refunds "
            "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
            "refunded_at, reason) "
            "VALUES (1, 1, 1, 100, ?, 'customer_request')",
            (bad_value,),
        )


def test_refunds_refunded_at_accepts_valid_value(
    seeded_order_item: sqlite3.Connection,
) -> None:
    seeded_order_item.execute(
        "INSERT INTO refunds "
        "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
        "refunded_at, reason) "
        "VALUES (1, 1, 1, 100, ?, 'customer_request')",
        (GOOD_TIMESTAMP,),
    )
