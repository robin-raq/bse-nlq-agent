"""U2 Slice 4A: internal CTE / derived / Union output-name schemas."""

from __future__ import annotations

import hashlib

import pytest
import sqlglot
from policy_test_helpers import EMPTY_COLUMNS, EMPTY_VISIBLE
from sqlglot.optimizer.scope import traverse_scope

from bse_nlq.sql_policy import (
    SqlRejectedError,
    SqlRejectionReason,
    ValidatedSql,
    validate_sql,
)
from bse_nlq.sql_policy.output_schemas import (
    output_schema_for_scope,
    validate_internal_output_schemas,
)

INVENTORY: frozenset[str] = frozenset(
    {"venues", "events", "ticket_tiers", "orders", "order_items", "refunds"}
)


def _validate(sql: str) -> ValidatedSql:
    return validate_sql(
        sql,
        physical_tables=INVENTORY,
        physical_columns=EMPTY_COLUMNS,
        prompt_visible_columns=EMPTY_VISIBLE,
    )


def _cte_scope(sql: str):
    expression = sqlglot.parse_one(sql, read="sqlite")
    for scope in traverse_scope(expression):
        if scope.is_cte:
            return scope, expression
    raise AssertionError("no CTE scope found")


def _derived_scope(sql: str):
    expression = sqlglot.parse_one(sql, read="sqlite")
    for scope in traverse_scope(expression):
        if scope.is_derived_table:
            return scope, expression
    raise AssertionError("no derived scope found")


def _union_scope(sql: str):
    expression = sqlglot.parse_one(sql, read="sqlite")
    for scope in traverse_scope(expression):
        from sqlglot import exp

        if isinstance(scope.expression, exp.Union):
            return scope, expression
    raise AssertionError("no Union scope found")


# --- Red 5: direct output schemas ---


def test_cte_direct_column_names() -> None:
    scope, _ = _cte_scope(
        "WITH x AS (SELECT event_id, name FROM events) SELECT 1 FROM x"
    )
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("event_id", "name")
    assert schema.is_complete is True
    assert dict(schema.folded_to_canonical) == {
        "event_id": "event_id",
        "name": "name",
    }


def test_cte_column_aliases_preserve_spelling() -> None:
    scope, _ = _cte_scope(
        'WITH x AS (SELECT event_id AS "Event_ID" FROM events) SELECT 1 FROM x'
    )
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("Event_ID",)
    assert schema.folded_to_canonical["event_id"] == "Event_ID"
    assert schema.is_complete is True


def test_expression_and_aggregate_aliases() -> None:
    scope, _ = _cte_scope(
        "WITH x AS ("
        "SELECT event_id + 1 AS next_id, COUNT(*) AS total FROM events"
        ") SELECT 1 FROM x"
    )
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("next_id", "total")
    assert schema.is_complete is True


def test_literal_alias_and_select_without_from() -> None:
    scope, _ = _cte_scope("WITH x AS (SELECT 1 AS value) SELECT 1 FROM x")
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("value",)
    assert schema.is_complete is True


def test_unnamed_expression_omitted_and_incomplete() -> None:
    scope, _ = _cte_scope("WITH x AS (SELECT event_id + 1 FROM events) SELECT 1 FROM x")
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == (None,)
    assert dict(schema.folded_to_canonical) == {}
    assert schema.is_complete is False


def test_unnamed_expression_does_not_invent_sql_text_name() -> None:
    scope, _ = _cte_scope("WITH x AS (SELECT event_id + 1 FROM events) SELECT 1 FROM x")
    schema = output_schema_for_scope(scope)
    assert "event_id + 1" not in schema.folded_to_canonical
    assert "event_id+1" not in schema.folded_to_canonical


def test_derived_table_output_schema() -> None:
    scope, _ = _derived_scope("SELECT 1 FROM (SELECT event_id AS eid FROM events) AS x")
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("eid",)
    assert schema.is_complete is True


# --- Red 6: explicit CTE output lists ---


def test_explicit_cte_names_override_projections() -> None:
    scope, _ = _cte_scope(
        "WITH x(a, b) AS (SELECT event_id, name FROM events) SELECT 1 FROM x"
    )
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("a", "b")
    assert schema.is_complete is True
    assert "event_id" not in schema.folded_to_canonical
    assert schema.folded_to_canonical["a"] == "a"
    assert schema.folded_to_canonical["b"] == "b"


def test_explicit_cte_quoted_names() -> None:
    scope, _ = _cte_scope(
        'WITH x("Event_ID") AS (SELECT event_id FROM events) SELECT 1 FROM x'
    )
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("Event_ID",)
    assert schema.folded_to_canonical["event_id"] == "Event_ID"


