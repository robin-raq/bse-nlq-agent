"""Static SQL parsing, structure policy, and table/column inventory checks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import sqlglot
from sqlglot.errors import ParseError
from sqlglot.expressions import Expr

from bse_nlq.sql_policy.column_inventory import (
    CanonicalColumnInventory,
    canonicalize_column_inventories,
)
from bse_nlq.sql_policy.errors import (
    InvalidSqlError,
    SqlRejectedError,
    SqlRejectionReason,
)
from bse_nlq.sql_policy.models import ValidatedSql
from bse_nlq.sql_policy.output_schemas import validate_internal_output_schemas
from bse_nlq.sql_policy.scope_policy import authorize_physical_tables
from bse_nlq.sql_policy.structure import apply_structure_policy


@dataclass(frozen=True, slots=True)
class _PolicyInventories:
    """Immutable inventory bag for ``validate_sql``.

    ``physical_tables`` authorize physical sources (Slice 3).
    ``column_inventory`` holds canonical physical and prompt-visible column
    inventories (Slice 4A). Column binding and ``referenced_columns`` remain
    deferred.
    """

    physical_tables: frozenset[str]
    column_inventory: CanonicalColumnInventory


def validate_sql(
    sql: str,
    *,
    physical_tables: frozenset[str],
    physical_columns: frozenset[tuple[str, str]],
    prompt_visible_columns: frozenset[tuple[str, str]],
) -> ValidatedSql:
    """Parse, apply structure policy, authorize tables, and check output schemas.

    Accepts immutable inventories. ``physical_tables`` is authoritative for
    Slice 3 physical-source allowlisting. Column inventories are validated and
    canonicalized (Slice 4A). Internal CTE/derived/Union output-name schemas
    are constructed for duplicate and arity checks; column binding and
    ``referenced_columns`` remain deferred. Does not open SQLite or execute SQL.
    """
    if not isinstance(sql, str):
        raise TypeError("sql must be str")
    inventories = _coerce_inventories(
        physical_tables=physical_tables,
        physical_columns=physical_columns,
        prompt_visible_columns=prompt_visible_columns,
    )

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
    referenced_tables = authorize_physical_tables(
        expression, physical_tables=inventories.physical_tables
    )
    validate_internal_output_schemas(expression)
    normalized_sql = _normalize(expression)
    fingerprint = hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest()
    return ValidatedSql(
        original_sql=original_sql,
        normalized_sql=normalized_sql,
        fingerprint=fingerprint,
        referenced_tables=referenced_tables,
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
    tables = _require_str_frozenset("physical_tables", physical_tables)
    column_inventory = canonicalize_column_inventories(
        physical_tables=tables,
        physical_columns=physical_columns,
        prompt_visible_columns=prompt_visible_columns,
    )
    return _PolicyInventories(
        physical_tables=tables,
        column_inventory=column_inventory,
    )


def _require_str_frozenset(name: str, value: object) -> frozenset[str]:
    if not isinstance(value, frozenset):
        raise TypeError(f"{name} must be frozenset[str]")
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{name} must contain only str values")
    return value
