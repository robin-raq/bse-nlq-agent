"""Persistent database builder: success path and public evidence."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

import pytest

from bse_nlq.db.artifact import APPLICATION_TABLES, compute_logical_content_fingerprint
from bse_nlq.db.build import DatabaseBuildResult, build_database
from bse_nlq.db.seed_data import EXPECTED_ROW_COUNTS, TOTAL_SEED_ROWS


def test_build_database_is_importable() -> None:
    from bse_nlq.db.build import DatabaseBuildResult as Result
    from bse_nlq.db.build import build_database as api

    assert callable(api)
    assert Result is DatabaseBuildResult


def test_successful_persistent_build(tmp_path: Path) -> None:
    destination = tmp_path / "app.sqlite3"
    result = build_database(destination)

    assert isinstance(result, DatabaseBuildResult)
    assert result.destination == destination.resolve()
    assert destination.is_file()
    assert result.file_size_bytes == destination.stat().st_size
    assert result.file_sha256 == hashlib.sha256(destination.read_bytes()).hexdigest()
    assert destination.read_bytes().startswith(b"SQLite format 3\x00")
    assert dict(result.row_counts) == EXPECTED_ROW_COUNTS
    assert sum(result.row_counts.values()) == TOTAL_SEED_ROWS
    assert isinstance(result.row_counts, MappingProxyType)

    with pytest.raises(TypeError):
        result.row_counts["venues"] = 0  # type: ignore[index]


def test_built_database_has_six_tables_and_109_rows(tmp_path: Path) -> None:
    destination = tmp_path / "seeded.db"
    build_database(destination)
    conn = sqlite3.connect(destination)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert tables == set(APPLICATION_TABLES)
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in APPLICATION_TABLES
        }
        assert counts == EXPECTED_ROW_COUNTS
        assert sum(counts.values()) == 109
    finally:
        conn.close()


def test_generated_columns_present_in_artifact(tmp_path: Path) -> None:
    destination = tmp_path / "generated.db"
    build_database(destination)
    conn = sqlite3.connect(destination)
    try:
        events = {row[1]: row[6] for row in conn.execute("PRAGMA table_xinfo(events)")}
        items = {
            row[1]: row[6] for row in conn.execute("PRAGMA table_xinfo(order_items)")
        }
        assert events["event_date"] == 3
        assert items["line_gross_cents"] == 3
        date_row = conn.execute(
            "SELECT event_date FROM events WHERE event_id = 1"
        ).fetchone()
        assert date_row is not None
        assert date_row[0] is not None
    finally:
        conn.close()


def test_fk_and_integrity_checks_pass(tmp_path: Path) -> None:
    destination = tmp_path / "integrity.db"
    build_database(destination)
    conn = sqlite3.connect(destination)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        conn.close()


def test_apply_schema_and_seed_called_once(tmp_path: Path) -> None:
    destination = tmp_path / "once.db"
    with (
        patch(
            "bse_nlq.db.build.apply_schema",
            wraps=__import__(
                "bse_nlq.db.schema", fromlist=["apply_schema"]
            ).apply_schema,
        ) as schema_mock,
        patch(
            "bse_nlq.db.build.load_seed_data",
            wraps=__import__(
                "bse_nlq.db.seed", fromlist=["load_seed_data"]
            ).load_seed_data,
        ) as seed_mock,
    ):
        build_database(destination)
    assert schema_mock.call_count == 1
    assert seed_mock.call_count == 1


def test_no_temporary_residue_after_success(tmp_path: Path) -> None:
    destination = tmp_path / "clean.db"
    build_database(destination)
    leftovers = [
        path
        for path in tmp_path.iterdir()
        if path != destination and path.name.startswith(".")
    ]
    assert leftovers == []
    for suffix in ("-wal", "-shm", "-journal"):
        assert not Path(f"{destination}{suffix}").exists()


def test_artifact_unchanged_after_readonly_verification(tmp_path: Path) -> None:
    destination = tmp_path / "stable.db"
    result = build_database(destination)
    before = destination.read_bytes()
    conn = sqlite3.connect(f"file:{destination}?mode=ro", uri=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM venues").fetchone() == (4,)
        fingerprint = compute_logical_content_fingerprint(conn)
    finally:
        conn.close()
    assert destination.read_bytes() == before
    assert fingerprint == result.logical_content_fingerprint