def test_explicit_cte_arity_too_short_rejected() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("WITH x(a) AS (SELECT event_id, name FROM events) SELECT 1 FROM x")
    assert exc_info.value.reason is SqlRejectionReason.INVALID_CTE_COLUMN_LIST


def test_explicit_cte_arity_too_long_rejected() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("WITH x(a, b) AS (SELECT event_id FROM events) SELECT 1 FROM x")
    assert exc_info.value.reason is SqlRejectionReason.INVALID_CTE_COLUMN_LIST


def test_explicit_cte_duplicate_names_ambiguous() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("WITH x(a, a) AS (SELECT event_id, name FROM events) SELECT 1 FROM x")
    assert exc_info.value.reason is SqlRejectionReason.AMBIGUOUS_COLUMN


def test_explicit_cte_ascii_fold_collision_ambiguous() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(
            "WITH x(event_id, EVENT_ID) AS "
            "(SELECT event_id, name FROM events) SELECT 1 FROM x"
        )
    assert exc_info.value.reason is SqlRejectionReason.AMBIGUOUS_COLUMN


# --- Red 7: duplicate internal outputs ---


def test_cte_duplicate_bare_names_ambiguous() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(
            """
            WITH x AS (
                SELECT events.event_id, orders.order_id AS event_id
                FROM events
                JOIN orders ON 1 = 1
            )
            SELECT 1 FROM x
            """
        )
    assert exc_info.value.reason is SqlRejectionReason.AMBIGUOUS_COLUMN


def test_cte_duplicate_join_column_names_ambiguous() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(
            """
            WITH x AS (
                SELECT events.event_id, ticket_tiers.event_id
                FROM events
                JOIN ticket_tiers ON 1 = 1
            )
            SELECT 1 FROM x
            """
        )
    assert exc_info.value.reason is SqlRejectionReason.AMBIGUOUS_COLUMN


def test_cte_duplicate_aliases_case_fold_ambiguous() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(
            """
            WITH x AS (
                SELECT event_id AS value, name AS VALUE
                FROM events
            )
            SELECT 1 FROM x
            """
        )
    assert exc_info.value.reason is SqlRejectionReason.AMBIGUOUS_COLUMN


def test_derived_duplicate_outputs_ambiguous() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(
            """
            SELECT 1 FROM (
                SELECT events.event_id, ticket_tiers.event_id
                FROM events
                JOIN ticket_tiers ON 1 = 1
            ) AS x
            """
        )
    assert exc_info.value.reason is SqlRejectionReason.AMBIGUOUS_COLUMN


def test_non_ascii_output_names_remain_distinct() -> None:
    result = _validate(
        """
        WITH x AS (
            SELECT event_id AS "straße", name AS "strasse"
            FROM events
        )
        SELECT 1 FROM x
        """
    )
    assert result.referenced_tables == frozenset({"events"})
    assert result.referenced_columns == frozenset()


# --- Red 8: Union schemas ---


def test_union_output_names_from_first_branch() -> None:
    scope, _ = _union_scope(
        "SELECT event_id AS entity_id FROM events "
        "UNION ALL SELECT order_id AS entity_id FROM orders"
    )
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("entity_id",)
    assert schema.is_complete is True


def test_union_mismatched_branch_aliases_use_first_branch() -> None:
    scope, _ = _union_scope(
        "SELECT event_id AS left_name FROM events "
        "UNION ALL SELECT order_id AS right_name FROM orders"
    )
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("left_name",)
    assert "right_name" not in schema.folded_to_canonical


def test_union_unaliased_uses_first_branch_column_name() -> None:
    scope, _ = _union_scope(
        "SELECT event_id FROM events UNION ALL SELECT order_id FROM orders"
    )
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("event_id",)


def test_union_branch_arity_mismatch_rejected() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(
            "SELECT event_id, name FROM events UNION ALL SELECT order_id FROM orders"
        )
    assert exc_info.value.reason is SqlRejectionReason.INVALID_UNION_ARITY


def test_union_non_first_branch_star_marks_incomplete() -> None:
    scope, _ = _union_scope(
        "SELECT event_id FROM events UNION ALL SELECT * FROM events"
    )
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("event_id",)
    assert schema.is_complete is False


def test_union_values_branch_marks_incomplete_not_false_arity() -> None:
    # SQLGlot rewrites VALUES into SELECT * FROM (VALUES ...) AS _values.
    # Expression-count arity would falsely reject a SQLite-valid 2-vs-2 case.
    scope, _ = _union_scope("SELECT event_id, name FROM events UNION VALUES (1, 2)")
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("event_id", "name")
    assert schema.is_complete is False


