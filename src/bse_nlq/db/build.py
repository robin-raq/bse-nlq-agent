"""Deterministic persistent SQLite database builder.

Composes ``apply_schema`` and ``load_seed_data`` into an atomically published
filesystem artifact. Generated databases are local developer artifacts and are
not committed. This module is not a read-only runtime factory, query service,
or product CLI.

Publication contract summary:

- ``overwrite=False`` publishes with atomic no-clobber ``os.link`` (same
  directory / filesystem). Concurrent creation of the destination fails closed
  without clobbering the other actor's bytes.
- ``overwrite=True`` publishes with ``os.replace`` after all validation and
  evidence calculation, then removes exact destination ``-wal`` / ``-shm`` /
  ``-journal`` sidecars before returning success.
- File size, SHA-256, header checks, row counts, and the logical fingerprint
  are computed from the closed temporary artifact **before** publication.
- Existing destinations may be overwritten only when they are non-symlink
  regular files (``lstat``). Concurrent external use or mutation of the
  destination during publication is unsupported.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import stat
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from bse_nlq.db.artifact import (
    compute_logical_content_fingerprint,
    validate_built_database,
)
from bse_nlq.db.errors import DatabaseBuildError
from bse_nlq.db.schema import apply_schema
from bse_nlq.db.seed import load_seed_data

_SQLITE_HEADER = b"SQLite format 3\x00"
_SIDE_SUFFIXES = ("-wal", "-shm", "-journal")

_POST_PUBLICATION_HYGIENE = (
    "publication completed but destination SQLite sidecar cleanup failed"
)


@dataclass(frozen=True, slots=True)
class DatabaseBuildResult:
    """Immutable evidence for one successful persistent database build."""

    destination: Path
    file_size_bytes: int
    file_sha256: str
    logical_content_fingerprint: str
    row_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        """Snapshot row-count evidence so callers cannot mutate the result."""
        object.__setattr__(
            self,
            "row_counts",
            MappingProxyType(dict(self.row_counts)),
        )


@dataclass(frozen=True, slots=True)
class _PrecomputedEvidence:
    """Byte and logical evidence captured before publication."""

    file_size_bytes: int
    file_sha256: str
    logical_content_fingerprint: str
    row_counts: Mapping[str, int]


def destination_sidecar_paths(destination: Path) -> tuple[Path, ...]:
    """Return the exact SQLite sidecar paths for ``destination``."""
    return tuple(Path(f"{destination}{suffix}") for suffix in _SIDE_SUFFIXES)


def build_database(
    destination: Path | str,
    *,
    overwrite: bool = False,
) -> DatabaseBuildResult:
    """Build a validated persistent SQLite database at ``destination``.

    The parent directory of ``destination`` must already exist. An existing
    destination is refused unless ``overwrite=True``, and only a non-symlink
    regular file may be overwritten. When overwriting, the previous main file
    remains byte-for-byte unchanged until the replacement has been fully
    validated and published; destination ``-wal`` / ``-shm`` / ``-journal``
    files are removed only after that successful publication.

    In-memory SQLite targets and SQLite URI destinations are rejected. The
    builder never opens a default repository database and does not consult the
    system clock for content. Concurrent external use or mutation of the
    destination during publication is unsupported.
    """
    dest = _validate_destination(destination, overwrite=overwrite)
    temporary = _temporary_sibling_path(dest)
    connection: sqlite3.Connection | None = None
    published = False
    try:
        connection = sqlite3.connect(temporary)
        connection.execute("PRAGMA foreign_keys = ON")
        fk = connection.execute("PRAGMA foreign_keys").fetchone()
        if fk is None or fk[0] != 1:
            raise DatabaseBuildError("failed to enable PRAGMA foreign_keys")

        apply_schema(connection)
        load_seed_data(connection)
        row_counts = validate_built_database(connection)
        logical_fingerprint = compute_logical_content_fingerprint(connection)

        connection.close()
        connection = None
        _assert_no_sidecars(temporary)

        evidence = _compute_file_evidence(
            temporary,
            row_counts=row_counts,
            logical_content_fingerprint=logical_fingerprint,
        )

        if overwrite:
            _require_existing_regular_file(dest)
            os.replace(temporary, dest)
            published = True
            _remove_destination_sidecars_after_publication(dest)
        else:
            try:
                os.link(temporary, dest)
            except OSError as error:
                raise DatabaseBuildError(
                    "atomic no-clobber publication failed"
                ) from error
            published = True
            _unlink_temporary_after_link(temporary)
            _remove_destination_sidecars_after_publication(dest)

        return DatabaseBuildResult(
            destination=dest,
            file_size_bytes=evidence.file_size_bytes,
            file_sha256=evidence.file_sha256,
            logical_content_fingerprint=evidence.logical_content_fingerprint,
            row_counts=evidence.row_counts,
        )
    except BaseException as error:
        _cleanup_build_resources(connection, temporary, published=published)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(error, DatabaseBuildError):
            raise
        raise DatabaseBuildError("persistent database build failed") from error


def _validate_destination(destination: Path | str, *, overwrite: bool) -> Path:
    if not isinstance(destination, (str, Path)):
        raise DatabaseBuildError("destination must be a filesystem path")

    raw = os.fspath(destination)
    if not raw or not raw.strip():
        raise DatabaseBuildError("destination must be a non-empty path")
    if raw.strip() != raw:
        raise DatabaseBuildError(
            "destination path must not include surrounding whitespace"
        )
    if raw == ":memory:" or raw.startswith("file:"):
        raise DatabaseBuildError(
            "destination must be a filesystem path, not a SQLite URI"
        )
    if "?" in raw:
        raise DatabaseBuildError("destination must not include SQLite URI parameters")

    path = Path(raw).expanduser()
    if path.name in {"", ".", ".."} or path.name == ":memory:":
        raise DatabaseBuildError("destination must include a valid database filename")

    # Resolve only the parent so a destination symlink is not followed.
    parent = path.parent
    if not parent.is_absolute():
        parent = (Path.cwd() / parent).resolve(strict=False)
    else:
        parent = parent.resolve(strict=False)
    if not parent.exists() or not parent.is_dir():
        raise DatabaseBuildError("destination parent directory must exist")

    dest = parent / path.name
    try:
        mode = dest.lstat().st_mode
    except FileNotFoundError:
        return dest
    except OSError as error:
        raise DatabaseBuildError("destination path is not usable") from error

    if stat.S_ISLNK(mode):
        raise DatabaseBuildError("destination must not be a symbolic link")
    if stat.S_ISDIR(mode):
        raise DatabaseBuildError("destination must be a file path, not a directory")
    if not stat.S_ISREG(mode):
        raise DatabaseBuildError("destination must be a regular file")
    if not overwrite:
        raise DatabaseBuildError("destination already exists")
    return dest


def _require_existing_regular_file(destination: Path) -> None:
    """Recheck overwrite targets immediately before publication."""
    try:
        mode = destination.lstat().st_mode
    except FileNotFoundError:
        # Destination disappeared between validation and overwrite publication.
        # os.replace will create the name; treat as allowed for overwrite=True.
        return
    except OSError as error:
        raise DatabaseBuildError("destination path is not usable") from error
    if stat.S_ISLNK(mode):
        raise DatabaseBuildError("destination must not be a symbolic link")
    if not stat.S_ISREG(mode):
        raise DatabaseBuildError("destination must be a regular file")


def _temporary_sibling_path(destination: Path) -> Path:
    token = uuid.uuid4().hex
    return destination.with_name(f".{destination.name}.{token}.building")


def _assert_no_sidecars(path: Path) -> None:
    for sidecar in destination_sidecar_paths(path):
        if sidecar.exists() or sidecar.is_symlink():
            raise DatabaseBuildError(
                f"temporary database left a SQLite sidecar: {sidecar.name}"
            )


def _compute_file_evidence(
    temporary: Path,
    *,
    row_counts: Mapping[str, int],
    logical_content_fingerprint: str,
) -> _PrecomputedEvidence:
    """Read and hash the closed temporary database before publication."""
    data = temporary.read_bytes()
    if not data.startswith(_SQLITE_HEADER):
        raise DatabaseBuildError("built artifact is not a SQLite database file")
    digest = hashlib.sha256(data).hexdigest()
    return _PrecomputedEvidence(
        file_size_bytes=len(data),
        file_sha256=digest,
        logical_content_fingerprint=logical_content_fingerprint,
        row_counts=MappingProxyType(dict(row_counts)),
    )


def _remove_destination_sidecars_after_publication(destination: Path) -> None:
    """Remove exact destination sidecars after the main file is published.

    Failure here means the new database was already published; the previous
    destination was not preserved. Concurrent use of the destination during
    publication remains unsupported.
    """
    first_error: OSError | None = None
    for sidecar in destination_sidecar_paths(destination):
        try:
            if sidecar.exists() or sidecar.is_symlink():
                sidecar.unlink()
        except OSError as error:
            if first_error is None:
                first_error = error

    remaining = [
        sidecar
        for sidecar in destination_sidecar_paths(destination)
        if sidecar.exists() or sidecar.is_symlink()
    ]
    if remaining or first_error is not None:
        raise DatabaseBuildError(_POST_PUBLICATION_HYGIENE) from first_error


def _unlink_temporary_after_link(temporary: Path) -> None:
    try:
        temporary.unlink()
    except OSError as error:
        raise DatabaseBuildError(
            "publication completed but temporary hard-link name could not be removed"
        ) from error


def _cleanup_build_resources(
    connection: sqlite3.Connection | None,
    temporary: Path,
    *,
    published: bool,
) -> None:
    """Best-effort cleanup that never replaces the primary build exception."""
    if connection is not None:
        try:
            if connection.in_transaction:
                connection.rollback()
        except Exception:
            pass
        try:
            connection.close()
        except Exception:
            pass

    if not published:
        _remove_path_and_sidecars(temporary)


def _remove_path_and_sidecars(path: Path) -> None:
    candidates = [path, *destination_sidecar_paths(path)]
    for candidate in candidates:
        try:
            if candidate.exists() or candidate.is_symlink():
                candidate.unlink()
        except OSError:
            # Best-effort cleanup; primary exception remains authoritative.
            continue


def main(argv: list[str] | None = None) -> int:
    """Developer entry point: ``python -m bse_nlq.db.build PATH``."""
    parser = argparse.ArgumentParser(
        prog="python -m bse_nlq.db.build",
        description=(
            "Build the deterministic synthetic SQLite database artifact. "
            "This is a developer utility, not the product NLQ CLI."
        ),
    )
    parser.add_argument(
        "destination",
        type=Path,
        help="Filesystem path for the generated database file",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing destination after the replacement validates",
    )
    args = parser.parse_args(argv)
    try:
        result = build_database(args.destination, overwrite=args.overwrite)
    except DatabaseBuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        "built "
        f"{result.destination} "
        f"rows={sum(result.row_counts.values())} "
        f"logical_sha256={result.logical_content_fingerprint} "
        f"file_sha256={result.file_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
