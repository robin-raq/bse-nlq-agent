"""Public SQL-policy API surface for U2 Slice 1."""

from __future__ import annotations

import importlib
import inspect

import pytest

from bse_nlq.sql_policy import (
    InvalidSqlError,
    SqlPolicyError,
    SqlRejectedError,
    SqlRejectionReason,
    ValidatedSql,
    validate_sql,
)

EXPECTED_PUBLIC_EXPORTS = {
    "InvalidSqlError",
    "SqlPolicyError",
    "SqlRejectedError",
    "SqlRejectionReason",
    "ValidatedSql",
    "validate_sql",
}


def test_public_symbols_are_importable() -> None:
    assert callable(validate_sql)
    assert issubclass(ValidatedSql, object)
    assert issubclass(InvalidSqlError, SqlPolicyError)
    assert issubclass(SqlRejectedError, SqlPolicyError)
    assert issubclass(SqlPolicyError, Exception)
    assert SqlRejectionReason.EMPTY_SQL.value == "empty_sql"


def test_public_all_exports_only_intended_symbols() -> None:
    package = importlib.import_module("bse_nlq.sql_policy")
    assert hasattr(package, "__all__")
    exported = set(package.__all__)
    assert exported == EXPECTED_PUBLIC_EXPORTS
    for name in exported:
        assert not name.startswith("_"), name


def test_import_does_not_parse_or_touch_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sqlglot

    def boom(*_args: object, **_kwargs: object) -> list[object]:
        raise AssertionError("sqlglot.parse must not run at import time")

    monkeypatch.setattr(sqlglot, "parse", boom)
    importlib.reload(importlib.import_module("bse_nlq.sql_policy"))


def test_package_has_no_sqlite_execution_surface() -> None:
    package = importlib.import_module("bse_nlq.sql_policy")
    for name, obj in vars(package).items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(obj):
            assert name == "validate_sql"
            source = inspect.getsource(obj)
            assert "sqlite3" not in source
            assert ".execute(" not in source
            assert "connect(" not in source
