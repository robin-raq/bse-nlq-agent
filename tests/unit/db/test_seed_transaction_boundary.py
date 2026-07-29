"""Transaction-boundary contract tests for load_seed_data."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

import bse_nlq.db.seed_data as seed_data_mod
from bse_nlq.db.seed import load_seed_data
from bse_nlq.db.seed_data import EXPECTED_ROW_COUNTS, TOTAL_SEED_ROWS

_ACTIVE_TXN_MESSAGE = "load_seed_data requires a connection with no active transaction"
_FK_DISABLED_MESSAGE = "load_seed_data requires PRAGMA foreign_keys to be enabled"

APPLICATION_TABLES = {
    "venues",
    "events",
    "ticket_tiers",
    "orders",
    "order_items",
    "refunds",
}


class _InterruptLike(BaseException):
    """Deterministic BaseException stand-in for interrupt-style failures."""


class _BoomAfter[T]:
    """Yield ``after`` rows, then raise ``exc`` (non-SQLite failure injection)."""

    def __init__(self, rows: tuple[T, ...], *, after: int, exc: BaseException) -> None:
        self._rows = rows
        self._after = after
        self._exc = exc
        self._seen = 0

    def __iter__(self) -> Iterator[T]:
        for row in self._rows:
            self._seen += 1
            if self._seen > self._after:
                raise self._exc
            yield row


def _row_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in APPLICATION_TABLES
    }


def _application_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        name
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def test_seed_load_succeeds_after_schema(
    connection: sqlite3.Connection,
) -> None:
    load_seed_data(connection)
    assert sum(_row_counts(connection).values()) == TOTAL_SEED_ROWS
    assert connection.in_transaction is False
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_active_caller_transaction_is_rejected(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("CREATE TABLE scratch (value INTEGER)")
    connection.commit()
    connection.execute("INSERT INTO scratch (value) VALUES (42)")
    assert connection.in_transaction is True

    with pytest.raises(sqlite3.ProgrammingError, match=_ACTIVE_TXN_MESSAGE):
        load_seed_data(connection)

    assert connection.in_transaction is True
    assert connection.execute("SELECT value FROM scratch").fetchone() == (42,)
    assert all(count == 0 for count in _row_counts(connection).values())

    connection.rollback()
    assert connection.in_transaction is False
    assert connection.execute("SELECT value FROM scratch").fetchone() is None


def test_second_load_raises_and_leaves_seed_intact(
    seeded_connection: sqlite3.Connection,
) -> None:
    counts_before = _row_counts(seeded_connection)
    with pytest.raises(sqlite3.IntegrityError):
        load_seed_data(seeded_connection)
    assert seeded_connection.in_transaction is False
    assert _row_counts(seeded_connection) == counts_before
    assert counts_before == EXPECTED_ROW_COUNTS
    assert seeded_connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    seeded_connection.execute(
        "INSERT INTO venues (venue_id, name, district, capacity) "
        "VALUES (99, 'Temp Venue', 'Temp', 10)"
    )
    assert seeded_connection.execute(
        "SELECT name FROM venues WHERE venue_id = 99"
    ).fetchone() == ("Temp Venue",)


def test_mid_load_failure_rolls_back_partial_seed(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Fail on the first refund FK after earlier tables would otherwise insert.
    monkeypatch.setattr(
        seed_data_mod,
        "REFUNDS",
        ((1, 999, 1, 100, "2026-01-01T10:00:00", "customer_request"),),
    )
    with pytest.raises(sqlite3.IntegrityError):
        load_seed_data(connection)

    assert connection.in_transaction is False
    assert all(count == 0 for count in _row_counts(connection).values())
    assert _application_tables(connection) == APPLICATION_TABLES

    monkeypatch.undo()
    load_seed_data(connection)
    assert sum(_row_counts(connection).values()) == TOTAL_SEED_ROWS


def test_non_sqlite_exception_rolls_back_partial_seed(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boom = RuntimeError("seed boom after first event")
    monkeypatch.setattr(
        seed_data_mod,
        "EVENTS",
        _BoomAfter(seed_data_mod.EVENTS, after=1, exc=boom),
    )
    with pytest.raises(RuntimeError, match="seed boom after first event"):
        load_seed_data(connection)

    assert connection.in_transaction is False
    assert all(count == 0 for count in _row_counts(connection).values())
    assert _application_tables(connection) == APPLICATION_TABLES

    monkeypatch.undo()
    load_seed_data(connection)
    assert sum(_row_counts(connection).values()) == TOTAL_SEED_ROWS
    assert connection.in_transaction is False


def test_baseexception_rolls_back_partial_seed(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boom = _InterruptLike("interrupt after first event")
    monkeypatch.setattr(
        seed_data_mod,
        "EVENTS",
        _BoomAfter(seed_data_mod.EVENTS, after=1, exc=boom),
    )
    with pytest.raises(_InterruptLike, match="interrupt after first event"):
        load_seed_data(connection)

    assert connection.in_transaction is False
    assert all(count == 0 for count in _row_counts(connection).values())
    assert _application_tables(connection) == APPLICATION_TABLES

    monkeypatch.undo()
    load_seed_data(connection)
    assert sum(_row_counts(connection).values()) == TOTAL_SEED_ROWS


def test_foreign_keys_disabled_is_rejected(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("PRAGMA foreign_keys = OFF")
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (0,)

    with pytest.raises(sqlite3.ProgrammingError, match=_FK_DISABLED_MESSAGE):
        load_seed_data(connection)

    assert connection.in_transaction is False
    assert all(count == 0 for count in _row_counts(connection).values())
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (0,)
    assert _application_tables(connection) == APPLICATION_TABLES

    connection.execute("PRAGMA foreign_keys = ON")
    load_seed_data(connection)
    assert sum(_row_counts(connection).values()) == TOTAL_SEED_ROWS


def test_load_seed_data_is_importable() -> None:
    from bse_nlq.db.seed import load_seed_data as api

    assert callable(api)
