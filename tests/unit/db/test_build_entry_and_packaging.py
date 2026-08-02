"""Developer entry point and generated-artifact Git protection."""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

from bse_nlq.db.build import main

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_module_entry_point_success(tmp_path: Path) -> None:
    destination = tmp_path / "cli.db"
    code = main([str(destination)])
    assert code == 0
    assert destination.is_file()


def test_module_entry_point_expected_error_is_concise(tmp_path: Path, capsys) -> None:
    destination = tmp_path / "exists.db"
    destination.write_text("x", encoding="utf-8")
    code = main([str(destination)])
    captured = capsys.readouterr()
    assert code == 1
    assert "already exists" in captured.err
    assert "Traceback" not in captured.err


def test_module_entry_point_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "cli-overwrite.db"
    assert main([str(destination)]) == 0
    assert main([str(destination), "--overwrite"]) == 0


def test_subprocess_module_invocation(tmp_path: Path) -> None:
    destination = tmp_path / "subproc.db"
    completed = subprocess.run(
        [sys.executable, "-m", "bse_nlq.db.build", str(destination)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "built" in completed.stdout
    assert destination.is_file()


def test_documented_db_patterns_are_gitignored() -> None:
    completed = subprocess.run(
        ["git", "check-ignore", "-v", "data/app.db", "local.sqlite", "x.sqlite3"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "*.db" in completed.stdout
    assert "*.sqlite" in completed.stdout
    assert "*.sqlite3" in completed.stdout


def test_build_database_works_from_installed_wheel(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    build = subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--offline",
            "--no-build-isolation",
            "-o",
            str(wheel_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr
    wheels = list(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert "bse_nlq/db/build.py" in names

    venv_dir = tmp_path / "venv"
    create = subprocess.run(
        ["uv", "venv", str(venv_dir)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert create.returncode == 0, create.stderr
    python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    install = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--no-deps",
            "--no-index",
            str(wheel),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert install.returncode == 0, install.stderr

    outside = tmp_path / "outside"
    outside.mkdir()
    db_path = outside / "installed.db"
    probe = subprocess.run(
        [
            str(python),
            "-c",
            (
                "from pathlib import Path;"
                "from bse_nlq.db import build_database;"
                f"result = build_database(Path({str(db_path)!r}));"
                "assert sum(result.row_counts.values()) == 109;"
                "assert len(result.row_counts) == 6;"
                "print('WHEEL_BUILD_OK', result.logical_content_fingerprint)"
            ),
        ],
        cwd=outside,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": ""},
    )
    assert probe.returncode == 0, probe.stderr + probe.stdout
    assert "WHEEL_BUILD_OK" in probe.stdout
    assert db_path.is_file()
    db_path.unlink()
