"""Shared helpers for SQL-policy unit tests."""

from __future__ import annotations

from bse_nlq.sql_policy import ValidatedSql, validate_sql

EMPTY_TABLES: frozenset[str] = frozenset()
EMPTY_COLUMNS: frozenset[tuple[str, str]] = frozenset()
EMPTY_VISIBLE: frozenset[tuple[str, str]] = frozenset()


def validate(sql: object) -> ValidatedSql:
    return validate_sql(
        sql,  # type: ignore[arg-type]
        physical_tables=EMPTY_TABLES,
        physical_columns=EMPTY_COLUMNS,
        prompt_visible_columns=EMPTY_VISIBLE,
    )
