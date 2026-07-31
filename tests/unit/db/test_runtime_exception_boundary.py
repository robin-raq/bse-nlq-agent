"""Exception-boundary contracts for open_readonly_database.

Expected runtime failures normalize to DatabaseRuntimeError. Programming
defects must propagate as their original types after failed-open cleanup.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from bse_nlq.db import runtime as runtime_module
from bse_nlq.db.build import build_database, destination_sidecar_paths
from bse_nlq.db.errors import DatabaseRuntimeError
from bse_nlq.db.runtime import open_readonly_database
from bse_nlq.metadata.errors import MetadataError, MetadataReconciliationError


@pytest.fixture
def published_db(tmp_path: Path) -> Path:
    destination = tmp_path / "app.db"
    build_database(destination)
    return destination


def _track_connect(monkeypatch: pytest.MonkeyPatch) -> list[sqlite3.Connection]:
    real_connect = sqlite3.connect
    connections: list[sqlite3.Connection] = []

    def connect_and_track(*args: object, **kwargs: object) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr("bse_nlq.db.runtime.sqlite3.connect", connect_and_track)
    return connections


def _assert_connections_closed(connections: list[sqlite3.Connection]) -> None:
    assert connections
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


@pytest.mark.parametrize(
    "defect",
    (
        AttributeError("injected attribute defect"),
        AssertionError("injected assertion defect"),
        KeyError("injected-key"),
        NameError("injected_name"),
        ZeroDivisionError("injected zero division"),
    ),
    ids=(
        "AttributeError",
        "AssertionError",
        "KeyError",
        "NameError",
        "ZeroDivisionError",
    ),
)
def test_programmer_defects_propagate_after_cleanup(
    published_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: BaseException,
) -> None:
    """Internal factory defects must not be normalized as DatabaseRuntimeError."""
    connections = _track_connect(monkeypatch)
    digest_before = hashlib.sha256(published_db.read_bytes()).hexdigest()

    def raise_defect(*_args: object, **_kwargs: object) -> None:
        raise defect

    monkeypatch.setattr("bse_nlq.db.runtime._disable_load_extension", raise_defect)

    with pytest.raises(type(defect)) as exc_info:
        open_readonly_database(published_db)

    assert exc_info.value is defect
    assert not isinstance(exc_info.value, DatabaseRuntimeError)
    _assert_connections_closed(connections)
    assert hashlib.sha256(published_db.read_bytes()).hexdigest() == digest_before
    assert not any(p.exists() for p in destination_sidecar_paths(published_db))

    monkeypatch.undo()
    with open_readonly_database(published_db) as db:
        assert not db.closed
        assert db._connection.execute("SELECT COUNT(*) FROM venues").fetchone() == (4,)


_UNKNOWN_USER_PATH = "~nosuchuser_zz/app.db"


def _unknown_user_expansion_raises() -> bool:
    try:
        Path(_UNKNOWN_USER_PATH).expanduser()
    except RuntimeError:
        return True
    except Exception:  # pragma: no cover - platform-dependent
        return False
    return False  # pragma: no cover - platform-dependent


@pytest.mark.skipif(
    not _unknown_user_expansion_raises(),
    reason="Path.expanduser() does not raise for unknown users on this platform",
)
def test_expected_runtime_error_from_expanduser_normalizes() -> None:
    with pytest.raises(DatabaseRuntimeError, match="expand") as exc_info:
        open_readonly_database(_UNKNOWN_USER_PATH)
    assert isinstance(exc_info.value.__cause__, RuntimeError)


@pytest.mark.parametrize(
    "raw",
    (
        "/tmp/a\x00b.db",
        "/tmp/a\x00b/x.db",
    ),
)
def test_expected_value_error_from_embedded_nul_normalizes(raw: str) -> None:
    with pytest.raises(DatabaseRuntimeError, match="usable|path") as exc_info:
        open_readonly_database(raw)
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_embedded_nul_in_sibling_sidecar_inspection_normalizes(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "bse_nlq.db.runtime.destination_sidecar_paths",
        lambda _path: [Path("/tmp/sidecar\x00name-wal")],
    )
    with pytest.raises(DatabaseRuntimeError, match="sidecar|usable") as exc_info:
        open_readonly_database(published_db)
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_malformed_sqlite_database_error_normalizes(tmp_path: Path) -> None:
    target = tmp_path / "not-sqlite.db"
    payload = b"NOT A SQLITE DATABASE"
    target.write_bytes(payload)
    with pytest.raises(DatabaseRuntimeError, match="open failed") as exc_info:
        open_readonly_database(target)
    assert isinstance(exc_info.value.__cause__, sqlite3.Error)
    assert target.read_bytes() == payload


def test_metadata_error_normalizes_through_dedicated_branch(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connections = _track_connect(monkeypatch)

    def boom(_connection: object) -> object:
        raise MetadataReconciliationError("injected metadata reconciliation failure")

    monkeypatch.setattr("bse_nlq.db.runtime.load_semantic_metadata", boom)

    with pytest.raises(DatabaseRuntimeError, match="metadata") as exc_info:
        open_readonly_database(published_db)

    assert isinstance(exc_info.value.__cause__, MetadataError)
    assert "open failed" not in str(exc_info.value)
    _assert_connections_closed(connections)


def test_filesystem_oserror_normalizes(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_self: Path) -> object:
        raise OSError("injected filesystem failure")

    monkeypatch.setattr(Path, "lstat", boom)

    with pytest.raises(DatabaseRuntimeError, match="usable|exist|open") as exc_info:
        open_readonly_database(published_db)
    assert isinstance(exc_info.value.__cause__, OSError)


@pytest.mark.parametrize(
    "bad_path",
    (None, 123, b"/tmp/app.db", ["app.db"]),
)
def test_unsupported_runtime_path_input_normalizes(bad_path: object) -> None:
    with pytest.raises(DatabaseRuntimeError, match="filesystem path"):
        open_readonly_database(bad_path)  # type: ignore[arg-type]


def test_specific_database_runtime_error_is_not_double_wrapped() -> None:
    with pytest.raises(DatabaseRuntimeError, match="non-empty") as exc_info:
        open_readonly_database("")
    assert "open failed" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_injected_database_runtime_error_identity_preserved(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = DatabaseRuntimeError("database path does not exist")

    def boom(_path: object) -> Path:
        raise sentinel

    monkeypatch.setattr("bse_nlq.db.runtime._validate_database_path", boom)

    with pytest.raises(DatabaseRuntimeError) as exc_info:
        open_readonly_database(published_db)
    assert exc_info.value is sentinel


def test_pragma_setup_sqlite_error_normalizes_with_cause(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuine SQLite failure surfaced through PRAGMA setup normalizes.

    ``_enable_and_verify_pragma`` only ever raises ``sqlite3.Error`` as an
    expected failure mode (or its own explicit ``DatabaseRuntimeError`` on a
    failed verification) -- never a bare ``RuntimeError``. This is the
    legitimate counterpart to
    ``test_pragma_setup_runtime_error_propagates_unchanged`` below.
    """

    def boom(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("injected pragma failure")

    monkeypatch.setattr("bse_nlq.db.runtime._enable_and_verify_pragma", boom)

    with pytest.raises(DatabaseRuntimeError, match="configure") as exc_info:
        open_readonly_database(published_db)
    assert isinstance(exc_info.value.__cause__, sqlite3.Error)
    assert "injected pragma failure" in str(exc_info.value.__cause__)


def test_pragma_setup_runtime_error_propagates_unchanged(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare RuntimeError from the PRAGMA helper is a programming defect.

    Nothing in ``_enable_and_verify_pragma``'s documented contract raises a
    bare ``RuntimeError`` as an expected outcome, so this must not be
    normalized as an ordinary ``DatabaseRuntimeError`` -- doing so would hide
    a real bug in the helper behind a misleading "bad database" diagnosis.
    Replaces the previous ``test_normalized_failures_preserve_cause``, which
    incorrectly treated this exact injection as expected-and-normalized.
    """
    connections = _track_connect(monkeypatch)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected pragma failure")

    monkeypatch.setattr("bse_nlq.db.runtime._enable_and_verify_pragma", boom)

    with pytest.raises(RuntimeError, match="injected pragma failure") as exc_info:
        open_readonly_database(published_db)
    assert not isinstance(exc_info.value, DatabaseRuntimeError)
    _assert_connections_closed(connections)

    monkeypatch.undo()
    with open_readonly_database(published_db) as db:
        assert not db.closed


def test_pragma_setup_type_error_propagates_unchanged(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A TypeError from the PRAGMA setup helper is a programming defect."""
    connections = _track_connect(monkeypatch)
    digest_before = hashlib.sha256(published_db.read_bytes()).hexdigest()

    def boom(*_args: object, **_kwargs: object) -> None:
        raise TypeError("internal setup bug")

    monkeypatch.setattr("bse_nlq.db.runtime._enable_and_verify_pragma", boom)

    with pytest.raises(TypeError, match="internal setup bug") as exc_info:
        open_readonly_database(published_db)
    assert not isinstance(exc_info.value, DatabaseRuntimeError)
    _assert_connections_closed(connections)
    assert hashlib.sha256(published_db.read_bytes()).hexdigest() == digest_before
    assert not any(p.exists() for p in destination_sidecar_paths(published_db))

    monkeypatch.undo()
    with open_readonly_database(published_db) as db:
        assert not db.closed


def test_metadata_inventory_runtime_error_propagates_unchanged(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A RuntimeError from a metadata/inventory helper is a programming
    defect, not a ``MetadataError`` or a SQLite failure, and must not be
    normalized."""
    connections = _track_connect(monkeypatch)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("internal metadata bug")

    monkeypatch.setattr("bse_nlq.db.runtime.prompt_visible_columns", boom)

    with pytest.raises(RuntimeError, match="internal metadata bug") as exc_info:
        open_readonly_database(published_db)
    assert not isinstance(exc_info.value, DatabaseRuntimeError)
    _assert_connections_closed(connections)

    monkeypatch.undo()
    with open_readonly_database(published_db) as db:
        assert not db.closed


def test_metadata_inventory_value_error_propagates_unchanged(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ValueError from a non-path metadata/inventory helper is a
    programming defect and must not be normalized."""
    connections = _track_connect(monkeypatch)
    digest_before = hashlib.sha256(published_db.read_bytes()).hexdigest()

    def boom(*_args: object, **_kwargs: object) -> None:
        raise ValueError("internal inventory bug")

    monkeypatch.setattr("bse_nlq.db.runtime.prompt_excluded_columns", boom)

    with pytest.raises(ValueError, match="internal inventory bug") as exc_info:
        open_readonly_database(published_db)
    assert not isinstance(exc_info.value, DatabaseRuntimeError)
    _assert_connections_closed(connections)
    assert hashlib.sha256(published_db.read_bytes()).hexdigest() == digest_before
    assert not any(p.exists() for p in destination_sidecar_paths(published_db))

    monkeypatch.undo()
    with open_readonly_database(published_db) as db:
        assert not db.closed


class _FailingCloseConnection:
    def __init__(self, error: BaseException) -> None:
        self._error = error
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        raise self._error


def test_context_manager_double_failure_keeps_both_inspectable(
    published_db: Path,
) -> None:
    """Body and close failures both remain available through the exception chain."""
    db = open_readonly_database(published_db)
    real_connection = db._raw_connection
    stub = _FailingCloseConnection(sqlite3.OperationalError("injected close failure"))
    db._raw_connection = stub  # type: ignore[assignment]
    try:
        with pytest.raises(DatabaseRuntimeError, match="close") as exc_info:
            with db:
                raise ValueError("injected body failure")
        assert isinstance(exc_info.value.__cause__, sqlite3.OperationalError)
        # Close uses ``raise from``, so the body failure sits further down the
        # standard ``__context__`` chain rather than as the immediate context.
        chain: list[BaseException] = []
        current: BaseException | None = exc_info.value
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            chain.append(current)
            current = current.__context__
        assert any(isinstance(item, ValueError) for item in chain)
        assert stub.close_calls == 1
        assert db.closed is False
    finally:
        db._raw_connection = real_connection  # type: ignore[assignment]
        db.close()


def test_failed_open_cleanup_preserves_primary_even_if_close_fails(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Emergency cleanup suppresses ordinary close failures; primary stays.

    The primary failure is injected as a genuine ``sqlite3.Error`` (not a
    bare ``RuntimeError``) so this test exercises the localized normalize
    path rather than accidentally re-encoding the F-1 masking bug: a bare
    ``RuntimeError`` from a post-connect setup helper is a programming
    defect and must propagate unwrapped (see
    ``test_pragma_setup_runtime_error_propagates_unchanged``), not stand in
    for "any primary failure."
    """
    connections = _track_connect(monkeypatch)
    real_cleanup = runtime_module._cleanup_failed_open

    def cleanup_with_suppressed_secondary(
        connection: sqlite3.Connection | None,
    ) -> None:
        # Mimic production: attempt close, swallow ordinary failures, never
        # replace the primary open exception that is already propagating.
        try:
            raise RuntimeError("secondary cleanup failure")
        except Exception:
            pass
        real_cleanup(connection)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("primary open failure")

    monkeypatch.setattr(
        "bse_nlq.db.runtime._cleanup_failed_open", cleanup_with_suppressed_secondary
    )
    monkeypatch.setattr("bse_nlq.db.runtime._disable_load_extension", boom)

    with pytest.raises(DatabaseRuntimeError, match="configure") as exc_info:
        open_readonly_database(published_db)
    assert isinstance(exc_info.value.__cause__, sqlite3.Error)
    assert "primary open failure" in str(exc_info.value.__cause__)
    assert "secondary" not in str(exc_info.value)
    _assert_connections_closed(connections)


def test_keyboard_interrupt_remains_unwrapped(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connections = _track_connect(monkeypatch)

    def interrupt(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("bse_nlq.db.runtime._disable_load_extension", interrupt)
    with pytest.raises(KeyboardInterrupt):
        open_readonly_database(published_db)
    _assert_connections_closed(connections)


def test_system_exit_remains_unwrapped(
    published_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connections = _track_connect(monkeypatch)

    def exit_now(*_args: object, **_kwargs: object) -> None:
        raise SystemExit(3)

    monkeypatch.setattr("bse_nlq.db.runtime._disable_load_extension", exit_now)
    with pytest.raises(SystemExit) as exc_info:
        open_readonly_database(published_db)
    assert exc_info.value.code == 3
    _assert_connections_closed(connections)
