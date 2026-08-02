"""Qualified column binding and projection-star policy for U2 Slice 4B."""

from __future__ import annotations

from sqlglot import exp
from sqlglot.expressions import Expr
from sqlglot.optimizer.scope import Scope, traverse_scope

from bse_nlq.sql_policy.column_inventory import CanonicalColumnInventory
from bse_nlq.sql_policy.errors import SqlRejectedError, SqlRejectionReason
from bse_nlq.sql_policy.output_schemas import output_schema_for_scope
from bse_nlq.sql_policy.scope_policy import fold_sqlite_identifier


def enforce_star_policy(expression: Expr) -> None:
    """Reject every authored star except the argument in ``COUNT(*)``."""
    for star in expression.find_all(exp.Star):
        if _is_sqlglot_values_rewrite_star(star):
            continue
        if isinstance(star.parent, exp.Count) and star.parent.this is star:
            continue
        raise SqlRejectedError(
            "Projection stars are not allowed; name each projected column",
            reason=SqlRejectionReason.PROJECTION_STAR,
        )


def authorize_qualified_columns(
    expression: Expr,
    *,
    inventory: CanonicalColumnInventory,
) -> frozenset[tuple[str, str]]:
    """Bind qualified columns and return canonical physical identities.

    Unqualified references remain deferred to Slice 4C. Qualified references
    may climb through correlated subquery parents, but never through a CTE or
    derived-table boundary. The nearest scope containing a qualifier shadows
    every outer scope even when its requested column is absent or excluded.
    """
    referenced: set[tuple[str, str]] = set()
    seen_columns: set[int] = set()
    for scope in traverse_scope(expression):
        for column in scope.columns:
            identity = id(column)
            if identity in seen_columns:
                continue
            seen_columns.add(identity)
            if isinstance(column.this, exp.Star):
                continue
            _authorize_column(
                column,
                scope=scope,
                inventory=inventory,
                referenced=referenced,
            )
    return frozenset(referenced)


def _authorize_column(
    column: exp.Column,
    *,
    scope: Scope,
    inventory: CanonicalColumnInventory,
    referenced: set[tuple[str, str]],
) -> None:
    if column.args.get("db") is not None or column.args.get("catalog") is not None:
        raise SqlRejectedError(
            "Multipart column references are not supported",
            reason=SqlRejectionReason.UNSUPPORTED_COLUMN_REFERENCE,
        )

    qualifier_node = column.args.get("table")
    if qualifier_node is None:
        return
    if not isinstance(qualifier_node, exp.Identifier):
        raise SqlRejectedError(
            "Column qualifier must be an identifier",
            reason=SqlRejectionReason.UNSUPPORTED_COLUMN_REFERENCE,
        )
    column_node = column.this
    if not isinstance(column_node, exp.Identifier):
        raise SqlRejectedError(
            "Qualified column name must be an identifier",
            reason=SqlRejectionReason.UNSUPPORTED_COLUMN_REFERENCE,
        )

    qualifier = qualifier_node.name
    column_name = column_node.name
    if not qualifier or not column_name:
        raise SqlRejectedError(
            "Qualified column reference contains an empty identifier",
            reason=SqlRejectionReason.UNSUPPORTED_COLUMN_REFERENCE,
        )

    source = _resolve_qualified_source(scope, qualifier=qualifier)
    if isinstance(source, exp.Table):
        _authorize_physical_column(
            source,
            column_name=column_name,
            inventory=inventory,
            referenced=referenced,
        )
        return
    if isinstance(source, Scope):
        _authorize_internal_column(source, column_name=column_name)
        return
    raise SqlRejectedError(
        f"Unsupported qualified column source: {type(source).__name__}",
        reason=SqlRejectionReason.UNSUPPORTED_COLUMN_REFERENCE,
    )


def _resolve_qualified_source(scope: Scope, *, qualifier: str) -> Scope | Expr:
    folded_qualifier = fold_sqlite_identifier(qualifier)
    current: Scope | None = scope
    while current is not None:
        lookup = _source_lookup(current)
        source = lookup.get(folded_qualifier)
        if source is not None:
            return source
        if current.is_cte or current.is_derived_table:
            break
        current = current.parent
    raise SqlRejectedError(
        f"Unknown column qualifier: {qualifier}",
        reason=SqlRejectionReason.UNKNOWN_COLUMN_QUALIFIER,
    )


def _source_lookup(scope: Scope) -> dict[str, Scope | Expr]:
    lookup: dict[str, Scope | Expr] = {}
    for name, source in scope.sources.items():
        folded = fold_sqlite_identifier(name)
        if folded in lookup:
            raise SqlRejectedError(
                f"Ambiguous source qualifier under ASCII folding: {name}",
                reason=SqlRejectionReason.AMBIGUOUS_COLUMN,
            )
        lookup[folded] = source
    return lookup


def _authorize_physical_column(
    table: exp.Table,
    *,
    column_name: str,
    inventory: CanonicalColumnInventory,
    referenced: set[tuple[str, str]],
) -> None:
    identity = (
        fold_sqlite_identifier(table.name),
        fold_sqlite_identifier(column_name),
    )
    canonical = inventory.physical_by_identity.get(identity)
    if canonical is None:
        raise SqlRejectedError(
            f"Unknown column on qualified physical source: {column_name}",
            reason=SqlRejectionReason.UNKNOWN_COLUMN,
        )
    if identity not in inventory.visible_identities:
        raise SqlRejectedError(
            f"Qualified physical column is excluded: {column_name}",
            reason=SqlRejectionReason.EXCLUDED_COLUMN,
        )
    referenced.add(canonical)


def _authorize_internal_column(source: Scope, *, column_name: str) -> None:
    if not (
        source.is_cte
        or source.is_derived_table
        or isinstance(source.expression, (exp.Select, exp.Union))
    ):
        raise SqlRejectedError(
            "Qualified internal source has no supported output schema",
            reason=SqlRejectionReason.UNSUPPORTED_COLUMN_REFERENCE,
        )
    schema = output_schema_for_scope(source)
    if fold_sqlite_identifier(column_name) not in schema.folded_to_canonical:
        raise SqlRejectedError(
            f"Unknown column on qualified internal source: {column_name}",
            reason=SqlRejectionReason.UNKNOWN_COLUMN,
        )


def _is_sqlglot_values_rewrite_star(star: exp.Star) -> bool:
    """Identify SQLGlot's synthetic ``SELECT *`` wrapper for a VALUES branch."""
    parent = star.parent
    if not isinstance(parent, exp.Select) or star not in parent.expressions:
        return False
    from_clause = parent.args.get("from_")
    return (
        isinstance(from_clause, exp.From)
        and isinstance(from_clause.this, exp.Values)
        and star.meta.get("start") == 0
        and star.meta.get("end") == 0
    )
