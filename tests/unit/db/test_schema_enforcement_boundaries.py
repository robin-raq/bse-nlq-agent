"""Documents the cross-table invariants (I-1 through I-8 in
docs/planning/schema-design.md) that this schema deliberately does NOT
enforce via DDL.

SQLite prohibits subqueries in CHECK constraints, and this design uses no
triggers (the database is written once by seed code and read thereafter, so
a trigger could only fire where seed logic already runs). Each invariant
therefore belongs to the later deterministic seed-validation phase, not this
schema-contract phase.

Each test below constructs a fixture that violates one invariant and asserts
the schema layer accepts it anyway -- proving enforcement is genuinely
deferred, not silently present. If a future change adds a trigger or CHECK
that starts rejecting one of these, that is a contract change and this test
will fail, forcing a deliberate decision rather than an accidental one.
"""

import sqlite3

GOOD_TIMESTAMP = "2026-01-01T10:00:00"


def _insert_full_chain(
    connection: sqlite3.Connection,
    *,
    event_status: str = "completed",
    event_start: str = "2026-06-01T20:00:00",
    event_capacity: int = 500,
    venue_capacity: int = 1000,
    purchased_at: str = "2026-01-01T10:00:00",
    quantity: int = 10,
    unit_price_cents: int = 5000,
) -> None:
    connection.execute(
        "INSERT INTO venues (venue_id, name, district, capacity) "
        "VALUES (1, 'V', 'D', ?)",
        (venue_capacity,),
    )
    attendance = 100 if event_status == "completed" else None
    connection.execute(
        "INSERT INTO events "
        "(event_id, venue_id, name, category, status, start_local, "
        "capacity, attendance) "
        "VALUES (1, 1, 'E', 'concert', ?, ?, ?, ?)",
        (event_status, event_start, event_capacity, attendance),
    )
    connection.execute(
        "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
        "VALUES (1, 1, 'general', 5000)"
    )
    connection.execute(
        "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
        "VALUES (1, 'ORD-00001', 'web', 'completed', ?)",
        (purchased_at,),
    )
    connection.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (1, 1, 1, ?, ?)",
        (quantity, unit_price_cents),
    )


def test_i1_refund_amount_may_exceed_line_gross(
    connection: sqlite3.Connection,
) -> None:
    """I-1: refund_amount_cents <= line_gross_cents per line is a seed/test
    invariant."""
    _insert_full_chain(connection, quantity=1, unit_price_cents=1000)  # gross = 1000
    connection.execute(
        "INSERT INTO refunds "
        "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
        "refunded_at, reason) "
        "VALUES (1, 1, 1, 999999, ?, 'customer_request')",
        (GOOD_TIMESTAMP,),
    )  # refund far exceeds the line's gross; the schema does not reject this.


def test_i2_refunded_qty_may_exceed_line_quantity(
    connection: sqlite3.Connection,
) -> None:
    """I-2: SUM(refunded_qty) <= quantity per line is a seed/test invariant."""
    _insert_full_chain(connection, quantity=1)
    connection.execute(
        "INSERT INTO refunds "
        "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
        "refunded_at, reason) "
        "VALUES (1, 1, 999, 100, ?, 'customer_request')",
        (GOOD_TIMESTAMP,),
    )  # refunds 999 tickets against a line of quantity 1; schema does not reject this.


def test_i3_event_capacity_may_exceed_venue_capacity(
    connection: sqlite3.Connection,
) -> None:
    """I-3: events.capacity <= venues.capacity is a seed/test invariant."""
    _insert_full_chain(connection, venue_capacity=100, event_capacity=200)
    # Event capacity (200) exceeds venue capacity (100); schema does not reject this.


def test_i4_order_may_be_purchased_after_event_start(
    connection: sqlite3.Connection,
) -> None:
    """I-4: orders.purchased_at < events.start_local is a seed/test invariant."""
    _insert_full_chain(
        connection,
        event_start="2026-01-01T00:00:00",
        purchased_at="2026-06-01T00:00:00",
    )
    # Purchase occurs after the event's start; schema does not reject this.


def test_i5_refund_may_precede_purchase(connection: sqlite3.Connection) -> None:
    """I-5: refunds.refunded_at > orders.purchased_at is a seed/test invariant."""
    _insert_full_chain(connection, purchased_at="2026-06-01T00:00:00")
    connection.execute(
        "INSERT INTO refunds "
        "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
        "refunded_at, reason) "
        "VALUES (1, 1, 1, 100, '2020-01-01T00:00:00', 'customer_request')"
    )
    # Refund predates the purchase; schema does not reject this.


def test_i6_cancelled_event_line_need_not_be_fully_refunded(
    connection: sqlite3.Connection,
) -> None:
    """I-6: cancelled events must be fully refunded is a seed/test invariant."""
    _insert_full_chain(connection, event_status="cancelled", quantity=10)
    # No refund row is inserted at all for this cancelled event's completed
    # order line; schema does not require or reject this.


def test_i7_order_lines_may_span_multiple_events(
    connection: sqlite3.Connection,
) -> None:
    """I-7: all order_items in one order belong to one event is a seed/test
    invariant."""
    _insert_full_chain(connection)
    connection.execute(
        "INSERT INTO events "
        "(event_id, venue_id, name, category, status, start_local, "
        "capacity, attendance) "
        "VALUES (2, 1, 'E2', 'concert', 'scheduled', '2026-07-01T20:00:00', 500, NULL)"
    )
    connection.execute(
        "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
        "VALUES (2, 2, 'general', 5000)"
    )
    connection.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (2, 1, 2, 1, 5000)"
    )
    # Order 1 now has line items referencing two different events; schema
    # does not reject this.


def test_i8_tickets_sold_may_exceed_event_capacity(
    connection: sqlite3.Connection,
) -> None:
    """I-8: tickets_sold <= events.capacity (asserted as <=) is a seed/test
    invariant. It is stated as <=, not <, because a legitimately sold-out
    event may sit exactly on the boundary -- but this schema enforces
    neither direction, since it requires an aggregate across order_items.
    """
    _insert_full_chain(
        connection, event_status="scheduled", event_capacity=5, quantity=10
    )
    # 10 tickets sold against a capacity of 5; schema does not reject this.
