"""The frozen physical SQLite schema for the BSE NLQ agent.

Contract source: docs/planning/schema-design.md. This module owns only DDL
application; seeding, connection factories, and query execution are separate
concerns per ARCHITECTURE.md.
"""

import sqlite3

_SCHEMA_SQL = """
BEGIN;

CREATE TABLE venues (
    venue_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (length(name) > 0),
    district TEXT NOT NULL CHECK (length(district) > 0),
    capacity INTEGER NOT NULL CHECK (capacity > 0)
) STRICT;

CREATE TABLE events (
    event_id INTEGER PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues (venue_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (length(name) > 0),
    category TEXT NOT NULL
        CHECK (category IN ('basketball', 'hockey', 'concert', 'comedy', 'family')),
    status TEXT NOT NULL
        CHECK (status IN ('scheduled', 'completed', 'cancelled')),
    start_local TEXT NOT NULL
        CHECK (start_local IS strftime('%Y-%m-%dT%H:%M:%S', start_local)),
    event_date TEXT NOT NULL GENERATED ALWAYS AS (date(start_local)) STORED,
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    attendance INTEGER
        CHECK (attendance IS NULL OR (attendance >= 0 AND attendance <= capacity)),
    CHECK ((status = 'completed') = (attendance IS NOT NULL))
) STRICT;

CREATE TABLE ticket_tiers (
    tier_id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events (event_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    tier_name TEXT NOT NULL CHECK (
        tier_name IN (
            'premium', 'reserved', 'general', 'pit', 'lawn', 'floor_ga', 'balcony'
        )
    ),
    face_value_cents INTEGER NOT NULL CHECK (face_value_cents > 0),
    UNIQUE (event_id, tier_name)
) STRICT;

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    order_ref TEXT NOT NULL UNIQUE CHECK (length(order_ref) = 9),
    channel TEXT NOT NULL
        CHECK (channel IN ('web', 'mobile_app', 'box_office', 'partner')),
    status TEXT NOT NULL CHECK (status IN ('completed', 'cancelled')),
    purchased_at TEXT NOT NULL
        CHECK (purchased_at IS strftime('%Y-%m-%dT%H:%M:%S', purchased_at))
) STRICT;

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders (order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    tier_id INTEGER NOT NULL REFERENCES ticket_tiers (tier_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    line_gross_cents INTEGER NOT NULL
        GENERATED ALWAYS AS (unit_price_cents * quantity) STORED,
    UNIQUE (order_id, tier_id)
) STRICT;

CREATE TABLE refunds (
    refund_id INTEGER PRIMARY KEY,
    order_item_id INTEGER NOT NULL REFERENCES order_items (order_item_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    refunded_qty INTEGER NOT NULL CHECK (refunded_qty > 0),
    refund_amount_cents INTEGER NOT NULL CHECK (refund_amount_cents >= 0),
    refunded_at TEXT NOT NULL
        CHECK (refunded_at IS strftime('%Y-%m-%dT%H:%M:%S', refunded_at)),
    reason TEXT NOT NULL CHECK (
        reason IN ('customer_request', 'event_cancelled', 'duplicate_purchase')
    )
) STRICT;

CREATE INDEX idx_events_event_date ON events (event_date);
CREATE INDEX idx_events_venue_id ON events (venue_id);
CREATE INDEX idx_events_category ON events (category);
CREATE INDEX idx_events_status ON events (status);
CREATE INDEX idx_ticket_tiers_event_id ON ticket_tiers (event_id);
CREATE INDEX idx_order_items_tier_id ON order_items (tier_id);
CREATE INDEX idx_order_items_order_id ON order_items (order_id);
CREATE INDEX idx_orders_purchased_at ON orders (purchased_at);
CREATE INDEX idx_orders_status ON orders (status);
CREATE INDEX idx_refunds_order_item_id ON refunds (order_item_id);

COMMIT;
"""


def apply_schema(connection: sqlite3.Connection) -> None:
    """Apply the approved six-table schema to a caller-supplied connection.

    Precondition: ``connection.in_transaction`` must be False. This function
    never commits, rolls back, or otherwise disturbs a caller's pending
    uncommitted work, so it refuses to run rather than silently absorbing an
    open transaction into its own.

    Enables and verifies foreign-key enforcement outside the schema
    transaction, then executes the frozen DDL as one transaction. On any
    failure after the schema transaction begins — including
    non-``sqlite3.Error`` exceptions — the schema transaction is rolled
    back and the original exception is re-raised. The connection is left
    with no open transaction on both success and failure. The caller owns
    the connection's lifecycle; this function opens nothing, seeds nothing,
    and reads no clock.
    """
    if connection.in_transaction:
        raise sqlite3.ProgrammingError(
            "apply_schema requires a connection with no active transaction"
        )

    connection.execute("PRAGMA foreign_keys = ON")
    row = connection.execute("PRAGMA foreign_keys").fetchone()
    if row is None or row[0] != 1:
        raise sqlite3.ProgrammingError("failed to enable PRAGMA foreign_keys")

    try:
        connection.executescript(_SCHEMA_SQL)
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
