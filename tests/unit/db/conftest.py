"""Shared fixtures and fixture data for schema contract tests.

Every fixture uses a fresh in-memory SQLite connection; nothing here persists
a database file or reads the machine clock.
"""

import sqlite3
from collections.abc import Iterator

import pytest

from bse_nlq.db.schema import apply_schema

APPLICATION_TABLES = (
    "venues",
    "events",
    "ticket_tiers",
    "orders",
    "order_items",
    "refunds",
)

GOOD_TIMESTAMP = "2026-01-01T10:00:00"

# Malformed date/timestamp fixtures shared across every date/timestamp column.
BAD_TIMESTAMPS = (
    "not-a-date",
    "2026-02-30",  # impossible date
    "2026-2-14",  # malformed separator (missing zero-padding)
    "",
    "2026-01-01T10:00:00Z",  # trailing Z
    "2026-01-01T10:00:00+00:00",  # explicit offset
    "2026-01-01 10:00:00",  # malformed separator (space instead of T)
    "2026-01-01T10:00",  # missing seconds
    "2026-01-01T10:00:00extra",  # extra trailing content
)


@pytest.fixture
def raw_connection() -> Iterator[sqlite3.Connection]:
    """A bare in-memory connection with no schema applied."""
    conn = sqlite3.connect(":memory:")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def connection(raw_connection: sqlite3.Connection) -> sqlite3.Connection:
    """An in-memory connection with the approved schema applied."""
    apply_schema(raw_connection)
    return raw_connection


@pytest.fixture
def seeded_connection(connection: sqlite3.Connection) -> sqlite3.Connection:
    """Schema applied and the frozen 109-row seed loaded."""
    from bse_nlq.db.seed import load_seed_data

    load_seed_data(connection)
    return connection


@pytest.fixture
def seeded_venue(connection: sqlite3.Connection) -> sqlite3.Connection:
    """A connection with one valid venue row, for FK-parent fixtures."""
    connection.execute(
        "INSERT INTO venues (venue_id, name, district, capacity) "
        "VALUES (1, 'Test Venue', 'Test District', 1000)"
    )
    return connection


@pytest.fixture
def seeded_event(seeded_venue: sqlite3.Connection) -> sqlite3.Connection:
    """A connection with one valid completed event, for FK-parent fixtures."""
    seeded_venue.execute(
        "INSERT INTO events "
        "(event_id, venue_id, name, category, status, start_local, "
        "capacity, attendance) "
        "VALUES (1, 1, 'Test Event', 'concert', 'completed', ?, 500, 100)",
        (GOOD_TIMESTAMP,),
    )
    return seeded_venue


@pytest.fixture
def seeded_tier(seeded_event: sqlite3.Connection) -> sqlite3.Connection:
    """A connection with one valid ticket tier, for FK-parent fixtures."""
    seeded_event.execute(
        "INSERT INTO ticket_tiers (tier_id, event_id, tier_name, face_value_cents) "
        "VALUES (1, 1, 'general', 5000)"
    )
    return seeded_event


@pytest.fixture
def seeded_order(seeded_tier: sqlite3.Connection) -> sqlite3.Connection:
    """A connection with one valid completed order, for FK-parent fixtures."""
    seeded_tier.execute(
        "INSERT INTO orders (order_id, order_ref, channel, status, purchased_at) "
        "VALUES (1, 'ORD-00001', 'web', 'completed', ?)",
        (GOOD_TIMESTAMP,),
    )
    return seeded_tier


@pytest.fixture
def seeded_order_item(seeded_order: sqlite3.Connection) -> sqlite3.Connection:
    """A connection with one valid order item, for FK-parent fixtures."""
    seeded_order.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (1, 1, 1, 10, 5000)"
    )
    return seeded_order
