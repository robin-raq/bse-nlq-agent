"""order_items.line_gross_cents generated-column tests.

line_gross_cents = unit_price_cents * quantity, STORED and not settable by
the caller.
"""

import sqlite3

import pytest


def test_line_gross_equals_price_times_quantity(
    seeded_order: sqlite3.Connection,
) -> None:
    seeded_order.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (1, 1, 1, 7, 3000)"
    )
    row = seeded_order.execute(
        "SELECT line_gross_cents FROM order_items WHERE order_item_id = 1"
    ).fetchone()
    assert row == (21000,)


def test_zero_price_generates_zero_line_gross(seeded_order: sqlite3.Connection) -> None:
    seeded_order.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (1, 1, 1, 10, 0)"
    )
    row = seeded_order.execute(
        "SELECT line_gross_cents FROM order_items WHERE order_item_id = 1"
    ).fetchone()
    assert row == (0,)


def test_line_gross_is_integer_typed(seeded_order: sqlite3.Connection) -> None:
    seeded_order.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (1, 1, 1, 4, 5000)"
    )
    value = seeded_order.execute(
        "SELECT line_gross_cents FROM order_items WHERE order_item_id = 1"
    ).fetchone()[0]
    assert isinstance(value, int)


def test_cannot_insert_explicit_line_gross_value(
    seeded_order: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.OperationalError):
        seeded_order.execute(
            "INSERT INTO order_items "
            "(order_item_id, order_id, tier_id, quantity, unit_price_cents, "
            "line_gross_cents) "
            "VALUES (1, 1, 1, 4, 5000, 999999)"
        )


def test_cannot_update_line_gross_directly(seeded_order: sqlite3.Connection) -> None:
    seeded_order.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (1, 1, 1, 4, 5000)"
    )
    with pytest.raises(sqlite3.OperationalError):
        seeded_order.execute(
            "UPDATE order_items SET line_gross_cents = 1 WHERE order_item_id = 1"
        )


def test_line_gross_updates_when_inputs_change(
    seeded_order: sqlite3.Connection,
) -> None:
    seeded_order.execute(
        "INSERT INTO order_items "
        "(order_item_id, order_id, tier_id, quantity, unit_price_cents) "
        "VALUES (1, 1, 1, 4, 5000)"
    )
    seeded_order.execute(
        "UPDATE order_items SET unit_price_cents = 6000 WHERE order_item_id = 1"
    )
    row = seeded_order.execute(
        "SELECT line_gross_cents FROM order_items WHERE order_item_id = 1"
    ).fetchone()
    assert row == (24000,)
