"""Object-inventory contract tests for the applied schema.

Proves apply_schema creates exactly the approved objects: six STRICT tables,
no views, no triggers, the approved indexes, and correctly classified
generated columns.
"""

import sqlite3

APPLICATION_TABLES = (
    "venues",
    "events",
    "ticket_tiers",
    "orders",
    "order_items",
    "refunds",
)

APPROVED_INDEXES = {
    "idx_events_event_date": "events",
    "idx_events_venue_id": "events",
    "idx_events_category": "events",
    "idx_events_status": "events",
    "idx_ticket_tiers_event_id": "ticket_tiers",
    "idx_order_items_tier_id": "order_items",
    "idx_order_items_order_id": "order_items",
    "idx_orders_purchased_at": "orders",
    "idx_orders_status": "orders",
    "idx_refunds_order_item_id": "refunds",
}

# SQLite table_xinfo "hidden" classification codes.
_HIDDEN_NORMAL = 0
_HIDDEN_GENERATED_STORED = 3


def _application_object_names(connection: sqlite3.Connection, kind: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
        (kind,),
    )
    return {row[0] for row in rows}


def test_exactly_six_application_tables(connection: sqlite3.Connection) -> None:
    assert _application_object_names(connection, "table") == set(APPLICATION_TABLES)


def test_all_application_tables_are_strict(connection: sqlite3.Connection) -> None:
    for table in APPLICATION_TABLES:
        options = connection.execute(
            "SELECT strict FROM pragma_table_list WHERE name = ?", (table,)
        ).fetchone()
        assert options is not None
        assert options[0] == 1, f"{table} is not STRICT"


def test_no_application_views(connection: sqlite3.Connection) -> None:
    assert _application_object_names(connection, "view") == set()


def test_no_triggers(connection: sqlite3.Connection) -> None:
    assert _application_object_names(connection, "trigger") == set()


def test_approved_indexes_exist(connection: sqlite3.Connection) -> None:
    # sqlite_autoindex_* names are already excluded by the sqlite_% filter.
    existing = _application_object_names(connection, "index")
    assert existing == set(APPROVED_INDEXES)
    for index_name, table in APPROVED_INDEXES.items():
        row = connection.execute(
            "SELECT tbl_name FROM sqlite_master WHERE type = 'index' AND name = ?",
            (index_name,),
        ).fetchone()
        assert row == (table,)


def test_events_event_date_is_generated_stored(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]: row[6] for row in connection.execute("PRAGMA table_xinfo(events)")
    }
    assert columns["event_date"] == _HIDDEN_GENERATED_STORED
    assert columns["start_local"] == _HIDDEN_NORMAL


def test_order_items_line_gross_is_generated_stored(
    connection: sqlite3.Connection,
) -> None:
    columns = {
        row[1]: row[6] for row in connection.execute("PRAGMA table_xinfo(order_items)")
    }
    assert columns["line_gross_cents"] == _HIDDEN_GENERATED_STORED
    assert columns["unit_price_cents"] == _HIDDEN_NORMAL
    assert columns["quantity"] == _HIDDEN_NORMAL


def test_no_other_generated_columns(connection: sqlite3.Connection) -> None:
    for table in APPLICATION_TABLES:
        for row in connection.execute(f"PRAGMA table_xinfo({table})"):
            column_name, hidden = row[1], row[6]
            if table == "events" and column_name == "event_date":
                continue
            if table == "order_items" and column_name == "line_gross_cents":
                continue
            assert hidden == _HIDDEN_NORMAL, (
                f"{table}.{column_name} unexpectedly generated"
            )
