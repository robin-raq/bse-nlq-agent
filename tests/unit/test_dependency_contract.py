"""Reviewed parser and build-backend constraints."""

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _pyproject() -> dict[str, object]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_sqlglot_is_pinned_to_reviewed_ast_version() -> None:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    dependencies = project["dependencies"]
    assert isinstance(dependencies, list)
    assert "sqlglot==30.14.0" in dependencies
    assert not any(dependency == "sqlglot" for dependency in dependencies)


def test_hatchling_is_pinned_and_available_in_locked_dev_environment() -> None:
    pyproject = _pyproject()
    build_system = pyproject["build-system"]
    dependency_groups = pyproject["dependency-groups"]
    assert isinstance(build_system, dict)
    assert isinstance(dependency_groups, dict)
    assert build_system["requires"] == ["hatchling==1.31.0"]
    dev = dependency_groups["dev"]
    assert isinstance(dev, list)
    assert "hatchling==1.31.0" in dev
