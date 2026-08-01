"""Immutable ValidatedSql model contract for U2 Slice 1."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from bse_nlq.sql_policy import ValidatedSql


def _sample() -> ValidatedSql:
    return ValidatedSql(
        original_sql="SELECT 1",
        normalized_sql="SELECT 1",
        fingerprint="a" * 64,
        referenced_tables=frozenset(),
        referenced_columns=frozenset(),
        referenced_functions=frozenset(),
    )


def test_validated_sql_is_frozen_and_slotted() -> None:
    model = _sample()
    assert model.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    assert hasattr(ValidatedSql, "__slots__")
    with pytest.raises(FrozenInstanceError):
        model.original_sql = "SELECT 2"  # type: ignore[misc]


def test_validated_sql_field_inventory() -> None:
    names = {f.name for f in fields(ValidatedSql)}
    assert names == {
        "original_sql",
        "normalized_sql",
        "fingerprint",
        "referenced_tables",
        "referenced_columns",
        "referenced_functions",
    }
    assert "sql" not in names
    assert "connection" not in names
    assert "cursor" not in names
    assert "ast" not in names
    assert "expression" not in names
    assert "terminal_state" not in names


def test_referenced_collections_are_frozensets() -> None:
    model = _sample()
    assert isinstance(model.referenced_tables, frozenset)
    assert isinstance(model.referenced_columns, frozenset)
    assert isinstance(model.referenced_functions, frozenset)
    with pytest.raises(AttributeError):
        model.referenced_tables.add("events")  # type: ignore[attr-defined]
