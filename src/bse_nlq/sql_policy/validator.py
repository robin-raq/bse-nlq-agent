"""Static SQL parsing, statement-shape, and Slice 2 structure validation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import sqlglot
from sqlglot.errors import ParseError
from sqlglot.expressions import Expr

from bse_nlq.sql_policy.errors import (
    InvalidSqlError,
    SqlRejectedError,
    SqlRejectionReason,
)
from bse_nlq.sql_policy.models import ValidatedSql
from bse_nlq.sql_policy.structure import apply_structure_policy


@dataclass(frozen=True, slots=True)
class _PolicyInventories:
    """Immutable inventory bag accepted by ``validate_sql`` (Slice 1 unused)."""

    physical_tables: frozenset[str]
    physical_columns: frozenset[tuple[str, str]]
    prompt_visible_columns: frozenset[tuple[str, str]]


def validate_sql(
    sql: str,
    *,
    physical_tables: frozenset[str],
    physical_columns: frozenset[tuple[str, str]],
    prompt_visible_columns: frozenset[tuple[str, str]],
) -> ValidatedSql:
    """Parse and apply Slice 1 shape plus Slice 2 structure policy.

    Accepts immutable physical/visible inventories for later authorization
    slices. Verifies inventory shapes but does not authorize tables or
    columns, open SQLite, or execute SQL.
    """
    if not isinstance(sql, str):
        raise TypeError("sql must be str")
    inventories = _coerce_inventories(
        physical_tables=physical_tables,
        physical_columns=physical_columns,
        prompt_visible_columns=prompt_visible_columns,
    )
    # Slice 1 accepts inventories for the stable public signature only.
    _ = inventories

    original_sql = sql.strip()
    if not original_sql:
        raise SqlRejectedError(
            "SQL is empty after trimming outer whitespace",
            reason=SqlRejectionReason.EMPTY_SQL,
        )

    try:
        expressions = sqlglot.parse(original_sql, read="sqlite")
    except ParseError as error:
        raise InvalidSqlError(
            "SQL could not be parsed",
            reason=SqlRejectionReason.PARSE_ERROR,
        ) from error

    meaningful = [expression for expression in expressions if expression is not None]
    if not meaningful:
        raise SqlRejectedError(
            "SQL contains no meaningful statement",
            reason=SqlRejectionReason.EMPTY_SQL,
        )
    if len(meaningful) > 1:
        raise SqlRejectedError(
            "SQL must contain exactly one statement",
            reason=SqlRejectionReason.MULTIPLE_STATEMENTS,
        )

    expression = meaningful[0]
    apply_structure_policy(expression)
    normalized_sql = _normalize(expression)
    fingerprint = hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest()
    return ValidatedSql(
        original_sql=original_sql,
        normalized_sql=normalized_sql,
        fingerprint=fingerprint,
        referenced_tables=frozenset(),
        referenced_columns=frozenset(),
        referenced_functions=frozenset(),
    )


def _normalize(expression: Expr) -> str:
    return expression.sql(dialect="sqlite", comments=False)


def _coerce_inventories(
    *,
    physical_tables: frozenset[str],
    physical_columns: frozenset[tuple[str, str]],
    prompt_visible_columns: frozenset[tuple[str, str]],
) -> _PolicyInventories:
    return _PolicyInventories(
        physical_tables=_require_str_frozenset("physical_tables", physical_tables),
        physical_columns=_require_column_frozenset(
            "physical_columns", physical_columns
        ),
        prompt_visible_columns=_require_column_frozenset(
            "prompt_visible_columns", prompt_visible_columns
        ),
    )


def _require_str_frozenset(name: str, value: object) -> frozenset[str]:
    if not isinstance(value, frozenset):
        raise TypeError(f"{name} must be frozenset[str]")
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{name} must contain only str values")
    return value


def _require_column_frozenset(name: str, value: object) -> frozenset[tuple[str, str]]:
    if not isinstance(value, frozenset):
        raise TypeError(f"{name} must be frozenset[tuple[str, str]]")
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError(f"{name} must contain (table, column) str pairs")
        table, column = item
        if not isinstance(table, str) or not isinstance(column, str):
            raise TypeError(f"{name} must contain (table, column) str pairs")
    return value
