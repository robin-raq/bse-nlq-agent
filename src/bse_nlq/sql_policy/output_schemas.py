"""Internal CTE / derived / Union output-name schemas for Slice 4A.

Builds bindable output-name schemas from SQLGlot scopes without mutating the
AST, binding physical columns, expanding stars, or querying SQLite.

Star-containing internal projections are Strategy A: ``is_complete=False`` with
no invented expansion (full star policy remains Slice 4B).

Unnamed expressions (empty bindable name) are omitted from the bindable lookup
and mark the schema incomplete; expression text is never invented as a name.

Explicit CTE column lists come from ``scope.outer_columns`` and override
projection names when present; arity mismatches fail closed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sqlglot import exp
from sqlglot.expressions import Expr
from sqlglot.optimizer.scope import Scope, traverse_scope

from bse_nlq.sql_policy.errors import SqlRejectedError, SqlRejectionReason
from bse_nlq.sql_policy.scope_policy import fold_sqlite_identifier


@dataclass(frozen=True, slots=True)
class InternalOutputSchema:
    """Immutable output-name schema for one internal query scope.

    ``canonical_names`` is positional (``None`` = unnamed / non-bindable slot).
    ``folded_to_canonical`` maps ASCII-folded bindable names to canonical
    spelling. ``is_complete`` is False when stars or unnamed slots prevent a
    full bindable schema.
    """

    canonical_names: tuple[str | None, ...]
    folded_to_canonical: Mapping[str, str]
    is_complete: bool


def validate_internal_output_schemas(expression: Expr) -> None:
    """Construct internal output schemas and reject duplicate / arity failures.

    Does not mutate ``expression``. Does not return schemas publicly.
    """
    for scope in traverse_scope(expression):
        if isinstance(scope.expression, exp.Union):
            _schema_for_union_scope(scope)
        elif scope.is_cte or scope.is_derived_table:
            _schema_for_select_scope(scope)


def output_schema_for_scope(scope: Scope) -> InternalOutputSchema:
    """Build an output schema for a CTE, derived, or Union scope (testing helper)."""
    if isinstance(scope.expression, exp.Union):
        return _schema_for_union_scope(scope)
    if (
        scope.is_cte
        or scope.is_derived_table
        or isinstance(scope.expression, exp.Select)
    ):
        return _schema_for_select_scope(scope)
    raise TypeError(f"unsupported scope expression: {type(scope.expression).__name__}")


def _schema_for_select_scope(scope: Scope) -> InternalOutputSchema:
    expression = scope.expression
    if not isinstance(expression, exp.Select):
        raise SqlRejectedError(
            f"Unsupported internal select expression: {type(expression).__name__}",
            reason=SqlRejectionReason.UNSUPPORTED_STATEMENT,
        )

    selects = list(expression.selects)
    has_star = any(_is_projection_star(select) for select in selects)

    explicit = list(scope.outer_columns) if scope.is_cte else []
    if explicit:
        if len(explicit) != len(selects):
            raise SqlRejectedError(
                "CTE column list arity does not match projection arity",
                reason=SqlRejectionReason.INVALID_CTE_COLUMN_LIST,
            )
        raw_names: list[str | None] = list(explicit)
    else:
        raw_names = [_bindable_output_name(select) for select in selects]

    return _finalize_schema(raw_names, has_star=has_star)


def _schema_for_union_scope(scope: Scope) -> InternalOutputSchema:
    expression = scope.expression
    if not isinstance(expression, exp.Union):
        raise TypeError("expected Union expression")

    branches = _union_select_branches(expression)
    if not branches:
        raise SqlRejectedError(
            "Union has no selectable branches",
            reason=SqlRejectionReason.UNSUPPORTED_STATEMENT,
        )

    # Stars (and SQLGlot's VALUES→SELECT * rewrite) make expression-count
    # arity unreliable: a star is one select node but expands to N columns.
    # Strategy A: treat any-branch star/Values as incomplete and skip the
    # false-positive INVALID_UNION_ARITY check when expansion is unknown.
    has_star = any(_branch_has_incomplete_projection(branch) for branch in branches)
    if not has_star:
        arities = [len(branch.selects) for branch in branches]
        if any(arity != arities[0] for arity in arities):
            raise SqlRejectedError(
                "Union branches do not have the same number of result columns",
                reason=SqlRejectionReason.INVALID_UNION_ARITY,
            )

    first = branches[0]
    explicit = list(scope.outer_columns) if scope.is_cte else []
    if explicit:
        if has_star:
            # Explicit names over star/Values bodies remain incomplete (Strategy A).
            return _finalize_schema(list(explicit), has_star=True)
        if len(explicit) != len(first.selects):
            raise SqlRejectedError(
                "CTE column list arity does not match projection arity",
                reason=SqlRejectionReason.INVALID_CTE_COLUMN_LIST,
            )
        raw_names: list[str | None] = list(explicit)
    else:
        raw_names = [_bindable_output_name(select) for select in first.selects]
    return _finalize_schema(raw_names, has_star=has_star)


def _union_select_branches(expression: exp.Union) -> list[exp.Select]:
    """Return left-to-right Select branches under a Union tree."""
    branches: list[exp.Select] = []

    def walk(node: Expr) -> None:
        if isinstance(node, exp.Union):
            walk(node.this)
            walk(node.expression)
            return
        unwrapped = node
        while isinstance(unwrapped, exp.Subquery):
            unwrapped = unwrapped.this
        if isinstance(unwrapped, exp.Select):
            branches.append(unwrapped)
            return
        if isinstance(unwrapped, exp.Union):
            walk(unwrapped)
            return
        raise SqlRejectedError(
            f"Unsupported Union branch expression: {type(node).__name__}",
            reason=SqlRejectionReason.UNSUPPORTED_STATEMENT,
        )

    walk(expression)
    return branches


def _finalize_schema(
    raw_names: list[str | None], *, has_star: bool
) -> InternalOutputSchema:
    folded_to_canonical: dict[str, str] = {}
    has_unnamed = False
    for name in raw_names:
        if name is None or name == "":
            has_unnamed = True
            continue
        if name == "*":
            # Star placeholder from named_selects — treat as incomplete, not bindable.
            has_star = True
            continue
        key = fold_sqlite_identifier(name)
        if key in folded_to_canonical:
            raise SqlRejectedError(
                f"Duplicate internal output name under ASCII folding: {name}",
                reason=SqlRejectionReason.AMBIGUOUS_COLUMN,
            )
        folded_to_canonical[key] = name

    canonical_names = tuple(
        None if (name is None or name == "" or name == "*") else name
        for name in raw_names
    )
    is_complete = (
        (not has_star)
        and (not has_unnamed)
        and all(name is not None for name in canonical_names)
    )
    return InternalOutputSchema(
        canonical_names=canonical_names,
        folded_to_canonical=MappingProxyType(dict(folded_to_canonical)),
        is_complete=is_complete,
    )


def _bindable_output_name(select: Expr) -> str | None:
    """Return a bindable output name, or None when unnamed.

    Uses alias when present; otherwise column name for bare columns; otherwise
    nonempty ``alias_or_name`` only when it is not invented expression SQL for
    compound expressions (Add/etc. report empty alias_or_name in SQLGlot 30.14).
    Does not call ``qualify()`` or execute SQLite.
    """
    if _is_projection_star(select):
        return "*"
    if isinstance(select, exp.Alias):
        alias = select.alias
        return alias if isinstance(alias, str) and alias != "" else None
    if isinstance(select, exp.Column):
        name = select.name
        return name if isinstance(name, str) and name != "" else None
    # Literals and other simple nodes may expose alias_or_name (e.g. SELECT 1 → "1").
    # Compound expressions without AS yield empty alias_or_name in SQLGlot 30.14.0.
    name = select.alias_or_name
    if isinstance(name, str) and name != "":
        return name
    return None


def _is_projection_star(select: Expr) -> bool:
    if isinstance(select, exp.Star):
        return True
    if isinstance(select, exp.Column) and isinstance(select.this, exp.Star):
        return True
    return False


def _branch_has_incomplete_projection(branch: exp.Select) -> bool:
    """True when a Union branch cannot yield a complete bindable schema.

    Covers bare/qualified projection stars and SQLGlot's SQLite rewrite of
    ``VALUES (...)`` into ``SELECT * FROM (VALUES (...)) AS _values``.
    """
    if any(_is_projection_star(select) for select in branch.selects):
        return True
    return any(isinstance(node, exp.Values) for node in branch.walk())
