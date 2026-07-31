"""Metadata readiness and immutability for ReadOnlyDatabase."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import MappingProxyType

import pytest

from bse_nlq.db.build import build_database
from bse_nlq.db.errors import DatabaseRuntimeError
from bse_nlq.db.runtime import open_readonly_database
from bse_nlq.metadata.models import APPLICATION_TABLES


@pytest.fixture
def published_db(tmp_path: Path) -> Path:
    destination = tmp_path / "app.db"
    build_database(destination)
    return destination


def test_prompt_visible_columns_are_frozen_pairs(published_db: Path) -> None:
    with open_readonly_database(published_db) as db:
        assert isinstance(db.prompt_visible_columns, frozenset)
        assert all(
            isinstance(pair, tuple) and len(pair) == 2
            for pair in db.prompt_visible_columns
        )
        for table in APPLICATION_TABLES:
            assert any(t == table for t, _ in db.prompt_visible_columns)
        with pytest.raises(AttributeError):
            db.prompt_visible_columns = frozenset()  # type: ignore[misc]


def test_physical_tables_are_frozen(published_db: Path) -> None:
    with open_readonly_database(published_db) as db:
        assert isinstance(db.physical_tables, frozenset)
        assert db.physical_tables == frozenset(APPLICATION_TABLES)
        with pytest.raises((TypeError, AttributeError)):
            db.physical_tables.add("extra")  # type: ignore[attr-defined]


def test_physical_and_excluded_column_inventories(published_db: Path) -> None:
    with open_readonly_database(published_db) as db:
        assert isinstance(db.physical_columns, frozenset)
        assert isinstance(db.prompt_excluded_columns, frozenset)
        assert ("orders", "order_ref") in db.physical_columns
        assert ("orders", "order_ref") in db.prompt_excluded_columns
        assert ("orders", "order_ref") not in db.prompt_visible_columns
        assert db.physical_columns == (
            db.prompt_visible_columns | db.prompt_excluded_columns
        )
        assert not (db.prompt_visible_columns & db.prompt_excluded_columns)
        with pytest.raises((TypeError, AttributeError)):
            db.physical_columns.add(("venues", "extra"))  # type: ignore[attr-defined]
        with pytest.raises((TypeError, AttributeError)):
            db.prompt_excluded_columns.add(("venues", "extra"))  # type: ignore[attr-defined]


def test_metadata_nested_maps_reject_mutation(published_db: Path) -> None:
    with open_readonly_database(published_db) as db:
        assert isinstance(db.metadata.tables, MappingProxyType)
        with pytest.raises(TypeError):
            db.metadata.tables["orders"] = db.metadata.tables["orders"]  # type: ignore[index]


def test_metadata_failure_closes_connection(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuine SQLite failure surfaced while loading metadata normalizes.

    Uses ``sqlite3.OperationalError`` rather than a bare ``RuntimeError``:
    the latter would be a programming defect in ``load_semantic_metadata``
    and must propagate unwrapped instead (see
    ``tests/unit/db/test_runtime_exception_boundary.py::
    test_metadata_inventory_runtime_error_propagates_unchanged``).
    """

    def boom(_connection: object) -> object:
        raise sqlite3.OperationalError("injected metadata failure")

    monkeypatch.setattr("bse_nlq.db.runtime.load_semantic_metadata", boom)

    with pytest.raises(DatabaseRuntimeError) as exc_info:
        open_readonly_database(published_db)

    assert isinstance(exc_info.value.__cause__, sqlite3.Error)
    # No leaked ready wrapper; a second open of the same path still works once
    # the monkeypatch is undone below.
    monkeypatch.undo()
    with open_readonly_database(published_db) as db:
        assert not db.closed


def test_rejects_malformed_sqlite_without_modifying_file(tmp_path: Path) -> None:
    target = tmp_path / "not-sqlite.db"
    payload = b"NOT A SQLITE DATABASE"
    target.write_bytes(payload)
    with pytest.raises(DatabaseRuntimeError):
        open_readonly_database(target)
    assert target.read_bytes() == payload


def test_rejects_incompatible_schema_without_modifying_file(tmp_path: Path) -> None:
    import sqlite3

    target = tmp_path / "wrong-schema.db"
    connection = sqlite3.connect(target)
    try:
        connection.execute("CREATE TABLE only_one (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    digest_before = target.read_bytes()
    with pytest.raises(DatabaseRuntimeError, match="metadata|reconcil|schema|open"):
        open_readonly_database(target)
    assert target.read_bytes() == digest_before
