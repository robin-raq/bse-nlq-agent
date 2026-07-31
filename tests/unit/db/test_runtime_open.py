"""Happy-path open and connection invariants for ReadOnlyDatabase."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from bse_nlq.db.build import build_database, destination_sidecar_paths
from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database
from bse_nlq.metadata.models import APPLICATION_TABLES


@pytest.fixture
def published_db(tmp_path: Path) -> Path:
    destination = tmp_path / "app.db"
    build_database(destination)
    return destination


def test_open_returns_ready_readonly_database(published_db: Path) -> None:
    db = open_readonly_database(published_db)
    try:
        assert isinstance(db, ReadOnlyDatabase)
        assert db.database_path == published_db.resolve()
        assert not db.closed
        assert set(db.physical_tables) == set(APPLICATION_TABLES)
        assert ("orders", "order_ref") not in db.prompt_visible_columns
        assert ("orders", "status") in db.prompt_visible_columns
        assert ("orders", "order_ref") in db.physical_columns
        assert ("orders", "order_ref") in db.prompt_excluded_columns
        assert db.metadata.tables["orders"].columns["order_ref"].in_prompt is False
    finally:
        db.close()


def test_open_accepts_str_path(published_db: Path) -> None:
    db = open_readonly_database(str(published_db))
    try:
        assert not db.closed
        assert db._connection.execute("SELECT COUNT(*) FROM venues").fetchone() == (4,)
    finally:
        db.close()


def test_foreign_keys_and_query_only_are_on(published_db: Path) -> None:
    with open_readonly_database(published_db) as db:
        conn = db._connection
        assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert conn.execute("PRAGMA query_only").fetchone() == (1,)
        assert conn.in_transaction is False


def test_mode_ro_rejects_writes(published_db: Path) -> None:
    with open_readonly_database(published_db) as db:
        with pytest.raises(
            sqlite3.OperationalError, match="readonly|read-only|query_only"
        ):
            db._connection.execute(
                "INSERT INTO venues (venue_id, name, district, capacity) "
                "VALUES (99, 'Nope', 'Nowhere', 1)"
            )


def test_mode_ro_enforced_independently_of_query_only(published_db: Path) -> None:
    digest_before = hashlib.sha256(published_db.read_bytes()).hexdigest()
    size_before = published_db.stat().st_size
    with open_readonly_database(published_db) as db:
        conn = db._connection
        conn.execute("PRAGMA query_only = OFF")
        assert conn.execute("PRAGMA query_only").fetchone() == (0,)
        with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
            conn.execute(
                "INSERT INTO venues (venue_id, name, district, capacity) "
                "VALUES (99, 'Nope', 'Nowhere', 1)"
            )
        assert conn.execute("SELECT COUNT(*) FROM venues").fetchone() == (4,)
    assert published_db.stat().st_size == size_before
    assert hashlib.sha256(published_db.read_bytes()).hexdigest() == digest_before
    assert not any(p.exists() for p in destination_sidecar_paths(published_db))


def test_successful_open_close_preserves_artifact(published_db: Path) -> None:
    digest_before = hashlib.sha256(published_db.read_bytes()).hexdigest()
    size_before = published_db.stat().st_size
    with open_readonly_database(published_db) as db:
        assert db._connection.in_transaction is False
        assert db._connection.execute("SELECT COUNT(*) FROM venues").fetchone() == (4,)
    assert published_db.stat().st_size == size_before
    assert hashlib.sha256(published_db.read_bytes()).hexdigest() == digest_before
    assert not any(p.exists() for p in destination_sidecar_paths(published_db))


def test_context_manager_closes_idempotently(published_db: Path) -> None:
    db = open_readonly_database(published_db)
    with db as entered:
        assert entered is db
        assert not db.closed
    assert db.closed
    db.close()
    db.close()
    assert db.closed


def test_no_public_arbitrary_sql_execute(published_db: Path) -> None:
    with open_readonly_database(published_db) as db:
        assert not hasattr(db, "execute")
        public = {name for name in dir(db) if not name.startswith("_")}
        assert "execute" not in public
        assert "_connection" not in public
        assert "connection" not in public
