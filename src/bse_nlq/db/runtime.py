"""Read-only runtime database factory.

Opens a published filesystem SQLite artifact for application query execution.
This module is not a SQL policy validator, authorizer, progress limiter, or
query service. It returns a narrow ``ReadOnlyDatabase`` wrapper that privately
owns the connection after semantic metadata has been reconciled.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from bse_nlq.db.build import destination_sidecar_paths
from bse_nlq.db.errors import DatabaseRuntimeError
from bse_nlq.metadata import (
    load_semantic_metadata,
    prompt_excluded_columns,
    prompt_visible_columns,
)
from bse_nlq.metadata.errors import MetadataError
from bse_nlq.metadata.models import APPLICATION_TABLES, SemanticMetadata


@dataclass(frozen=True, slots=True)
class _ReadyState:
    """Immutable snapshots captured once the runtime wrapper is ready."""

    database_path: Path
    metadata: SemanticMetadata
    physical_tables: frozenset[str]
    physical_columns: frozenset[tuple[str, str]]
    prompt_visible_columns: frozenset[tuple[str, str]]
    prompt_excluded_columns: frozenset[tuple[str, str]]


class ReadOnlyDatabase:
    """Context-managed owner of one read-only, query-only SQLite connection.

    The private connection is available to peer ``bse_nlq.db`` modules through
    the ``_connection`` property. Callers must not treat that attribute as a
    public API for arbitrary SQL execution.
    """

    __slots__ = ("_state", "_raw_connection", "_closed")

    def __init__(self, state: _ReadyState, connection: sqlite3.Connection) -> None:
        self._state = state
        self._raw_connection = connection
        self._closed = False

    @property
    def database_path(self) -> Path:
        return self._state.database_path

    @property
    def metadata(self) -> SemanticMetadata:
        self._require_open()
        return self._state.metadata

    @property
    def physical_tables(self) -> frozenset[str]:
        self._require_open()
        return self._state.physical_tables

    @property
    def physical_columns(self) -> frozenset[tuple[str, str]]:
        self._require_open()
        return self._state.physical_columns

    @property
    def prompt_visible_columns(self) -> frozenset[tuple[str, str]]:
        self._require_open()
        return self._state.prompt_visible_columns

    @property
    def prompt_excluded_columns(self) -> frozenset[tuple[str, str]]:
        self._require_open()
        return self._state.prompt_excluded_columns

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def _connection(self) -> sqlite3.Connection:
        """Package-private connection accessor; not part of the public surface."""
        self._require_open()
        return self._raw_connection

    def close(self) -> None:
        """Close the owned connection. Idempotent."""
        if self._closed:
            return
        self._closed = True
        try:
            self._raw_connection.close()
        except Exception:
            # Closing is best-effort once ownership has ended.
            pass

    def __enter__(self) -> ReadOnlyDatabase:
        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise DatabaseRuntimeError("ReadOnlyDatabase is closed")


def open_readonly_database(database_path: Path | str) -> ReadOnlyDatabase:
    """Open a published SQLite file as a ready ``ReadOnlyDatabase``.

    The path must name an existing non-symlink regular file. In-memory targets
    and SQLite URI strings (``file:...``) are rejected. Exact sibling SQLite
    sidecars (``{path}-wal`` / ``{path}-shm`` / ``{path}-journal``) cause
    fail-closed rejection without deleting them. Filenames that merely end in
    those suffixes remain valid targets when no such siblings exist.

    The connection is opened with ``mode=ro``, ``PRAGMA foreign_keys=ON``, and
    ``PRAGMA query_only=ON``. Semantic metadata is loaded and reconciled before
    the wrapper is returned. No authorizer or progress handler is installed.
    """
    path = _validate_database_path(database_path)
    uri = _readonly_uri(path)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(uri, uri=True)
        _disable_load_extension(connection)
        _enable_and_verify_pragma(
            connection, "foreign_keys", on_sql="PRAGMA foreign_keys = ON"
        )
        _enable_and_verify_pragma(
            connection, "query_only", on_sql="PRAGMA query_only = ON"
        )
        if connection.in_transaction:
            raise DatabaseRuntimeError(
                "read-only connection must not be in a transaction"
            )

        metadata = load_semantic_metadata(connection)
        visible = prompt_visible_columns(metadata)
        visible_pairs = frozenset(
            (table, column) for table, columns in visible.items() for column in columns
        )
        excluded = prompt_excluded_columns(metadata)
        excluded_pairs = frozenset(
            (table, column) for table, columns in excluded.items() for column in columns
        )
        physical_column_pairs = frozenset(
            (table_name, column_name)
            for table_name, table in metadata.tables.items()
            for column_name in table.columns
        )
        physical = frozenset(APPLICATION_TABLES)
        if set(metadata.tables) != set(physical):
            raise DatabaseRuntimeError(
                "reconciled metadata tables diverge from the application table set"
            )
        if visible_pairs & excluded_pairs:
            raise DatabaseRuntimeError(
                "prompt-visible and prompt-excluded column inventories overlap"
            )
        if physical_column_pairs != visible_pairs | excluded_pairs:
            raise DatabaseRuntimeError(
                "physical column inventory does not equal visible ∪ excluded"
            )
        if connection.in_transaction:
            raise DatabaseRuntimeError(
                "read-only connection must not be in a transaction"
            )

        state = _ReadyState(
            database_path=path,
            metadata=metadata,
            physical_tables=physical,
            physical_columns=physical_column_pairs,
            prompt_visible_columns=visible_pairs,
            prompt_excluded_columns=excluded_pairs,
        )
        ready = ReadOnlyDatabase(state, connection)
        connection = None
        return ready
    except BaseException as error:
        _cleanup_failed_open(connection)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(error, DatabaseRuntimeError):
            raise
        if isinstance(error, MetadataError):
            raise DatabaseRuntimeError(
                "semantic metadata could not be loaded for read-only open"
            ) from error
        raise DatabaseRuntimeError("read-only database open failed") from error


def _validate_database_path(database_path: Path | str) -> Path:
    if not isinstance(database_path, (str, Path)):
        raise DatabaseRuntimeError("database path must be a filesystem path")

    raw = os.fspath(database_path)
    if not raw or not raw.strip():
        raise DatabaseRuntimeError("database path must be a non-empty path")
    if raw.strip() != raw:
        raise DatabaseRuntimeError(
            "database path must not include surrounding whitespace"
        )
    if raw == ":memory:" or raw.startswith("file:"):
        raise DatabaseRuntimeError(
            "database path must be a filesystem path, not a SQLite URI"
        )

    path = Path(raw).expanduser()
    if path.name in {"", ".", ".."} or path.name == ":memory:":
        raise DatabaseRuntimeError(
            "database path must include a valid database filename"
        )

    # Resolve only the parent so a leaf symlink is detected via lstat.
    parent = path.parent
    if not parent.is_absolute():
        parent = (Path.cwd() / parent).resolve(strict=False)
    else:
        parent = parent.resolve(strict=False)

    candidate = parent / path.name
    try:
        mode = candidate.lstat().st_mode
    except FileNotFoundError as error:
        raise DatabaseRuntimeError("database path does not exist") from error
    except OSError as error:
        raise DatabaseRuntimeError("database path is not usable") from error

    if stat.S_ISLNK(mode):
        raise DatabaseRuntimeError("database path must not be a symbolic link")
    if stat.S_ISDIR(mode):
        raise DatabaseRuntimeError(
            "database path must be a regular file, not a directory"
        )
    if not stat.S_ISREG(mode):
        raise DatabaseRuntimeError("database path must be a regular file")

    _reject_exact_sibling_sidecars(candidate)
    return candidate


def _reject_exact_sibling_sidecars(database_path: Path) -> None:
    """Fail closed when exact SQLite sidecars of the main artifact exist.

    Only ``{database_path}-wal``, ``{database_path}-shm``, and
    ``{database_path}-journal`` are inspected. Sidecars are never deleted or
    modified. A main filename that itself ends in those suffixes is allowed
    when none of those exact siblings exist.
    """
    present = [
        sidecar
        for sidecar in destination_sidecar_paths(database_path)
        if _path_exists_without_following(sidecar)
    ]
    if not present:
        return
    names = ", ".join(sidecar.name for sidecar in present)
    raise DatabaseRuntimeError(
        f"database path has unexpected SQLite sidecar(s): {names}"
    )


def _path_exists_without_following(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise DatabaseRuntimeError(
            f"database sidecar path is not usable: {path.name}"
        ) from error
    return True


def _readonly_uri(path: Path) -> str:
    """Build a ``mode=ro`` URI without following a rejected leaf symlink."""
    if not path.is_absolute():
        raise DatabaseRuntimeError("database path must be absolute after validation")
    return f"{path.as_uri()}?mode=ro"


def _disable_load_extension(connection: sqlite3.Connection) -> None:
    if not hasattr(connection, "enable_load_extension"):
        return
    try:
        connection.enable_load_extension(False)
    except sqlite3.Error as error:
        raise DatabaseRuntimeError(
            "failed to disable SQLite extension loading"
        ) from error


def _enable_and_verify_pragma(
    connection: sqlite3.Connection,
    name: str,
    *,
    on_sql: str,
) -> None:
    connection.execute(on_sql)
    row = connection.execute(f"PRAGMA {name}").fetchone()
    if row is None or row[0] != 1:
        raise DatabaseRuntimeError(f"failed to enable PRAGMA {name}")


def _cleanup_failed_open(connection: sqlite3.Connection | None) -> None:
    if connection is None:
        return
    try:
        if connection.in_transaction:
            connection.rollback()
    except Exception:
        pass
    try:
        connection.close()
    except Exception:
        pass
