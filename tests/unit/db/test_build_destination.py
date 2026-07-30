"""Destination validation and overwrite contracts for build_database."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from bse_nlq.db.build import build_database
from bse_nlq.db.errors import DatabaseBuildError


def test_rejects_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(DatabaseBuildError, match="directory"):
        build_database(tmp_path)


def test_rejects_empty_destination(tmp_path: Path) -> None:
    with pytest.raises(DatabaseBuildError, match="non-empty"):
        build_database("")


def test_rejects_missing_parent(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "app.db"
    with pytest.raises(DatabaseBuildError, match="parent directory"):
        build_database(missing)


def test_rejects_memory_target(tmp_path: Path) -> None:
    with pytest.raises(DatabaseBuildError, match="filesystem"):
        build_database(":memory:")


def test_rejects_sqlite_uri_parameters(tmp_path: Path) -> None:
    with pytest.raises(DatabaseBuildError, match="URI"):
        build_database(f"{tmp_path / 'app.db'}?mode=rwc")


def test_rejects_file_uri(tmp_path: Path) -> None:
    with pytest.raises(DatabaseBuildError, match="filesystem"):
        build_database(f"file:{tmp_path / 'app.db'}")


def test_default_refusal_leaves_existing_bytes(tmp_path: Path) -> None:
    destination = tmp_path / "existing.db"
    destination.write_bytes(b"not-a-database-yet")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    before = list(tmp_path.iterdir())

    with pytest.raises(DatabaseBuildError, match="already exists"):
        build_database(destination)

    assert hashlib.sha256(destination.read_bytes()).hexdigest() == digest
    assert destination.read_bytes() == b"not-a-database-yet"
    assert list(tmp_path.iterdir()) == before


def test_successful_atomic_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "replace.db"
    first = build_database(destination)
    second = build_database(destination, overwrite=True)

    assert second.logical_content_fingerprint == first.logical_content_fingerprint
    assert destination.is_file()
    for suffix in ("-wal", "-shm", "-journal"):
        assert not Path(f"{destination}{suffix}").exists()
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_failed_overwrite_preserves_destination(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "keep.db"
    original = build_database(destination)
    original_bytes = destination.read_bytes()
    original_digest = original.file_sha256

    def boom(_connection: object) -> object:
        raise RuntimeError("injected validation failure")

    monkeypatch.setattr("bse_nlq.db.build.validate_built_database", boom)

    with pytest.raises(DatabaseBuildError) as exc_info:
        build_database(destination, overwrite=True)

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert destination.read_bytes() == original_bytes
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == original_digest
    leftovers = [path for path in tmp_path.iterdir() if path != destination]
    assert leftovers == []
    for suffix in ("-wal", "-shm", "-journal"):
        assert not Path(f"{destination}{suffix}").exists()
