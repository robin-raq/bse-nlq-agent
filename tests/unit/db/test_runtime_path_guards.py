"""Path and destination guards for open_readonly_database."""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
from pathlib import Path

import pytest

from bse_nlq.db.build import build_database, destination_sidecar_paths
from bse_nlq.db.errors import DatabaseRuntimeError
from bse_nlq.db.runtime import _readonly_uri, open_readonly_database


@pytest.fixture
def published_db(tmp_path: Path) -> Path:
    destination = tmp_path / "app.db"
    build_database(destination)
    return destination


def _copy_published(published_db: Path, destination: Path) -> Path:
    shutil.copy2(published_db, destination)
    return destination


def test_rejects_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    with pytest.raises(DatabaseRuntimeError, match="exist|not found|usable"):
        open_readonly_database(missing)


@pytest.mark.parametrize(
    "filename",
    (
        "missing?.db",
        "missing#name.db",
        "missing%name.db",
        "missing name.db",
        "missingé.db",
    ),
)
def test_rejects_missing_ordinary_paths_with_special_filename_chars(
    tmp_path: Path, filename: str
) -> None:
    """Missing filesystem paths are missing paths, never URI classification."""
    missing = tmp_path / filename
    assert not missing.exists()
    with pytest.raises(DatabaseRuntimeError, match=r"does not exist") as exc_info:
        open_readonly_database(missing)
    assert "URI" not in str(exc_info.value)


def test_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(DatabaseRuntimeError, match="directory|regular file"):
        open_readonly_database(tmp_path)


def test_rejects_empty_path() -> None:
    with pytest.raises(DatabaseRuntimeError, match="non-empty"):
        open_readonly_database("")


def test_rejects_whitespace_only_path() -> None:
    with pytest.raises(DatabaseRuntimeError, match="non-empty|whitespace"):
        open_readonly_database("   ")


def test_rejects_surrounding_whitespace(published_db: Path) -> None:
    with pytest.raises(DatabaseRuntimeError, match="whitespace"):
        open_readonly_database(f" {published_db} ")


def test_rejects_memory_target() -> None:
    with pytest.raises(DatabaseRuntimeError, match="filesystem|URI"):
        open_readonly_database(":memory:")


def test_rejects_file_uri(published_db: Path) -> None:
    with pytest.raises(DatabaseRuntimeError, match="filesystem|URI"):
        open_readonly_database(f"file:{published_db}")


def test_rejects_uri_query_string_that_is_not_a_real_file(published_db: Path) -> None:
    # Appended query text is still a missing ordinary filesystem path, not file: URI.
    with pytest.raises(DatabaseRuntimeError, match=r"does not exist") as exc_info:
        open_readonly_database(f"{published_db}?mode=ro")
    assert "URI" not in str(exc_info.value)


@pytest.mark.parametrize("suffix", ("-wal", "-shm", "-journal"))
def test_rejects_exact_sibling_sidecars(published_db: Path, suffix: str) -> None:
    sidecar = Path(f"{published_db}{suffix}")
    sidecar.write_bytes(b"stale-sidecar")
    digest_before = hashlib.sha256(published_db.read_bytes()).hexdigest()
    with pytest.raises(DatabaseRuntimeError, match="sidecar|wal|shm|journal"):
        open_readonly_database(published_db)
    assert sidecar.read_bytes() == b"stale-sidecar"
    assert hashlib.sha256(published_db.read_bytes()).hexdigest() == digest_before


def test_rejects_when_all_exact_sibling_sidecars_exist(published_db: Path) -> None:
    for sidecar in destination_sidecar_paths(published_db):
        sidecar.write_bytes(b"stale")
    with pytest.raises(DatabaseRuntimeError, match="sidecar|wal|shm|journal"):
        open_readonly_database(published_db)
    for sidecar in destination_sidecar_paths(published_db):
        assert sidecar.exists()


def test_unrelated_similar_names_do_not_block_open(published_db: Path) -> None:
    (published_db.parent / f"{published_db.name}-wal.bak").write_bytes(b"x")
    (published_db.parent / f"{published_db.name}-wal-extra").write_bytes(b"x")
    (published_db.parent / f"{published_db.stem}-wal").write_bytes(b"x")
    with open_readonly_database(published_db) as db:
        assert not db.closed


