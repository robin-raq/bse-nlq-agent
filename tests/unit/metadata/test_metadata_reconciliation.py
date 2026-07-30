"""Schema reconciliation and drift tests for semantic metadata."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from bse_nlq.metadata import (
    MetadataReconciliationError,
    MetadataValidationError,
    load_metadata_document,
    load_semantic_metadata,
    reconcile_metadata,
    validate_metadata_document,
)
from bse_nlq.metadata.reconcile import (
    REQUIRED_GENERATED_COLUMNS,
    introspect_foreign_keys,
    introspect_generated_columns,
)


def test_reconciliation_covers_exactly_six_tables(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    assert set(metadata.tables) == {
        "venues",
        "events",
        "ticket_tiers",
        "orders",
        "order_items",
        "refunds",
    }


def test_every_physical_column_has_metadata(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    for table_name, table in metadata.tables.items():
        physical = {
            row[1]
            for row in seeded_connection.execute(f"PRAGMA table_xinfo({table_name})")
        }
        assert set(table.columns) == physical


def test_prompt_visibility_inventory_after_reconciliation(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    for table_name, table in metadata.tables.items():
        for column_name, column in table.columns.items():
            if table_name == "orders" and column_name == "order_ref":
                assert column.in_prompt is False
            else:
                assert column.in_prompt is True


def test_generated_columns_identified_via_introspection(
    seeded_connection: sqlite3.Connection,
) -> None:
    generated = introspect_generated_columns(seeded_connection)
    assert REQUIRED_GENERATED_COLUMNS <= generated
    load_semantic_metadata(seeded_connection)


def test_join_guidance_exactly_matches_foreign_keys(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    fk_edges = introspect_foreign_keys(seeded_connection)
    guided = {
        (
            guide.from_table,
            guide.from_column,
            guide.to_table,
            guide.to_column,
        )
        for guide in metadata.join_guidance
    }
    assert guided == fk_edges
    assert len(guided) == 5


def test_order_ref_excluded_after_reconciliation(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    assert metadata.column("orders", "order_ref").in_prompt is False


def test_drift_renamed_required_column_fails_validation(
    mutable_metadata_dict: dict[str, Any],
) -> None:
    columns = mutable_metadata_dict["tables"]["venues"]["columns"]
    columns["capacity_renamed"] = columns.pop("capacity")
    with pytest.raises(
        MetadataValidationError, match="missing required semantic columns"
    ):
        validate_metadata_document(mutable_metadata_dict)


def test_drift_renamed_physical_column_fails_reconciliation(
    seeded_connection: sqlite3.Connection,
    mutable_metadata_dict: dict[str, Any],
) -> None:
    columns = mutable_metadata_dict["tables"]["venues"]["columns"]
    columns["venue_id_renamed"] = columns.pop("venue_id")
    metadata = validate_metadata_document(mutable_metadata_dict)
    with pytest.raises(MetadataReconciliationError, match="nonexistent columns"):
        reconcile_metadata(metadata, seeded_connection)


def test_drift_invented_metadata_column_fails_reconciliation(
    seeded_connection: sqlite3.Connection,
    mutable_metadata_dict: dict[str, Any],
) -> None:
    mutable_metadata_dict["tables"]["venues"]["columns"]["invented_column"] = {
        "description": "not real",
        "in_prompt": True,
    }
    metadata = validate_metadata_document(mutable_metadata_dict)
    with pytest.raises(MetadataReconciliationError, match="nonexistent columns"):
        reconcile_metadata(metadata, seeded_connection)


def test_missing_physical_column_metadata_fails_reconciliation(
    seeded_connection: sqlite3.Connection,
    mutable_metadata_dict: dict[str, Any],
) -> None:
    del mutable_metadata_dict["tables"]["venues"]["columns"]["venue_id"]
    metadata = validate_metadata_document(mutable_metadata_dict)
    with pytest.raises(MetadataReconciliationError, match="missing physical columns"):
        reconcile_metadata(metadata, seeded_connection)


def test_drift_changed_table_identifier_fails_validation(
    mutable_metadata_dict: dict[str, Any],
) -> None:
    tables = mutable_metadata_dict["tables"]
    tables["venuez"] = tables.pop("venues")
    with pytest.raises(MetadataValidationError, match="tables"):
        validate_metadata_document(mutable_metadata_dict)


def test_drift_removed_required_column_fails_validation(
    mutable_metadata_dict: dict[str, Any],
) -> None:
    del mutable_metadata_dict["tables"]["events"]["columns"]["attendance"]
    with pytest.raises(
        MetadataValidationError, match="missing required semantic columns"
    ):
        validate_metadata_document(mutable_metadata_dict)


def test_empty_join_guidance_fails_reconciliation(
    seeded_connection: sqlite3.Connection,
    mutable_metadata_dict: dict[str, Any],
) -> None:
    mutable_metadata_dict["join_guidance"] = []
    metadata = validate_metadata_document(mutable_metadata_dict)
    with pytest.raises(
        MetadataReconciliationError, match="join_guidance must not be empty"
    ):
        reconcile_metadata(metadata, seeded_connection)


def test_missing_fk_join_fails_reconciliation(
    seeded_connection: sqlite3.Connection,
    mutable_metadata_dict: dict[str, Any],
) -> None:
    mutable_metadata_dict["join_guidance"] = [
        entry
        for entry in mutable_metadata_dict["join_guidance"]
        if not (entry["from_table"] == "events" and entry["from_column"] == "venue_id")
    ]
    metadata = validate_metadata_document(mutable_metadata_dict)
    with pytest.raises(
        MetadataReconciliationError, match="missing physical foreign keys"
    ):
        reconcile_metadata(metadata, seeded_connection)


def test_invented_join_fails_reconciliation(
    seeded_connection: sqlite3.Connection,
    mutable_metadata_dict: dict[str, Any],
) -> None:
    mutable_metadata_dict["join_guidance"].append(
        {
            "from_table": "events",
            "from_column": "venue_id",
            "to_table": "orders",
            "to_column": "order_id",
            "note": "invented relationship",
        }
    )
    metadata = validate_metadata_document(mutable_metadata_dict)
    with pytest.raises(MetadataReconciliationError, match="not physical foreign keys"):
        reconcile_metadata(metadata, seeded_connection)


def test_reversed_join_fails_reconciliation(
    seeded_connection: sqlite3.Connection,
    mutable_metadata_dict: dict[str, Any],
) -> None:
    for entry in mutable_metadata_dict["join_guidance"]:
        if entry["from_table"] == "events" and entry["from_column"] == "venue_id":
            entry["from_table"], entry["to_table"] = (
                entry["to_table"],
                entry["from_table"],
            )
            entry["from_column"], entry["to_column"] = (
                entry["to_column"],
                entry["from_column"],
            )
            break
    metadata = validate_metadata_document(mutable_metadata_dict)
    with pytest.raises(MetadataReconciliationError, match="join_guidance"):
        reconcile_metadata(metadata, seeded_connection)


def test_complete_join_guidance_passes(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_metadata_document()
    reconcile_metadata(metadata, seeded_connection)


def test_reconciliation_does_not_mutate_connection_schema(
    seeded_connection: sqlite3.Connection,
) -> None:
    before = seeded_connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    first = load_semantic_metadata(seeded_connection)
    second = load_semantic_metadata(seeded_connection)
    after = seeded_connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    assert before == after
    assert first.tables is not second.tables


_ORDINARY_ANALYTICAL_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE venues (
    venue_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    district TEXT NOT NULL,
    capacity INTEGER NOT NULL
) STRICT;
CREATE TABLE events (
    event_id INTEGER PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(venue_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    start_local TEXT NOT NULL,
    event_date TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    attendance INTEGER
) STRICT;
CREATE TABLE ticket_tiers (
    tier_id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(event_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    tier_name TEXT NOT NULL,
    face_value_cents INTEGER NOT NULL
) STRICT;
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    order_ref TEXT NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    purchased_at TEXT NOT NULL
) STRICT;
CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    tier_id INTEGER NOT NULL REFERENCES ticket_tiers(tier_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    quantity INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    line_gross_cents INTEGER NOT NULL
) STRICT;
CREATE TABLE refunds (
    refund_id INTEGER PRIMARY KEY,
    order_item_id INTEGER NOT NULL REFERENCES order_items(order_item_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    refunded_qty INTEGER NOT NULL,
    refund_amount_cents INTEGER NOT NULL,
    refunded_at TEXT NOT NULL,
    reason TEXT NOT NULL
) STRICT;
"""


@pytest.mark.parametrize(
    "missing_pair",
    sorted(REQUIRED_GENERATED_COLUMNS),
)
def test_generated_column_regression_detected(
    missing_pair: tuple[str, str],
) -> None:
    """Isolated six-table schema where analytical columns are ordinary, not STORED."""
    table, column = missing_pair
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(_ORDINARY_ANALYTICAL_SCHEMA)
        generated = introspect_generated_columns(connection)
        assert (table, column) not in generated
        assert generated == set()
        metadata = load_metadata_document()
        with pytest.raises(
            MetadataReconciliationError,
            match="expected generated columns missing from introspection",
        ):
            reconcile_metadata(metadata, connection)
    finally:
        connection.close()
