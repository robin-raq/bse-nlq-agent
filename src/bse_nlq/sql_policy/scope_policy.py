"""U2 Slice 3 physical-table authorization from SQLGlot ``scope.sources``.

Precedence within this module (after Slice 1–2 structure checks):

1. unsupported table-source kind
2. qualified physical table
3. unknown physical table

Authority is only ``scope.sources``: ``exp.Table`` is a physical candidate;
nested ``Scope`` is an internal CTE/derived source. Nested scopes are visited
via ``traverse_scope`` rather than by treating Scope values as tables.
"""

from __future__ import annotations

from sqlglot import exp
from sqlglot.expressions import Expr
from sqlglot.optimizer.scope import Scope, traverse_scope

from bse_nlq.sql_policy.errors import SqlRejectedError, SqlRejectionReason

_ASCII_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ASCII_LOWER = "abcdefghijklmnopqrstuvwxyz"
_ASCII_IDENTIFIER_TRANSLATION = str.maketrans(_ASCII_UPPER, _ASCII_LOWER)


def fold_sqlite_identifier(identifier: str) -> str:
    """Fold a SQL identifier the way this project matches SQLite names.

    Comparison is ASCII case-insensitive: only ``A``–``Z`` map to ``a``–``z``.
    Non-ASCII code points are preserved unchanged. No Unicode normalization or
    Unicode casefolding is applied. This matches the supported SQLite
    identifier behavior used by the project; it does not claim general Unicode
    case-insensitive equivalence.
    """
    return identifier.translate(_ASCII_IDENTIFIER_TRANSLATION)


def build_physical_table_lookup(physical_tables: frozenset[str]) -> dict[str, str]:
    """Map folded inventory names to canonical inventory spellings."""
    lookup: dict[str, str] = {}
    for name in physical_tables:
        if not isinstance(name, str):
            raise TypeError("physical_tables must contain only str values")
        if name == "" or name.strip() != name:
            raise TypeError(
                "physical_tables entries must be nonempty and free of "
                "leading/trailing whitespace"
            )
        key = fold_sqlite_identifier(name)
        if key in lookup:
            raise TypeError(
                "physical_tables contains case-fold collisions under "
                "SQLite-compatible identifier matching"
            )
        lookup[key] = name
    return lookup


def authorize_physical_tables(
    expression: Expr, *, physical_tables: frozenset[str]
) -> frozenset[str]:
    """Authorize physical ``exp.Table`` sources and return canonical names.

    Reads SQLGlot nodes and builds independent Python collections. Does not
    mutate the parsed expression, rewrite identifiers in place, or alter
    aliases.
    """
    lookup = build_physical_table_lookup(physical_tables)
    referenced: set[str] = set()
    for scope in traverse_scope(expression):
        for source in scope.sources.values():
            if isinstance(source, Scope):
                continue
            if not isinstance(source, exp.Table):
                raise SqlRejectedError(
                    f"Unsupported table source type: {type(source).__name__}",
                    reason=SqlRejectionReason.UNSUPPORTED_TABLE_SOURCE,
                )
            _authorize_table_node(source, lookup=lookup, referenced=referenced)
    return frozenset(referenced)


def _authorize_table_node(
    table: exp.Table,
    *,
    lookup: dict[str, str],
    referenced: set[str],
) -> None:
    if not isinstance(table.this, exp.Identifier):
        raise SqlRejectedError(
            f"Unsupported table source kind: {type(table.this).__name__}",
            reason=SqlRejectionReason.UNSUPPORTED_TABLE_SOURCE,
        )
    if table.args.get("db") is not None or table.args.get("catalog") is not None:
        raise SqlRejectedError(
            "Database-qualified table references are not allowed",
            reason=SqlRejectionReason.QUALIFIED_TABLE,
        )
    raw_name = table.name
    if not isinstance(raw_name, str) or raw_name == "":
        raise SqlRejectedError(
            "Unsupported table source with empty name",
            reason=SqlRejectionReason.UNSUPPORTED_TABLE_SOURCE,
        )
    canonical = lookup.get(fold_sqlite_identifier(raw_name))
    if canonical is None:
        raise SqlRejectedError(
            f"Unknown physical table: {raw_name}",
            reason=SqlRejectionReason.UNKNOWN_TABLE,
        )
    referenced.add(canonical)
