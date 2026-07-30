"""Reconcile semantic metadata references against SQLite introspection."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from bse_nlq.metadata.errors import MetadataReconciliationError
from bse_nlq.metadata.freeze import freeze_mapping
from bse_nlq.metadata.models import (
    APPLICATION_TABLES,
    REQUIRED_SEMANTIC_COLUMNS,
    SemanticMetadata,
)

_SQLITE_MASTER_APP_FILTER = (
    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
)

REQUIRED_GENERATED_COLUMNS: frozenset[tuple[str, str]] = frozenset(
    {
        ("events", "event_date"),
        ("order_items", "line_gross_cents"),
    }
)

PROMPT_EXCLUDED_COLUMNS: frozenset[tuple[str, str]] = frozenset(
    {("orders", "order_ref")}
)


def introspect_application_tables(
    connection: sqlite3.Connection,
) -> dict[str, set[str]]:
    """Return application table names mapped to their physical column names."""
    rows = connection.execute(_SQLITE_MASTER_APP_FILTER).fetchall()
    tables = {row[0] for row in rows}
    result: dict[str, set[str]] = {}
    for table in tables:
        columns = {row[1] for row in connection.execute(f"PRAGMA table_xinfo({table})")}
        result[table] = columns
    return result


def introspect_foreign_keys(
    connection: sqlite3.Connection,
) -> set[tuple[str, str, str, str]]:
    """Return FK edges as (from_table, from_column, to_table, to_column)."""
    edges: set[tuple[str, str, str, str]] = set()
    tables = {
        row[0] for row in connection.execute(_SQLITE_MASTER_APP_FILTER).fetchall()
    }
    for table in tables:
        for row in connection.execute(f"PRAGMA foreign_key_list({table})"):
            # row: id, seq, table, from, to, on_update, on_delete, match
            edges.add((table, row[3], row[2], row[4]))
    return edges


def introspect_generated_columns(
    connection: sqlite3.Connection,
) -> set[tuple[str, str]]:
    """Return (table, column) pairs classified as STORED generated columns."""
    generated: set[tuple[str, str]] = set()
    tables = {
        row[0] for row in connection.execute(_SQLITE_MASTER_APP_FILTER).fetchall()
    }
    for table in tables:
        for row in connection.execute(f"PRAGMA table_xinfo({table})"):
            # hidden == 3 => GENERATED ALWAYS STORED
            if row[6] == 3:
                generated.add((table, row[1]))
    return generated


def reconcile_metadata(
    metadata: SemanticMetadata,
    connection: sqlite3.Connection,
) -> None:
    """Fail closed when metadata diverges from SQLite physical structure.

    SQLite introspection owns tables, columns, keys, types, nullability, and
    generated-column status. Metadata must cover every physical application
    column, enforce the frozen prompt-visibility policy, and provide join
    guidance that exactly matches introspected foreign keys.
    """
    physical = introspect_application_tables(connection)
    physical_tables = set(physical)
    expected_tables = set(APPLICATION_TABLES)

    if physical_tables != expected_tables:
        raise MetadataReconciliationError(
            "physical application tables diverge from expected six-table set: "
            f"physical={sorted(physical_tables)} expected={sorted(expected_tables)}"
        )

    meta_tables = set(metadata.tables)
    if meta_tables != expected_tables:
        raise MetadataReconciliationError(
            "metadata tables diverge from expected six-table set: "
            f"metadata={sorted(meta_tables)} expected={sorted(expected_tables)}"
        )

    for table_name, table_meta in metadata.tables.items():
        physical_columns = physical[table_name]
        referenced = set(table_meta.columns)
        unknown = referenced - physical_columns
        if unknown:
            raise MetadataReconciliationError(
                f"metadata references nonexistent columns on {table_name}: "
                + ", ".join(sorted(unknown))
            )
        missing = physical_columns - referenced
        if missing:
            raise MetadataReconciliationError(
                f"metadata missing physical columns on {table_name}: "
                + ", ".join(sorted(missing))
            )
        # Fail closed on Meta?=yes gaps even if a future physical rename drifts.
        required = REQUIRED_SEMANTIC_COLUMNS[table_name]
        missing_required = required - referenced
        if missing_required:
            raise MetadataReconciliationError(
                f"metadata missing required semantic coverage on {table_name}: "
                + ", ".join(sorted(missing_required))
            )
        for column_name, column in table_meta.columns.items():
            excluded = (table_name, column_name) in PROMPT_EXCLUDED_COLUMNS
            if excluded and column.in_prompt:
                raise MetadataReconciliationError(
                    f"{table_name}.{column_name} must be prompt-excluded"
                )
            if not excluded and not column.in_prompt:
                raise MetadataReconciliationError(
                    f"{table_name}.{column_name} must remain prompt-visible; "
                    "only orders.order_ref may be excluded"
                )

    _assert_join_guidance_exact(metadata, connection)
    _assert_required_generated_columns(connection)


def _assert_join_guidance_exact(
    metadata: SemanticMetadata,
    connection: sqlite3.Connection,
) -> None:
    fk_edges = introspect_foreign_keys(connection)
    guided = {
        (
            guide.from_table,
            guide.from_column,
            guide.to_table,
            guide.to_column,
        )
        for guide in metadata.join_guidance
    }
    if not guided:
        raise MetadataReconciliationError("join_guidance must not be empty")
    missing = fk_edges - guided
    if missing:
        raise MetadataReconciliationError(
            "join_guidance missing physical foreign keys: "
            + ", ".join(f"{a}.{b}->{c}.{d}" for a, b, c, d in sorted(missing))
        )
    extra = guided - fk_edges
    if extra:
        raise MetadataReconciliationError(
            "join_guidance includes relationships that are not physical "
            "foreign keys: "
            + ", ".join(f"{a}.{b}->{c}.{d}" for a, b, c, d in sorted(extra))
        )


def _assert_required_generated_columns(connection: sqlite3.Connection) -> None:
    generated = introspect_generated_columns(connection)
    missing = REQUIRED_GENERATED_COLUMNS - generated
    if missing:
        raise MetadataReconciliationError(
            "expected generated columns missing from introspection: "
            + ", ".join(f"{t}.{c}" for t, c in sorted(missing))
        )


def prompt_visible_columns(
    metadata: SemanticMetadata,
) -> Mapping[str, frozenset[str]]:
    """Return prompt-visible columns grouped by table."""
    return freeze_mapping(
        {
            table_name: frozenset(
                column.name for column in table.columns.values() if column.in_prompt
            )
            for table_name, table in metadata.tables.items()
        }
    )


def prompt_excluded_columns(
    metadata: SemanticMetadata,
) -> Mapping[str, frozenset[str]]:
    """Return prompt-excluded columns grouped by table."""
    return freeze_mapping(
        {
            table_name: frozenset(
                column.name for column in table.columns.values() if not column.in_prompt
            )
            for table_name, table in metadata.tables.items()
        }
    )
