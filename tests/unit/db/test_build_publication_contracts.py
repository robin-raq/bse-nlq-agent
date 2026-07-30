"""Pre-publication evidence and no-clobber / special-file contracts (F2–F4)."""

from __future__ import annotations

import hashlib
import os
import socket
import stat
from pathlib import Path

import pytest

from bse_nlq.db.build import build_database
from bse_nlq.db.errors import DatabaseBuildError


def test_evidence_failure_before_publication_preserves_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "keep.db"
    # Use non-seed prior bytes so a post-publish evidence failure cannot hide
    # behind an identical rebuilt seed digest.
    original_bytes = b"PREVIOUS_DESTINATION_BYTES_NOT_SQLITE"
    destination.write_bytes(original_bytes)

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("evidence boom")

    monkeypatch.setattr("bse_nlq.db.build._compute_file_evidence", boom)

    with pytest.raises(DatabaseBuildError) as exc_info:
        build_database(destination, overwrite=True)

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert destination.read_bytes() == original_bytes
    leftovers = [path for path in tmp_path.iterdir() if path != destination]
    assert leftovers == []


def test_evidence_failure_without_destination_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "fresh.db"

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("evidence boom")

    monkeypatch.setattr("bse_nlq.db.build._compute_file_evidence", boom)

    with pytest.raises(DatabaseBuildError) as exc_info:
        build_database(destination)

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_success_computes_evidence_once_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import bse_nlq.db.build as build_mod

    calls: list[Path] = []
    real = build_mod._compute_file_evidence

    def spy(temporary: Path, **kwargs: object) -> object:
        calls.append(temporary)
        return real(temporary, **kwargs)

    monkeypatch.setattr(build_mod, "_compute_file_evidence", spy)
    destination = tmp_path / "once.db"
    result = build_database(destination)

    assert len(calls) == 1
    assert calls[0] != destination
    assert result.file_sha256 == hashlib.sha256(destination.read_bytes()).hexdigest()
    assert result.file_size_bytes == destination.stat().st_size


def test_overwrite_false_uses_link_not_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import bse_nlq.db.build as build_mod

    replace_calls: list[tuple[object, object]] = []
    link_calls: list[tuple[object, object]] = []
    real_link = os.link
    real_replace = os.replace

    def tracking_link(src: object, dst: object) -> None:
        link_calls.append((src, dst))
        return real_link(src, dst)

    def tracking_replace(src: object, dst: object) -> None:
        replace_calls.append((src, dst))
        return real_replace(src, dst)

    monkeypatch.setattr(build_mod.os, "link", tracking_link)
    monkeypatch.setattr(build_mod.os, "replace", tracking_replace)

    destination = tmp_path / "linked.db"
    result = build_database(destination)
    assert len(link_calls) == 1
    assert replace_calls == []
    assert result.file_sha256 == hashlib.sha256(destination.read_bytes()).hexdigest()
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_overwrite_false_race_preserves_other_actor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import bse_nlq.db.build as build_mod

    destination = tmp_path / "race.db"
    real_link = os.link

    def raced_link(src: object, dst: object) -> None:
        Path(dst).write_bytes(b"OTHER_ACTOR_BYTES")
        return real_link(src, dst)

    monkeypatch.setattr(build_mod.os, "link", raced_link)

    with pytest.raises(DatabaseBuildError, match="no-clobber") as exc_info:
        build_database(destination)

    assert isinstance(exc_info.value.__cause__, OSError)
    assert destination.read_bytes() == b"OTHER_ACTOR_BYTES"
    leftovers = [p for p in tmp_path.iterdir() if p != destination]
    assert leftovers == []
    for suffix in ("-wal", "-shm", "-journal"):
        assert not Path(f"{destination}{suffix}").exists()


def test_overwrite_true_still_uses_replace(tmp_path: Path) -> None:
    destination = tmp_path / "replace.db"
    first = build_database(destination)
    second = build_database(destination, overwrite=True)
    assert second.logical_content_fingerprint == first.logical_content_fingerprint


def test_rejects_symlink_to_regular_file(tmp_path: Path) -> None:
    target = tmp_path / "real.db"
    target.write_bytes(b"REAL")
    link = tmp_path / "link.db"
    link.symlink_to(target)
    before = list(tmp_path.iterdir())

    with pytest.raises(DatabaseBuildError, match="symbolic link"):
        build_database(link)
    with pytest.raises(DatabaseBuildError, match="symbolic link"):
        build_database(link, overwrite=True)

    assert link.is_symlink()
    assert target.read_bytes() == b"REAL"
    assert list(tmp_path.iterdir()) == before


def test_rejects_broken_symlink(tmp_path: Path) -> None:
    link = tmp_path / "broken.db"
    link.symlink_to(tmp_path / "missing-target.db")
    before = list(tmp_path.iterdir())

    with pytest.raises(DatabaseBuildError, match="symbolic link"):
        build_database(link, overwrite=True)

    assert link.is_symlink()
    assert list(tmp_path.iterdir()) == before


def test_rejects_fifo_when_available(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("mkfifo unavailable")
    fifo = tmp_path / "fifo.db"
    os.mkfifo(fifo)
    assert stat.S_ISFIFO(fifo.lstat().st_mode)
    before = list(tmp_path.iterdir())

    with pytest.raises(DatabaseBuildError, match="regular file"):
        build_database(fifo)
    with pytest.raises(DatabaseBuildError, match="regular file"):
        build_database(fifo, overwrite=True)

    assert stat.S_ISFIFO(fifo.lstat().st_mode)
    assert list(tmp_path.iterdir()) == before


def test_rejects_unix_socket_when_practical(tmp_path: Path) -> None:
    sock_path = tmp_path / "sock.db"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        try:
            server.bind(str(sock_path))
        except OSError:
            pytest.skip("AF_UNIX bind unavailable")
        assert sock_path.exists()
        before = list(tmp_path.iterdir())
        with pytest.raises(DatabaseBuildError, match="regular file"):
            build_database(sock_path, overwrite=True)
        assert sock_path.exists()
        assert list(tmp_path.iterdir()) == before
    finally:
        server.close()
        if sock_path.exists():
            sock_path.unlink()


def test_regular_file_refused_without_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "regular.db"
    destination.write_bytes(b"REGULAR")
    with pytest.raises(DatabaseBuildError, match="already exists"):
        build_database(destination)
    assert destination.read_bytes() == b"REGULAR"


def test_regular_file_accepted_with_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "regular.db"
    destination.write_bytes(b"REGULAR")
    result = build_database(destination, overwrite=True)
    assert destination.read_bytes().startswith(b"SQLite format 3\x00")
    assert result.file_size_bytes == destination.stat().st_size