@pytest.mark.parametrize("suffix", ("-wal", "-shm", "-journal"))
def test_opens_legitimate_target_whose_name_ends_with_sidecar_suffix(
    published_db: Path, tmp_path: Path, suffix: str
) -> None:
    target = _copy_published(published_db, tmp_path / f"legitimate{suffix}")
    assert not any(p.exists() for p in destination_sidecar_paths(target))
    with open_readonly_database(target) as db:
        assert db.database_path == target.resolve()
        assert db._connection.execute("SELECT COUNT(*) FROM venues").fetchone() == (4,)


def test_opens_existing_literal_question_mark_filename(
    published_db: Path, tmp_path: Path
) -> None:
    target = _copy_published(published_db, tmp_path / "weird?.db")
    assert "?" in target.name
    with open_readonly_database(target) as db:
        assert db.database_path == target.resolve()
        assert db._connection.execute("SELECT COUNT(*) FROM venues").fetchone() == (4,)


@pytest.mark.parametrize(
    ("filename", "encoded_fragment"),
    (
        ("app space.db", "%20"),
        ("café.db", "%C3%A9"),
        ("app#1.db", "%23"),
        ("100%.db", "%25"),
        ("weird?.db", "%3F"),
    ),
)
def test_opens_uri_sensitive_filenames_with_safe_encoding(
    published_db: Path, tmp_path: Path, filename: str, encoded_fragment: str
) -> None:
    target = _copy_published(published_db, tmp_path / filename)
    uri = _readonly_uri(target.resolve())
    assert encoded_fragment in uri
    assert uri.endswith("?mode=ro")
    assert not uri.startswith(f"file:{target.resolve()}?")
    with open_readonly_database(target) as db:
        assert db._connection.execute("SELECT COUNT(*) FROM venues").fetchone() == (4,)


def test_readonly_uri_never_uses_unescaped_path_interpolation(
    published_db: Path, tmp_path: Path
) -> None:
    target = _copy_published(published_db, tmp_path / "app#1.db")
    uri = _readonly_uri(target.resolve())
    unsafe = f"file:{target.resolve()}?mode=ro"
    assert uri != unsafe
    assert "%23" in uri


_UNKNOWN_USER_PATH = "~nosuchuser_zz/app.db"


def _unknown_user_expansion_raises() -> bool:
    """Whether ``~unknownuser`` expansion fails on this interpreter/platform."""
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
def test_unknown_user_expansion_surfaces_runtime_error_type() -> None:
    """Home-directory expansion failure must not escape as bare RuntimeError."""
    with pytest.raises(DatabaseRuntimeError, match="expand") as exc_info:
        open_readonly_database(_UNKNOWN_USER_PATH)
    assert isinstance(exc_info.value.__cause__, RuntimeError)


@pytest.mark.parametrize(
    "raw",
    (
        "/tmp/a\x00b.db",  # NUL in the filename component
        "/tmp/a\x00b/x.db",  # NUL in a parent component
    ),
)
def test_embedded_nul_surfaces_runtime_error_type(raw: str) -> None:
    """Embedded NUL must not escape as bare ValueError."""
    with pytest.raises(DatabaseRuntimeError, match="usable|path") as exc_info:
        open_readonly_database(raw)
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_rejects_symlink(published_db: Path, tmp_path: Path) -> None:
    link = tmp_path / "link.db"
    os.symlink(published_db, link)
    with pytest.raises(DatabaseRuntimeError, match="symbolic link|symlink"):
        open_readonly_database(link)


def test_rejects_broken_symlink(tmp_path: Path) -> None:
    link = tmp_path / "broken.db"
    os.symlink(tmp_path / "missing-target.db", link)
    with pytest.raises(DatabaseRuntimeError, match="symbolic link|symlink"):
        open_readonly_database(link)


def test_rejects_nonregular_fifo(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe.db"
    os.mkfifo(fifo)
    with pytest.raises(DatabaseRuntimeError, match="regular file"):
        open_readonly_database(fifo)


def test_rejects_unix_socket(tmp_path: Path) -> None:
    sock_path = tmp_path / "sock.db"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(sock_path))
        with pytest.raises(DatabaseRuntimeError, match="regular file"):
            open_readonly_database(sock_path)
    finally:
        server.close()
        if sock_path.exists():
            sock_path.unlink()