def test_union_values_single_column_accepted_as_incomplete() -> None:
    result = _validate("SELECT event_id FROM events UNION VALUES (1)")
    assert result.referenced_tables == frozenset({"events"})
    assert result.referenced_columns == frozenset()


def test_derived_union_values_marks_incomplete() -> None:
    expression = sqlglot.parse_one(
        "SELECT 1 FROM (SELECT event_id, name FROM events UNION VALUES (1, 2)) AS x",
        read="sqlite",
    )
    from sqlglot import exp

    union_scopes = [
        s for s in traverse_scope(expression) if isinstance(s.expression, exp.Union)
    ]
    assert union_scopes
    schema = output_schema_for_scope(union_scopes[0])
    assert schema.is_complete is False


def test_parenthesized_union_still_uses_first_branch_names() -> None:
    result = _validate(
        "(SELECT event_id AS left_name FROM events) "
        "UNION ALL (SELECT order_id AS right_name FROM orders)"
    )
    assert result.referenced_tables == frozenset({"events", "orders"})
    assert result.referenced_columns == frozenset()


def test_cte_union_explicit_names_override_branch_projections() -> None:
    sql = (
        "WITH x(a, b) AS ("
        "SELECT event_id, name FROM events "
        "UNION ALL SELECT order_id, status FROM orders"
        ") SELECT 1 FROM x"
    )
    scope, _ = _union_scope(sql)
    assert scope.is_cte is True
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("a", "b")
    assert schema.is_complete is True
    assert "event_id" not in schema.folded_to_canonical
    assert schema.folded_to_canonical["a"] == "a"
    assert schema.folded_to_canonical["b"] == "b"
    result = _validate(sql)
    assert result.referenced_tables == frozenset({"events", "orders"})
    assert result.referenced_columns == frozenset()


def test_cte_union_explicit_arity_mismatch_rejected() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(
            "WITH x(a) AS ("
            "SELECT event_id, name FROM events "
            "UNION ALL SELECT order_id, status FROM orders"
            ") SELECT 1 FROM x"
        )
    assert exc_info.value.reason is SqlRejectionReason.INVALID_CTE_COLUMN_LIST


def test_cte_union_explicit_duplicate_names_ambiguous() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(
            "WITH x(a, a) AS ("
            "SELECT event_id, name FROM events "
            "UNION ALL SELECT order_id, status FROM orders"
            ") SELECT 1 FROM x"
        )
    assert exc_info.value.reason is SqlRejectionReason.AMBIGUOUS_COLUMN


def test_cte_union_explicit_list_over_star_remains_incomplete() -> None:
    sql = (
        "WITH x(a) AS ("
        "SELECT * FROM events "
        "UNION ALL SELECT order_id FROM orders"
        ") SELECT 1 FROM x"
    )
    scope, _ = _union_scope(sql)
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("a",)
    assert schema.is_complete is False
    assert schema.folded_to_canonical["a"] == "a"


# --- Stars: Strategy A ---


def test_star_internal_schema_incomplete_not_expanded() -> None:
    scope, _ = _cte_scope("WITH x AS (SELECT * FROM events) SELECT 1 FROM x")
    schema = output_schema_for_scope(scope)
    assert schema.is_complete is False
    assert dict(schema.folded_to_canonical) == {}
    # Must not invent physical inventory columns.
    assert "event_id" not in schema.folded_to_canonical
    assert "name" not in schema.folded_to_canonical


def test_qualified_star_internal_schema_incomplete() -> None:
    scope, _ = _derived_scope("SELECT 1 FROM (SELECT events.* FROM events) AS x")
    schema = output_schema_for_scope(scope)
    assert schema.is_complete is False


def test_explicit_cte_list_over_qualified_star_remains_incomplete() -> None:
    scope, _ = _cte_scope("WITH x(a) AS (SELECT events.* FROM events) SELECT 1 FROM x")
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("a",)
    assert schema.is_complete is False
    assert schema.folded_to_canonical["a"] == "a"


def test_count_star_alias_is_complete() -> None:
    scope, _ = _cte_scope(
        "WITH x AS (SELECT COUNT(*) AS total FROM events) SELECT 1 FROM x"
    )
    schema = output_schema_for_scope(scope)
    assert schema.canonical_names == ("total",)
    assert schema.is_complete is True


def test_star_containing_cte_accepted_without_column_binding() -> None:
    result = _validate("WITH x AS (SELECT * FROM events) SELECT 1 FROM x")
    assert result.referenced_tables == frozenset({"events"})
    assert result.referenced_columns == frozenset()


# --- Nested scopes ---


def test_nested_cte_schemas_do_not_treat_cte_as_physical() -> None:
    result = _validate(
        """
        WITH x AS (
            SELECT event_id FROM events
        ), y AS (
            SELECT event_id FROM x
        )
        SELECT 1 FROM y
        """
    )
    assert result.referenced_tables == frozenset({"events"})
    assert result.referenced_columns == frozenset()


