"""U3: default-deny SQLite authorizer, tried against direct adversarial input.

These tests hand-construct ``ValidatedSql`` with malicious ``original_sql``,
bypassing ``validate_sql`` entirely, to prove the authorizer independently
enforces safety at the SQLite level rather than only trusting the static
policy that would ordinarily produce this object.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bse_nlq.db.build import build_database
from bse_nlq.db.errors import ExecutionErrorReason, SqlExecutionError
from bse_nlq.db.execution import execute_validated_sql
from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database
from bse_nlq.sql_policy.models import ValidatedSql


@pytest.fixture
def seeded_database(tmp_path: Path) -> ReadOnlyDatabase:
    destination = tmp_path / "app.db"
    build_database(destination)
    with open_readonly_database(destination) as database:
        yield database


def _adversarial(
    sql: str,
    *,
    referenced_tables: frozenset[str] = frozenset(),
    referenced_columns: frozenset[tuple[str, str]] = frozenset(),
) -> ValidatedSql:
    return ValidatedSql(
        original_sql=sql,
        normalized_sql=sql,
        fingerprint="test-fingerprint",
        referenced_tables=referenced_tables,
        referenced_columns=referenced_columns,
        referenced_functions=frozenset(),
    )


def _denied_reason(
    database: ReadOnlyDatabase, validated: ValidatedSql
) -> ExecutionErrorReason:
    with pytest.raises(SqlExecutionError) as exc_info:
        execute_validated_sql(database, validated)
    return exc_info.value.reason


def test_write_is_denied(seeded_database: ReadOnlyDatabase) -> None:
    validated = _adversarial(
        "INSERT INTO events (event_id) VALUES (999)",
        referenced_tables=frozenset({"events"}),
    )

    assert _denied_reason(seeded_database, validated) is (
        ExecutionErrorReason.AUTHORIZATION_DENIED
    )


def test_pragma_is_denied(seeded_database: ReadOnlyDatabase) -> None:
    validated = _adversarial("PRAGMA table_info(events)")

    assert _denied_reason(seeded_database, validated) is (
        ExecutionErrorReason.AUTHORIZATION_DENIED
    )


def test_attach_is_denied(seeded_database: ReadOnlyDatabase, tmp_path: Path) -> None:
    other = tmp_path / "other.db"
    validated = _adversarial(f"ATTACH DATABASE '{other}' AS other")

    assert _denied_reason(seeded_database, validated) is (
        ExecutionErrorReason.AUTHORIZATION_DENIED
    )


def test_unauthorized_table_is_denied(seeded_database: ReadOnlyDatabase) -> None:
    # Claims only "events" is authorized but the SQL actually reads "orders".
    validated = _adversarial(
        "SELECT order_id FROM orders", referenced_tables=frozenset({"events"})
    )

    assert _denied_reason(seeded_database, validated) is (
        ExecutionErrorReason.AUTHORIZATION_DENIED
    )


def test_unauthorized_column_is_denied(seeded_database: ReadOnlyDatabase) -> None:
    # The table is authorized but this specific column was never claimed.
    validated = _adversarial(
        "SELECT order_ref FROM orders",
        referenced_tables=frozenset({"orders"}),
        referenced_columns=frozenset({("orders", "order_id")}),
    )

    assert _denied_reason(seeded_database, validated) is (
        ExecutionErrorReason.AUTHORIZATION_DENIED
    )


def test_unauthorized_function_is_denied(seeded_database: ReadOnlyDatabase) -> None:
    # AVG is not in the fixed function allowlist regardless of what the
    # (hand-crafted, untrusted) referenced_functions field might claim.
    validated = _adversarial(
        "SELECT AVG(unit_price_cents) FROM order_items",
        referenced_tables=frozenset({"order_items"}),
        referenced_columns=frozenset({("order_items", "unit_price_cents")}),
    )

    assert _denied_reason(seeded_database, validated) is (
        ExecutionErrorReason.AUTHORIZATION_DENIED
    )


def test_transaction_control_is_denied(seeded_database: ReadOnlyDatabase) -> None:
    validated = _adversarial("BEGIN")

    assert _denied_reason(seeded_database, validated) is (
        ExecutionErrorReason.AUTHORIZATION_DENIED
    )


def test_schema_change_is_denied(seeded_database: ReadOnlyDatabase) -> None:
    validated = _adversarial("DROP TABLE events")

    assert _denied_reason(seeded_database, validated) is (
        ExecutionErrorReason.AUTHORIZATION_DENIED
    )


def test_recursive_cte_is_denied(seeded_database: ReadOnlyDatabase) -> None:
    # Recursive CTEs are already rejected by the static validator (Slice 2);
    # this proves the authorizer independently denies SQLITE_RECURSIVE too,
    # for a hand-crafted ValidatedSql that bypassed that layer.
    validated = _adversarial(
        "WITH RECURSIVE x(n) AS ("
        "SELECT 1 UNION ALL SELECT n + 1 FROM x WHERE n < 5"
        ") SELECT n FROM x"
    )

    assert _denied_reason(seeded_database, validated) is (
        ExecutionErrorReason.AUTHORIZATION_DENIED
    )
