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
            raise RuntimeError("injected query_only failure")
        real_enable(connection, name, on_sql=on_sql)

    monkeypatch.setattr("bse_nlq.db.runtime.sqlite3.connect", connect_and_track)
    monkeypatch.setattr(
        "bse_nlq.db.runtime._enable_and_verify_pragma", enable_and_maybe_fail
    )

    with pytest.raises(DatabaseRuntimeError) as exc_info:
        open_readonly_database(published_db)

    assert isinstance(exc_info.value.__cause__, RuntimeError)
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


def test_load_extension_disabled(published_db: Path) -> None:
    with open_readonly_database(published_db) as db:
        conn = db._connection
        assert hasattr(conn, "enable_load_extension")
        with pytest.raises(sqlite3.OperationalError, match="not authorized"):
            conn.load_extension("definitely_missing_extension")
