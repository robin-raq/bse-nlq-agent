"""Logical fingerprint reproducibility for persistent builds."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bse_nlq.db.build import build_database
from bse_nlq.db.errors import DatabaseBuildError
from bse_nlq.db.schema import apply_schema


def test_logical_fingerprint_matches_across_destinations(tmp_path: Path) -> None:
    left = build_database(tmp_path / "a.db")
    right = build_database(tmp_path / "b.db")
    assert left.logical_content_fingerprint == right.logical_content_fingerprint
    assert left.logical_content_fingerprint
    assert len(left.logical_content_fingerprint) == 64


def test_logical_fingerprint_stable_across_working_directories(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "one"
    second_dir = tmp_path / "two"
    first_dir.mkdir()
    second_dir.mkdir()
    original = Path.cwd()
    try:
        os.chdir(first_dir)
        first = build_database(Path("first.db"))
        os.chdir(second_dir)
        second = build_database(Path("second.db"))
    finally:
        os.chdir(original)

    assert first.logical_content_fingerprint == second.logical_content_fingerprint


def test_same_environment_file_digest_may_match(tmp_path: Path) -> None:
    """Byte digests can match within one environment; not a portability claim."""
    left = build_database(tmp_path / "left.db")
    right = build_database(tmp_path / "right.db")
    assert left.file_sha256 == right.file_sha256


def test_independent_repeated_builds_do_not_share_state(tmp_path: Path) -> None:
    results = [build_database(tmp_path / f"run-{index}.db") for index in range(3)]
    fingerprints = {result.logical_content_fingerprint for result in results}
    assert len(fingerprints) == 1
    assert len({result.destination for result in results}) == 3


def test_failed_build_does_not_affect_later_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "later.db"

    def boom(_connection: object) -> None:
        raise RuntimeError("first failure")

    monkeypatch.setattr("bse_nlq.db.build.apply_schema", boom)
    with pytest.raises(DatabaseBuildError):
        build_database(destination)

    monkeypatch.setattr("bse_nlq.db.build.apply_schema", apply_schema)
    result = build_database(destination)
    assert sum(result.row_counts.values()) == 109
