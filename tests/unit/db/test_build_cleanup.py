"""Failure cleanup and interrupt handling for the persistent builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from bse_nlq.db.build import build_database
from bse_nlq.db.errors import DatabaseBuildError


def test_schema_failure_cleans_temporary(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "schema-fail.db"

    def boom(_connection: object) -> None:
        raise RuntimeError("schema boom")

    monkeypatch.setattr("bse_nlq.db.build.apply_schema", boom)

    with pytest.raises(DatabaseBuildError) as exc_info:
        build_database(destination)

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_seed_failure_cleans_temporary(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "seed-fail.db"

    def boom(_connection: object) -> None:
        raise ValueError("seed boom")

    monkeypatch.setattr("bse_nlq.db.build.load_seed_data", boom)

    with pytest.raises(DatabaseBuildError) as exc_info:
        build_database(destination)

    assert isinstance(exc_info.value.__cause__, ValueError)
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_keyboard_interrupt_during_seed_cleans_and_reraises(
    tmp_path: Path, monkeypatch
) -> None:
    destination = tmp_path / "interrupt.db"

    def boom(_connection: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("bse_nlq.db.build.load_seed_data", boom)

    with pytest.raises(KeyboardInterrupt):
        build_database(destination)

    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_system_exit_during_validation_cleans_and_reraises(
    tmp_path: Path, monkeypatch
) -> None:
    destination = tmp_path / "sysexit.db"

    def boom(_connection: object) -> object:
        raise SystemExit(7)

    monkeypatch.setattr("bse_nlq.db.build.validate_built_database", boom)

    with pytest.raises(SystemExit) as exc_info:
        build_database(destination)

    assert exc_info.value.code == 7
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_database_build_error_from_validation_is_not_rewrapped(
    tmp_path: Path, monkeypatch
) -> None:
    destination = tmp_path / "direct.db"

    def boom(_connection: object) -> object:
        raise DatabaseBuildError("artifact invalid")

    monkeypatch.setattr("bse_nlq.db.build.validate_built_database", boom)

    with pytest.raises(DatabaseBuildError, match="artifact invalid") as exc_info:
        build_database(destination)

    assert exc_info.value.__cause__ is None
    assert not destination.exists()
