"""Cleanup and closed-state contracts for ReadOnlyDatabase."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bse_nlq.db import runtime as runtime_module
from bse_nlq.db.build import build_database
from bse_nlq.db.errors import DatabaseRuntimeError
from bse_nlq.db.runtime import open_readonly_database


@pytest.fixture
def published_db(tmp_path: Path) -> Path:
    destination = tmp_path / "app.db"
    build_database(destination)
    return destination


def test_closed_wrapper_rejects_connection_access(published_db: Path) -> None:
    db = open_readonly_database(published_db)
    db.close()
    with pytest.raises(DatabaseRuntimeError, match="closed"):
        _ = db._connection


def test_closed_wrapper_rejects_reentry(published_db: Path) -> None:
    db = open_readonly_database(published_db)
    db.close()
    with pytest.raises(DatabaseRuntimeError, match="closed"):
        with db:
            pass


def test_failed_pragma_setup_does_not_leak_connection(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_connect = sqlite3.connect
    connections: list[sqlite3.Connection] = []

    def connect_and_track(*args: object, **kwargs: object) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        connections.append(conn)
        return conn

    real_enable = runtime_module._enable_and_verify_pragma

    def enable_and_maybe_fail(
        connection: sqlite3.Connection,
        name: str,
        *,
        on_sql: str,
    ) -> None:
        if name == "query_only":
            # A genuine SQLite failure, not a bare RuntimeError: a
            # programming defect from this helper must propagate unwrapped
            # instead of being normalized (see
            # test_runtime_exception_boundary.py::
            # test_pragma_setup_runtime_error_propagates_unchanged).
            raise sqlite3.OperationalError("injected query_only failure")
        real_enable(connection, name, on_sql=on_sql)

    monkeypatch.setattr("bse_nlq.db.runtime.sqlite3.connect", connect_and_track)
    monkeypatch.setattr(
        "bse_nlq.db.runtime._enable_and_verify_pragma", enable_and_maybe_fail
    )

    with pytest.raises(DatabaseRuntimeError) as exc_info:
        open_readonly_database(published_db)

    assert isinstance(exc_info.value.__cause__, sqlite3.Error)
    assert connections
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def test_keyboard_interrupt_during_setup_cleans_up_and_reraises(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_connect = sqlite3.connect
    connections: list[sqlite3.Connection] = []

    def connect_and_track(*args: object, **kwargs: object) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        connections.append(conn)
        return conn

    def interrupt(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("bse_nlq.db.runtime.sqlite3.connect", connect_and_track)
    monkeypatch.setattr("bse_nlq.db.runtime._disable_load_extension", interrupt)

    with pytest.raises(KeyboardInterrupt):
        open_readonly_database(published_db)

    assert connections
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def test_system_exit_during_setup_cleans_up_and_reraises(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_connect = sqlite3.connect
    connections: list[sqlite3.Connection] = []

    def connect_and_track(*args: object, **kwargs: object) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        connections.append(conn)
        return conn

    def exit_now(*_args: object, **_kwargs: object) -> None:
        raise SystemExit(7)

    monkeypatch.setattr("bse_nlq.db.runtime.sqlite3.connect", connect_and_track)
    monkeypatch.setattr("bse_nlq.db.runtime._disable_load_extension", exit_now)

    with pytest.raises(SystemExit) as exc_info:
        open_readonly_database(published_db)

    assert exc_info.value.code == 7
    assert connections
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


class _FailingCloseConnection:
    """Stub standing in for a sqlite3 connection whose close() fails."""

    def __init__(self, error: BaseException) -> None:
        self._error = error
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        raise self._error


def test_close_failure_raises_and_does_not_report_success(published_db: Path) -> None:
    """A failed underlying close must not be reported as a closed wrapper."""
    db = open_readonly_database(published_db)
    real_connection = db._raw_connection
    stub = _FailingCloseConnection(sqlite3.OperationalError("injected close failure"))
    db._raw_connection = stub  # type: ignore[assignment]
    try:
        with pytest.raises(DatabaseRuntimeError, match="close") as exc_info:
            db.close()
        assert isinstance(exc_info.value.__cause__, sqlite3.OperationalError)
        assert stub.close_calls == 1
        assert db.closed is False
        # The wrapper is still usable, so the caller can observe and retry.
        assert db.metadata is not None
    finally:
        db._raw_connection = real_connection  # type: ignore[assignment]
        db.close()
    assert db.closed is True


def test_close_failure_is_retryable(published_db: Path) -> None:
    db = open_readonly_database(published_db)
    real_connection = db._raw_connection
    stub = _FailingCloseConnection(sqlite3.OperationalError("injected close failure"))
    db._raw_connection = stub  # type: ignore[assignment]
    with pytest.raises(DatabaseRuntimeError):
        db.close()
    assert db.closed is False
    db._raw_connection = real_connection  # type: ignore[assignment]
    db.close()
    assert db.closed is True
    db.close()
    assert db.closed is True


@pytest.mark.parametrize(
    "defect",
    (
        RuntimeError("internal close bug"),
        MemoryError("resource exhaustion"),
    ),
    ids=("RuntimeError", "MemoryError"),
)
def test_close_programming_and_resource_failures_propagate_unchanged(
    published_db: Path,
    defect: BaseException,
) -> None:
    db = open_readonly_database(published_db)
    real_connection = db._raw_connection
    stub = _FailingCloseConnection(defect)
    db._raw_connection = stub  # type: ignore[assignment]
    try:
        with pytest.raises(type(defect)) as exc_info:
            db.close()
        assert exc_info.value is defect
        assert not isinstance(exc_info.value, DatabaseRuntimeError)
        assert stub.close_calls == 1
        assert db.closed is False
        assert db.metadata is not None
    finally:
        db._raw_connection = real_connection  # type: ignore[assignment]
        db.close()
    assert db.closed is True


@pytest.mark.parametrize(
    "control_flow",
    (SystemExit(3), GeneratorExit()),
    ids=("SystemExit", "GeneratorExit"),
)
def test_control_flow_exceptions_from_close_propagate_unchanged(
    published_db: Path,
    control_flow: BaseException,
) -> None:
    db = open_readonly_database(published_db)
    real_connection = db._raw_connection
    stub = _FailingCloseConnection(control_flow)
    db._raw_connection = stub  # type: ignore[assignment]
    try:
        with pytest.raises(type(control_flow)) as exc_info:
            db.close()
        assert exc_info.value is control_flow
        assert stub.close_calls == 1
        assert db.closed is False
    finally:
        db._raw_connection = real_connection  # type: ignore[assignment]
        db.close()


def test_keyboard_interrupt_from_close_propagates_unwrapped(
    published_db: Path,
) -> None:
    db = open_readonly_database(published_db)
    real_connection = db._raw_connection
    stub = _FailingCloseConnection(KeyboardInterrupt())
    db._raw_connection = stub  # type: ignore[assignment]
    try:
        with pytest.raises(KeyboardInterrupt):
            db.close()
        assert db.closed is False
    finally:
        db._raw_connection = real_connection  # type: ignore[assignment]
        db.close()


def test_database_path_remains_readable_after_close(published_db: Path) -> None:
    """Documented contract: path identity outlives the connection."""
    db = open_readonly_database(published_db)
    path_before = db.database_path
    assert path_before == published_db.resolve()
    db.close()

    assert db.closed is True
    assert db.database_path == path_before

    for name in (
        "metadata",
        "physical_tables",
        "physical_columns",
        "prompt_visible_columns",
        "prompt_excluded_columns",
    ):
        with pytest.raises(DatabaseRuntimeError, match="closed"):
            getattr(db, name)
    with pytest.raises(DatabaseRuntimeError, match="closed"):
        _ = db._connection


def test_load_extension_disabled(published_db: Path) -> None:
    with open_readonly_database(published_db) as db:
        conn = db._connection
        assert hasattr(conn, "enable_load_extension")
        with pytest.raises(sqlite3.OperationalError, match="not authorized"):
            conn.load_extension("definitely_missing_extension")
