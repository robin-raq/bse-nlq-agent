"""Whole-tree SQL function allowlist for U2 Slice 4D.

Default-deny by SQLGlot expression *type*, not by string name: only the
`exp.Func` subclasses in ``_ALLOWED_FUNCTIONS`` are permitted, everything else
(including every machine-clock form) is rejected. This sidesteps the
inconsistent string spelling SQLGlot gives unrecognized/anonymous calls
(``exp.Anonymous.sql_name()`` is always ``"ANONYMOUS"`` regardless of the
underlying SQL name) and keeps the allowlist a single source of truth.

The allowlist is sized to the 14 executable anchors and the PRD's own
correctly-implemented example questions: SUM and COALESCE (anchors), plus
COUNT (the ``COUNT(*)``-only star policy already assumes COUNT is otherwise a
legitimate function). No date/time function is allowlisted, so
``CURRENT_DATE``/``CURRENT_TIME``/``CURRENT_TIMESTAMP`` and every
``date/datetime/julianday/strftime/unixepoch(...)`` form are rejected by the
same default-deny path, not by inspecting their ``'now'``/``'localtime'``/
``'utc'`` arguments.
"""

from __future__ import annotations

from sqlglot import exp
from sqlglot.expressions import Expr

from bse_nlq.sql_policy.errors import SqlRejectedError, SqlRejectionReason

_ALLOWED_FUNCTIONS: dict[type[exp.Func], str] = {
    exp.Sum: "SUM",
    exp.Count: "COUNT",
    exp.Coalesce: "COALESCE",
}

#: Canonical allowed names, reused by the SQLite authorizer (U3) as the same
#: single source of truth rather than a second hand-maintained allowlist.
ALLOWED_FUNCTION_NAMES: frozenset[str] = frozenset(_ALLOWED_FUNCTIONS.values())


def authorize_functions(expression: Expr) -> frozenset[str]:
    """Reject any function call outside the fixed allowlist.

    Returns the canonical names of allowed functions actually present.
    """
    referenced: set[str] = set()
    for node in expression.find_all(exp.Func):
        if _is_non_function_syntax(node):
            continue
        canonical = _ALLOWED_FUNCTIONS.get(type(node))
        if canonical is None:
            raise SqlRejectedError(
                f"Function is not allowed: {node.sql_name()}",
                reason=SqlRejectionReason.FORBIDDEN_FUNCTION,
            )
        referenced.add(canonical)
    return frozenset(referenced)


def _is_non_function_syntax(node: exp.Func) -> bool:
    """True for ``exp.Func`` nodes that are not ``NAME(...)`` call syntax.

    In this SQLGlot version, ``exp.And``/``exp.Or`` multiply-inherit from both
    ``exp.Binary`` and ``exp.Func``, so a plain ``exp.Func`` walk also visits
    every ``AND``/``OR`` in the tree. ``exp.Exists`` is genuine function-call
    syntax but is a structural subquery predicate the already-committed
    Slice 4B qualified-correlation policy depends on, not a value-computing
    call this allowlist is meant to police.
    """
    return isinstance(node, exp.Binary | exp.Exists)
