"""Transaction-boundary contract tests for apply_schema.

apply_schema must never commit, roll back, or otherwise disturb a caller's
pending uncommitted work: it refuses to run against a connection that
already has an active transaction, applies the DDL as its own transaction,
and always leaves the connection with no open transaction -- whether it
succeeds or fails.
"""

import sqlite3

import pytest

import bse_nlq.db.schema as schema_mod
from bse_nlq.db.schema import apply_schema

APPLICATION_TABLES = {
    "venues",
    "events",
    "ticket_tiers",
    "orders",
    "order_items",
    "refunds",
}

_ACTIVE_TXN_MESSAGE = "apply_schema requires a connection with no active transaction"

# Intentionally broken DDL: creates one approved table, then fails so the
# schema-owned transaction must roll back the partial object.
_PARTIAL_THEN_FAIL_SQL = """
BEGIN;

CREATE TABLE venues (
    venue_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (length(name) > 0),
    district TEXT NOT NULL CHECK (length(district) > 0),
    capacity INTEGER NOT NULL CHECK (capacity > 0)
) STRICT;

CREATE TABLE events (this is not valid DDL);

COMMIT;
"""


def _application_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        name
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _application_indexes(connection: sqlite3.Connection) -> set[str]:
    return {
        name
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
        )
    }


def test_success_leaves_no_open_transaction(
    raw_connection: sqlite3.Connection,
) -> None:
    apply_schema(raw_connection)
    assert raw_connection.in_transaction is False


def test_success_reports_foreign_keys_enabled(
    raw_connection: sqlite3.Connection,
) -> None:
    apply_schema(raw_connection)
    assert raw_connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_success_creates_all_six_tables(
    raw_connection: sqlite3.Connection,
) -> None:
    apply_schema(raw_connection)
    assert _application_tables(raw_connection) == APPLICATION_TABLES


def test_active_caller_transaction_is_rejected(
    raw_connection: sqlite3.Connection,
) -> None:
    raw_connection.execute("CREATE TABLE scratch (value INTEGER)")
    raw_connection.commit()
    raw_connection.execute("INSERT INTO scratch (value) VALUES (42)")
    assert raw_connection.in_transaction is True

    with pytest.raises(sqlite3.ProgrammingError, match=_ACTIVE_TXN_MESSAGE):
        apply_schema(raw_connection)


def test_rejected_call_leaves_callers_transaction_untouched(
    raw_connection: sqlite3.Connection,
) -> None:
    raw_connection.execute("CREATE TABLE scratch (value INTEGER)")
    raw_connection.commit()
    raw_connection.execute("INSERT INTO scratch (value) VALUES (42)")
    assert raw_connection.in_transaction is True

    with pytest.raises(sqlite3.ProgrammingError, match=_ACTIVE_TXN_MESSAGE):
        apply_schema(raw_connection)

    # Still open: apply_schema neither committed nor rolled the caller back.
    assert raw_connection.in_transaction is True
    assert raw_connection.execute("SELECT value FROM scratch").fetchone() == (42,)
    assert _application_tables(raw_connection) == {"scratch"}

    # Explicit rollback removes the pending row, proving it was never
    # committed. The committed scratch table itself remains.
    raw_connection.rollback()
    assert raw_connection.in_transaction is False
    assert raw_connection.execute("SELECT value FROM scratch").fetchone() is None
    assert _application_tables(raw_connection) == {"scratch"}


def test_applying_schema_twice_raises_cleanly(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.OperationalError):
        apply_schema(connection)


def test_failed_second_application_leaves_no_open_transaction(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.OperationalError):
        apply_schema(connection)
    assert connection.in_transaction is False


def test_failed_second_application_leaves_original_tables_intact(
    connection: sqlite3.Connection,
) -> None:
    indexes_before = _application_indexes(connection)
    with pytest.raises(sqlite3.OperationalError):
        apply_schema(connection)
    assert _application_tables(connection) == APPLICATION_TABLES
    assert _application_indexes(connection) == indexes_before


def test_failed_second_application_keeps_foreign_keys_enabled(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.OperationalError):
        apply_schema(connection)
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_failed_second_application_connection_remains_usable(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.OperationalError):
        apply_schema(connection)
    connection.execute(
        "INSERT INTO venues (venue_id, name, district, capacity) "
        "VALUES (1, 'Usable Venue', 'Harbor', 100)"
    )
    assert connection.execute("SELECT name FROM venues").fetchone() == ("Usable Venue",)


def test_schema_owned_failure_rolls_back_partial_ddl(
    raw_connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(schema_mod, "_SCHEMA_SQL", _PARTIAL_THEN_FAIL_SQL)

    with pytest.raises(sqlite3.Error):
        apply_schema(raw_connection)

    assert raw_connection.in_transaction is False
    assert _application_tables(raw_connection) == set()
    assert raw_connection.execute("PRAGMA foreign_keys").fetchone() == (1,)

    # Restore the real schema SQL and prove the connection remains usable.
    monkeypatch.undo()
    apply_schema(raw_connection)
    assert _application_tables(raw_connection) == APPLICATION_TABLES


class _InterruptLike(BaseException):
    """Deterministic BaseException stand-in for interrupt-style failures."""


class _BoomAfterVenuesConnection:
    """Proxy that fails after creating venues inside executescript."""

    def __init__(self, real: sqlite3.Connection, exc: BaseException) -> None:
        self._real = real
        self._exc = exc

    def executescript(self, _sql: str) -> None:
        self._real.execute("BEGIN")
        self._real.execute(
            "CREATE TABLE venues ("
            "venue_id INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL UNIQUE CHECK (length(name) > 0), "
            "district TEXT NOT NULL CHECK (length(district) > 0), "
            "capacity INTEGER NOT NULL CHECK (capacity > 0)"
            ") STRICT"
        )
        raise self._exc

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


def test_non_sqlite_exception_rolls_back_partial_schema(
    raw_connection: sqlite3.Connection,
) -> None:
    """A non-SQLite failure after the schema txn begins must not leave objects."""
    proxy = _BoomAfterVenuesConnection(
        raw_connection, RuntimeError("schema boom after venues")
    )

    with pytest.raises(RuntimeError, match="schema boom after venues"):
        apply_schema(proxy)  # type: ignore[arg-type]

    assert raw_connection.in_transaction is False
    assert _application_tables(raw_connection) == set()
    assert raw_connection.execute("PRAGMA foreign_keys").fetchone() == (1,)

    apply_schema(raw_connection)
    assert _application_tables(raw_connection) == APPLICATION_TABLES


def test_baseexception_rolls_back_partial_schema(
    raw_connection: sqlite3.Connection,
) -> None:
    proxy = _BoomAfterVenuesConnection(
        raw_connection, _InterruptLike("schema interrupt after venues")
    )

    with pytest.raises(_InterruptLike, match="schema interrupt after venues"):
        apply_schema(proxy)  # type: ignore[arg-type]

    assert raw_connection.in_transaction is False
    assert _application_tables(raw_connection) == set()

    apply_schema(raw_connection)
    assert _application_tables(raw_connection) == APPLICATION_TABLES
