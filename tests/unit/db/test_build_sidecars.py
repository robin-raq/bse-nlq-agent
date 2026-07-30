"""Stale destination sidecar cleanup after overwrite (F1)."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from bse_nlq.db.artifact import APPLICATION_TABLES
from bse_nlq.db.build import build_database, destination_sidecar_paths
from bse_nlq.db.errors import DatabaseBuildError
from bse_nlq.db.seed_data import EXPECTED_ROW_COUNTS, TOTAL_SEED_ROWS

EXPECTED_LOGICAL = "428dae0b3d8d9b473a99be9606d9cd10e875ddcefc6e0a0f26d254778addf4d2"
STALE_SENTINEL = "STALE_WAL_NAME"


def _plant_stale_wal_destination(destination: Path) -> None:
    """Create a destination with valid WAL/SHM carrying a distinctive mutation.

    Leaves no live connection open. Does not open ``destination`` after planting
    so SQLite cannot checkpoint the planted sidecars away before overwrite.
    """
    scratch = destination.with_name(f".{destination.name}.wal-scratch")
    build_database(scratch)
    conn = sqlite3.connect(scratch)
    try:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        conn.execute(
            "UPDATE venues SET name = ? WHERE venue_id = 1",
            (STALE_SENTINEL,),
        )
        conn.commit()
        main_bytes = scratch.read_bytes()
        wal_bytes = Path(f"{scratch}-wal").read_bytes()
        shm_bytes = Path(f"{scratch}-shm").read_bytes()
    finally:
        conn.close()

    destination.write_bytes(main_bytes)
    Path(f"{destination}-wal").write_bytes(wal_bytes)
    Path(f"{destination}-shm").write_bytes(shm_bytes)
    for path in (scratch, Path(f"{scratch}-wal"), Path(f"{scratch}-shm")):
        if path.exists():
            path.unlink()


def test_destination_sidecar_paths_are_exact(tmp_path: Path) -> None:
    destination = tmp_path / "app.db"
    paths = destination_sidecar_paths(destination)
    assert paths == (
        Path(f"{destination}-wal"),
        Path(f"{destination}-shm"),
        Path(f"{destination}-journal"),
    )


def test_overwrite_clears_stale_wal_and_returns_seed_content(tmp_path: Path) -> None:
    destination = tmp_path / "stale.db"
    _plant_stale_wal_destination(destination)
    assert Path(f"{destination}-wal").exists()
    assert Path(f"{destination}-shm").exists()

    result = build_database(destination, overwrite=True)

    for sidecar in destination_sidecar_paths(destination):
        assert not sidecar.exists()
    assert result.logical_content_fingerprint == EXPECTED_LOGICAL
    assert result.file_sha256 == hashlib.sha256(destination.read_bytes()).hexdigest()

    conn = sqlite3.connect(destination)
    try:
        name = conn.execute("SELECT name FROM venues WHERE venue_id = 1").fetchone()[0]
        assert name == "Kings Harbor Arena"
        assert STALE_SENTINEL not in name
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in APPLICATION_TABLES
        }
        assert counts == EXPECTED_ROW_COUNTS
        assert sum(counts.values()) == TOTAL_SEED_ROWS
    finally:
        conn.close()


def test_overwrite_clears_independently_planted_wal(tmp_path: Path) -> None:
    destination = tmp_path / "wal-only.db"
    build_database(destination)
    Path(f"{destination}-wal").write_bytes(b"not-a-real-wal-but-present")
    build_database(destination, overwrite=True)
    assert not Path(f"{destination}-wal").exists()


def test_overwrite_clears_independently_planted_shm(tmp_path: Path) -> None:
    destination = tmp_path / "shm-only.db"
    build_database(destination)
    Path(f"{destination}-shm").write_bytes(b"stale-shm")
    build_database(destination, overwrite=True)
    assert not Path(f"{destination}-shm").exists()


def test_overwrite_clears_independently_planted_journal(tmp_path: Path) -> None:
    destination = tmp_path / "journal-only.db"
    build_database(destination)
    Path(f"{destination}-journal").write_bytes(b"stale-journal")
    build_database(destination, overwrite=True)
    assert not Path(f"{destination}-journal").exists()


def test_post_publication_sidecar_cleanup_failure_is_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "hygiene.db"
    build_database(destination)

    def boom(_destination: Path) -> None:
        raise DatabaseBuildError(
            "publication completed but destination SQLite sidecar cleanup failed"
        ) from OSError("refuse unlink")

    monkeypatch.setattr(
        "bse_nlq.db.build._remove_destination_sidecars_after_publication",
        boom,
    )

    with pytest.raises(DatabaseBuildError, match="publication completed") as exc_info:
        build_database(destination, overwrite=True)

    assert isinstance(exc_info.value.__cause__, OSError)
    assert destination.exists()
    assert destination.read_bytes().startswith(b"SQLite format 3\x00")