# --- Red 9: AST non-mutation ---


@pytest.mark.parametrize(
    "sql",
    [
        "WITH x AS (SELECT event_id AS eid FROM events) SELECT 1 FROM x",
        "SELECT 1 FROM (SELECT event_id AS eid FROM events) AS x",
        "SELECT event_id AS left_name FROM events "
        "UNION ALL SELECT order_id AS right_name FROM orders",
    ],
)
def test_output_schema_extraction_does_not_mutate_ast(sql: str) -> None:
    expression = sqlglot.parse_one(sql, read="sqlite")
    before = expression.sql(dialect="sqlite", comments=False)
    validate_internal_output_schemas(expression)
    after = expression.sql(dialect="sqlite", comments=False)
    assert before == after


def test_public_original_normalized_fingerprint_preserved() -> None:
    sql = "  WITH x AS (SELECT event_id AS eid FROM events) SELECT 1 FROM x  "
    expected_original = sql.strip()
    expected_normalized = sqlglot.parse_one(expected_original, read="sqlite").sql(
        dialect="sqlite", comments=False
    )
    expected_fingerprint = hashlib.sha256(
        expected_normalized.encode("utf-8")
    ).hexdigest()
    result = _validate(sql)
    assert result.original_sql == expected_original
    assert result.normalized_sql == expected_normalized
    assert result.fingerprint == expected_fingerprint
    # Outer whitespace must remain trimmed-only in original_sql, never replaced
    # by normalized rendering even when they happen to match for compact SQL.
    spaced = "SELECT   1   FROM   events"
    spaced_result = _validate(spaced)
    assert spaced_result.original_sql == spaced
    assert spaced_result.normalized_sql != spaced
    assert spaced_result.normalized_sql == sqlglot.parse_one(spaced, read="sqlite").sql(
        dialect="sqlite", comments=False
    )


# --- Red 10: public boundary ---


def test_validate_sql_rejects_ambiguous_internal_outputs() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(
            "WITH x AS (SELECT event_id AS v, name AS V FROM events) SELECT 1 FROM x"
        )
    assert exc_info.value.reason is SqlRejectionReason.AMBIGUOUS_COLUMN


def test_referenced_columns_remain_empty() -> None:
    result = _validate("SELECT event_id, name FROM events")
    assert result.referenced_columns == frozenset()
    assert result.referenced_functions == frozenset()


def test_order_ref_sql_not_rejected_for_exclusion() -> None:
    result = validate_sql(
        "SELECT order_ref FROM orders",
        physical_tables=INVENTORY,
        physical_columns=frozenset({("orders", "order_ref"), ("orders", "status")}),
        prompt_visible_columns=frozenset({("orders", "status")}),
    )
    assert result.referenced_tables == frozenset({"orders"})
    assert result.referenced_columns == frozenset()


def test_unknown_sql_column_not_rejected_yet() -> None:
    result = _validate("SELECT nonexistent FROM events")
    assert result.referenced_tables == frozenset({"events"})
    assert result.referenced_columns == frozenset()


def test_structure_precedence_beats_ambiguous_column() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("INSERT INTO events DEFAULT VALUES")
    assert exc_info.value.reason is SqlRejectionReason.UNSUPPORTED_STATEMENT


def test_parameter_precedence_beats_ambiguous_column() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("WITH x AS (SELECT ? AS a, 1 AS A) SELECT 1 FROM x")
    assert exc_info.value.reason is SqlRejectionReason.PARAMETERIZED_SQL


def test_unknown_table_beats_output_schema_when_earlier() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(
            "WITH x AS ("
            "SELECT a.id AS v, b.id AS V FROM unknown_table a "
            "JOIN events b ON 1 = 1"
            ") SELECT 1 FROM x"
        )
    assert exc_info.value.reason is SqlRejectionReason.UNKNOWN_TABLE


def test_no_qualify_authority_for_schemas() -> None:
    import bse_nlq.sql_policy.column_inventory as inventory_mod
    import bse_nlq.sql_policy.output_schemas as mod

    source = open(mod.__file__, encoding="utf-8").read()
    assert "from sqlglot.optimizer.qualify" not in source
    assert "optimizer.qualify" not in source
    assert "sqlite3" not in source
    assert ".set(" not in source

    inventory_source = open(inventory_mod.__file__, encoding="utf-8").read()
    assert "from sqlglot.optimizer.qualify" not in inventory_source
    assert "optimizer.qualify" not in inventory_source
    assert "sqlite3" not in inventory_source
    assert ".execute(" not in inventory_source
