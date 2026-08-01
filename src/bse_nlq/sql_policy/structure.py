"""U2 Slice 2 structural SQL policy over a parsed SQLGlot expression.

Precedence (first match wins):

1. unsupported root query family
2. whole-tree forbidden construct
3. recursive CTE
4. parameterized SQL

Does not authorize tables/columns, open SQLite, or mutate the AST.
"""

from __future__ import annotations

from sqlglot import exp
from sqlglot.expressions import Expr

from bse_nlq.sql_policy.errors import SqlRejectedError, SqlRejectionReason

# DML/DDL/admin nodes rejected anywhere in the tree (SQLGlot 30.14.0 classes).
# ``exp.Replace`` is the string function, not DML; SQLite REPLACE INTO falls
# back to ``exp.Command`` and is covered that way.
_FORBIDDEN_NODE_TYPES: tuple[type[Expr], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Pragma,
    exp.Attach,
    exp.Detach,
    exp.Command,
    exp.Analyze,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Grant,
    exp.Revoke,
)


def apply_structure_policy(expression: Expr) -> None:
    """Apply Slice 2 root / forbidden / recursive / parameter checks."""
    _reject_unsupported_root(expression)
    _reject_forbidden_constructs(expression)
    _reject_recursive_ctes(expression)
    _reject_parameters(expression)


def _unwrap_subquery_root(expression: Expr) -> Expr:
    current = expression
    while isinstance(current, exp.Subquery) and current.this is not None:
        current = current.this
    return current


def _reject_unsupported_root(expression: Expr) -> None:
    root = _unwrap_subquery_root(expression)
    if isinstance(root, (exp.Select, exp.Union)):
        return
    raise SqlRejectedError(
        f"Unsupported SQL statement root: {type(root).__name__}",
        reason=SqlRejectionReason.UNSUPPORTED_STATEMENT,
    )


def _reject_forbidden_constructs(expression: Expr) -> None:
    for node in expression.walk():
        if isinstance(node, _FORBIDDEN_NODE_TYPES):
            raise SqlRejectedError(
                f"Forbidden SQL construct: {type(node).__name__}",
                reason=SqlRejectionReason.FORBIDDEN_CONSTRUCT,
            )


def _reject_recursive_ctes(expression: Expr) -> None:
    for node in expression.walk():
        if isinstance(node, exp.With) and node.args.get("recursive"):
            raise SqlRejectedError(
                "Recursive CTEs are not allowed",
                reason=SqlRejectionReason.RECURSIVE_CTE,
            )


def _reject_parameters(expression: Expr) -> None:
    for node in expression.walk():
        if isinstance(node, (exp.Placeholder, exp.Parameter)):
            raise SqlRejectedError(
                "Parameterized SQL is not allowed",
                reason=SqlRejectionReason.PARAMETERIZED_SQL,
            )
        if _is_dollar_parameter_column(node):
            raise SqlRejectedError(
                "Parameterized SQL is not allowed",
                reason=SqlRejectionReason.PARAMETERIZED_SQL,
            )


def _is_dollar_parameter_column(node: Expr) -> bool:
    """Detect SQLite ``$1`` / ``$name`` forms that SQLGlot parses as columns.

    Quoted identifiers such as ``"$1"`` are not treated as parameters.
    """
    if not isinstance(node, exp.Column):
        return False
    identifier = node.args.get("this")
    if not isinstance(identifier, exp.Identifier):
        return False
    if identifier.args.get("quoted"):
        return False
    name = identifier.args.get("this")
    return isinstance(name, str) and name.startswith("$")
