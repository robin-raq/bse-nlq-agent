"""U3: controlled execution of ValidatedSql against the real seeded database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bse_nlq.db import execution as execution_module
from bse_nlq.db.build import build_database
from bse_nlq.db.errors import ExecutionErrorReason, SqlExecutionError
from bse_nlq.db.execution import RawQueryResult, execute_validated_sql
from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database
from bse_nlq.db.schema import apply_schema
from bse_nlq.metadata import load_semantic_metadata, prompt_visible_columns
from bse_nlq.metadata.models import APPLICATION_TABLES
from bse_nlq.sql_policy import validate_sql
from bse_nlq.sql_policy.models import ValidatedSql


@pytest.fixture
def seeded_database(tmp_path: Path) -> ReadOnlyDatabase:
    destination = tmp_path / "app.db"
    build_database(destination)
    with open_readonly_database(destination) as database:
        yield database


@pytest.fixture
def physical_and_visible_columns() -> tuple[frozenset[str], frozenset[tuple[str, str]]]:
    connection = sqlite3.connect(":memory:")
    try:
        apply_schema(connection)
        metadata = load_semantic_metadata(connection)
    finally:
        connection.close()
    physical_columns = frozenset(
        (table_name, column_name)
        for table_name, table in metadata.tables.items()
        for column_name in table.columns
    )
    visible = prompt_visible_columns(metadata)
    visible_columns = frozenset(
        (table, column) for table, columns in visible.items() for column in columns
    )
    return physical_columns, visible_columns


def _validated(
    sql: str,
    physical_and_visible_columns: tuple[frozenset[str], frozenset[tuple[str, str]]],
) -> ValidatedSql:
    physical_columns, visible_columns = physical_and_visible_columns
    return validate_sql(
        sql,
        physical_tables=frozenset(APPLICATION_TABLES),
        physical_columns=physical_columns,
        prompt_visible_columns=visible_columns,
    )


def test_successful_aggregate_query(
    seeded_database: ReadOnlyDatabase,
    physical_and_visible_columns: tuple[frozenset[str], frozenset[tuple[str, str]]],
) -> None:
    sql = """
        SELECT e.name AS event_name, SUM(oi.line_gross_cents) AS gross_revenue_cents
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        GROUP BY e.event_id, e.name
        ORDER BY gross_revenue_cents DESC, e.event_id
        LIMIT 1
    """
    validated = _validated(sql, physical_and_visible_columns)

    result = execute_validated_sql(seeded_database, validated)

    assert isinstance(result, RawQueryResult)
    assert result.columns == ("event_name", "gross_revenue_cents")
    assert result.rows == (("Marsh Hollow Family Field Day", 1_700_000),)


def test_successful_join_query(
    seeded_database: ReadOnlyDatabase,
    physical_and_visible_columns: tuple[frozenset[str], frozenset[tuple[str, str]]],
) -> None:
    sql = """
        SELECT SUM(oi.quantity) AS tickets_sold
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
        JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
        JOIN events e ON e.event_id = tt.event_id
        JOIN venues v ON v.venue_id = e.venue_id
        WHERE v.name = 'Ironworks Music Hall'
    """
    validated = _validated(sql, physical_and_visible_columns)

    result = execute_validated_sql(seeded_database, validated)

    assert result.rows == ((300,),)


def test_row_overflow_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    seeded_database: ReadOnlyDatabase,
    physical_and_visible_columns: tuple[frozenset[str], frozenset[tuple[str, str]]],
) -> None:
    monkeypatch.setattr(execution_module, "_MAX_ROWS", 2)
    validated = _validated("SELECT event_id FROM events", physical_and_visible_columns)

    with pytest.raises(SqlExecutionError) as exc_info:
        execute_validated_sql(seeded_database, validated)

    assert exc_info.value.reason is ExecutionErrorReason.ROW_LIMIT_EXCEEDED


def test_row_limit_boundary_is_not_an_overflow(
    monkeypatch: pytest.MonkeyPatch,
    seeded_database: ReadOnlyDatabase,
    physical_and_visible_columns: tuple[frozenset[str], frozenset[tuple[str, str]]],
) -> None:
    # events has 14 seeded rows; a limit exactly matching the result count
    # must not be treated as an overflow (only exceeding it is).
    monkeypatch.setattr(execution_module, "_MAX_ROWS", 14)
    validated = _validated("SELECT event_id FROM events", physical_and_visible_columns)

    result = execute_validated_sql(seeded_database, validated)

    assert len(result.rows) == 14


def test_column_overflow_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    seeded_database: ReadOnlyDatabase,
    physical_and_visible_columns: tuple[frozenset[str], frozenset[tuple[str, str]]],
) -> None:
    monkeypatch.setattr(execution_module, "_MAX_COLUMNS", 1)
    validated = _validated(
        "SELECT event_id, name FROM events", physical_and_visible_columns
    )

    with pytest.raises(SqlExecutionError) as exc_info:
        execute_validated_sql(seeded_database, validated)

    assert exc_info.value.reason is ExecutionErrorReason.COLUMN_LIMIT_EXCEEDED


def test_opcode_budget_exceeded_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    seeded_database: ReadOnlyDatabase,
    physical_and_visible_columns: tuple[frozenset[str], frozenset[tuple[str, str]]],
) -> None:
    monkeypatch.setattr(execution_module, "_MAX_PROGRESS_CALLS", 0)
    monkeypatch.setattr(execution_module, "_PROGRESS_OPCODE_INTERVAL", 1)
    validated = _validated("SELECT event_id FROM events", physical_and_visible_columns)

    with pytest.raises(SqlExecutionError) as exc_info:
        execute_validated_sql(seeded_database, validated)

    assert exc_info.value.reason is ExecutionErrorReason.EXECUTION_BUDGET_EXCEEDED


def test_callbacks_removed_after_success_do_not_block_a_different_table(
    seeded_database: ReadOnlyDatabase,
    physical_and_visible_columns: tuple[frozenset[str], frozenset[tuple[str, str]]],
) -> None:
    validated = _validated("SELECT event_id FROM events", physical_and_visible_columns)
    execute_validated_sql(seeded_database, validated)

    # If the authorizer from the call above were still attached, it would
    # deny this raw read of a table outside its closed-over referenced_tables.
    rows = list(seeded_database._connection.execute("SELECT order_id FROM orders"))

    assert rows


def test_callbacks_removed_after_failure_do_not_block_a_different_table(
    monkeypatch: pytest.MonkeyPatch,
    seeded_database: ReadOnlyDatabase,
    physical_and_visible_columns: tuple[frozenset[str], frozenset[tuple[str, str]]],
) -> None:
    monkeypatch.setattr(execution_module, "_MAX_ROWS", 0)
    validated = _validated("SELECT event_id FROM events", physical_and_visible_columns)

    with pytest.raises(SqlExecutionError):
        execute_validated_sql(seeded_database, validated)

    # Cleanup runs in `finally`, so a failure must not leave stale callbacks
    # attached to the connection either.
    rows = list(seeded_database._connection.execute("SELECT order_id FROM orders"))

    assert rows


def test_rejects_non_validated_sql_input(seeded_database: ReadOnlyDatabase) -> None:
    with pytest.raises(TypeError):
        execute_validated_sql(seeded_database, "SELECT 1")  # type: ignore[arg-type]
