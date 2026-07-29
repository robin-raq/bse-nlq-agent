"""Per-table, per-column contract tests: name, type, nullability, PK, and
generated-column status, per docs/planning/schema-design.md's data dictionary.
"""

import sqlite3

# (name, declared_type, not_null, is_pk, is_generated)
EXPECTED_COLUMNS: dict[str, list[tuple[str, str, bool, bool, bool]]] = {
    "venues": [
        ("venue_id", "INTEGER", False, True, False),
        ("name", "TEXT", True, False, False),
        ("district", "TEXT", True, False, False),
        ("capacity", "INTEGER", True, False, False),
    ],
    "events": [
        ("event_id", "INTEGER", False, True, False),
        ("venue_id", "INTEGER", True, False, False),
        ("name", "TEXT", True, False, False),
        ("category", "TEXT", True, False, False),
        ("status", "TEXT", True, False, False),
        ("start_local", "TEXT", True, False, False),
        ("event_date", "TEXT", True, False, True),
        ("capacity", "INTEGER", True, False, False),
        ("attendance", "INTEGER", False, False, False),
    ],
    "ticket_tiers": [
        ("tier_id", "INTEGER", False, True, False),
        ("event_id", "INTEGER", True, False, False),
        ("tier_name", "TEXT", True, False, False),
        ("face_value_cents", "INTEGER", True, False, False),
    ],
    "orders": [
        ("order_id", "INTEGER", False, True, False),
        ("order_ref", "TEXT", True, False, False),
        ("channel", "TEXT", True, False, False),
        ("status", "TEXT", True, False, False),
        ("purchased_at", "TEXT", True, False, False),
    ],
    "order_items": [
        ("order_item_id", "INTEGER", False, True, False),
        ("order_id", "INTEGER", True, False, False),
        ("tier_id", "INTEGER", True, False, False),
        ("quantity", "INTEGER", True, False, False),
        ("unit_price_cents", "INTEGER", True, False, False),
        ("line_gross_cents", "INTEGER", True, False, True),
    ],
    "refunds": [
        ("refund_id", "INTEGER", False, True, False),
        ("order_item_id", "INTEGER", True, False, False),
        ("refunded_qty", "INTEGER", True, False, False),
        ("refund_amount_cents", "INTEGER", True, False, False),
        ("refunded_at", "TEXT", True, False, False),
        ("reason", "TEXT", True, False, False),
    ],
}

_HIDDEN_NORMAL = 0
_HIDDEN_GENERATED_STORED = 3


def _xinfo(
    connection: sqlite3.Connection, table: str
) -> dict[str, tuple[str, int, int, int]]:
    """Map column name -> (declared_type, notnull, pk, hidden)."""
    return {
        row[1]: (row[2], row[3], row[5], row[6])
        for row in connection.execute(f"PRAGMA table_xinfo({table})")
    }


def test_all_expected_tables_are_covered() -> None:
    assert set(EXPECTED_COLUMNS) == {
        "venues",
        "events",
        "ticket_tiers",
        "orders",
        "order_items",
        "refunds",
    }


def test_column_contracts_match_declared_schema(connection: sqlite3.Connection) -> None:
    for table, expected_columns in EXPECTED_COLUMNS.items():
        actual = _xinfo(connection, table)
        assert set(actual) == {name for name, *_ in expected_columns}, table
        for name, declared_type, not_null, is_pk, is_generated in expected_columns:
            decl_type, notnull, pk, hidden = actual[name]
            assert decl_type == declared_type, f"{table}.{name} type"
            assert bool(notnull) == not_null, f"{table}.{name} notnull"
            assert bool(pk) == is_pk, f"{table}.{name} pk"
            expected_hidden = (
                _HIDDEN_GENERATED_STORED if is_generated else _HIDDEN_NORMAL
            )
            assert hidden == expected_hidden, f"{table}.{name} generated status"


def test_nullable_columns_accept_null(seeded_event: sqlite3.Connection) -> None:
    # events.attendance is the schema's only nullable column outside PKs.
    seeded_event.execute(
        "INSERT INTO events "
        "(event_id, venue_id, name, category, status, start_local, "
        "capacity, attendance) "
        "VALUES (2, 1, 'Scheduled Event', 'concert', 'scheduled', "
        "'2026-06-01T10:00:00', 500, NULL)"
    )
    row = seeded_event.execute(
        "SELECT attendance FROM events WHERE event_id = 2"
    ).fetchone()
    assert row == (None,)


def test_primary_keys_are_unique_and_required(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO venues (venue_id, name, district, capacity) "
        "VALUES (1, 'A', 'D', 100)"
    )
    try:
        connection.execute(
            "INSERT INTO venues (venue_id, name, district, capacity) "
            "VALUES (1, 'B', 'D', 100)"
        )
        raise AssertionError("duplicate primary key was accepted")
    except sqlite3.IntegrityError:
        pass
