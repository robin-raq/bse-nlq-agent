"""Deterministic seed loader for the BSE NLQ agent.

Contract sources: docs/planning/seed-manifest.md (literals) and
docs/planning/schema-design.md (analytical definitions). Schema application
remains a separate explicit call; this module never calls apply_schema.
"""

from __future__ import annotations

import sqlite3

from bse_nlq.db import seed_data

_ACTIVE_TXN_MESSAGE = "load_seed_data requires a connection with no active transaction"


def load_seed_data(connection: sqlite3.Connection) -> None:
    """Insert the frozen 109-row seed into a caller-supplied connection.

    Precondition: ``connection.in_transaction`` must be False. This function
    never commits, rolls back, or otherwise disturbs a caller's pending
    uncommitted work, so it refuses to run rather than silently absorbing an
    open transaction into its own.

    Precondition: the approved physical schema must already be present on the
    connection. This function does not call ``apply_schema``.

    Verifies ``PRAGMA foreign_keys`` is enabled (value ``1``) before inserting.
    Inserts all seed rows as one transaction. On any failure after the loader
    begins its transaction — including non-``sqlite3.Error`` exceptions — the
    seed transaction is rolled back and the original exception is re-raised.
    The connection is left with no open transaction on both success and failure.

    The operation is not idempotent: a second load may raise because primary
    keys already exist, but that failure leaves the first complete seed intact.

    Opens no database path, reads no clock, seeds only deterministic literals
    from ``seed_data``, and mutates no global state.
    """
    if connection.in_transaction:
        raise sqlite3.ProgrammingError(_ACTIVE_TXN_MESSAGE)

    row = connection.execute("PRAGMA foreign_keys").fetchone()
    if row is None or row[0] != 1:
        raise sqlite3.ProgrammingError(
            "load_seed_data requires PRAGMA foreign_keys to be enabled"
        )

    try:
        connection.execute("BEGIN")
        connection.executemany(
            "INSERT INTO venues (venue_id, name, district, capacity) "
            "VALUES (?, ?, ?, ?)",
            seed_data.VENUES,
        )
        connection.executemany(
            "INSERT INTO events "
            "(event_id, venue_id, name, category, status, start_local, "
            "capacity, attendance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            seed_data.EVENTS,
        )
        connection.executemany(
            "INSERT INTO ticket_tiers "
            "(tier_id, event_id, tier_name, face_value_cents) "
            "VALUES (?, ?, ?, ?)",
            seed_data.TICKET_TIERS,
        )
        connection.executemany(
            "INSERT INTO orders "
            "(order_id, order_ref, channel, status, purchased_at) "
            "VALUES (?, ?, ?, ?, ?)",
            seed_data.ORDERS,
        )
        connection.executemany(
            "INSERT INTO order_items "
            "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
            "VALUES (?, ?, ?, ?, ?)",
            seed_data.ORDER_ITEMS,
        )
        connection.executemany(
            "INSERT INTO refunds "
            "(refund_id, order_item_id, refunded_qty, refund_amount_cents, "
            "refunded_at, reason) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            seed_data.REFUNDS,
        )
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
