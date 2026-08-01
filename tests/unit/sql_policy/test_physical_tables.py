"""U2 Slice 3: scope-aware physical-table authorization via scope.sources."""

from __future__ import annotations

import hashlib

import pytest
import sqlglot
from policy_test_helpers import (
    EMPTY_COLUMNS,
    EMPTY_VISIBLE,
    validate,
)

from bse_nlq.sql_policy import (
    SqlRejectedError,
    SqlRejectionReason,
    ValidatedSql,
    validate_sql,
)
from bse_nlq.sql_policy.scope_policy import authorize_physical_tables

INVENTORY: frozenset[str] = frozenset(
    {"venues", "events", "ticket_tiers", "orders", "order_items", "refunds"}
)


def _validate(sql: str, *, tables: frozenset[str] = INVENTORY) -> ValidatedSql:
    return validate_sql(
        sql,
        physical_tables=tables,
        physical_columns=EMPTY_COLUMNS,
        prompt_visible_columns=EMPTY_VISIBLE,
    )


# --- Red 1: canonical known tables ---


def test_select_without_from_has_empty_referenced_tables() -> None:
    result = _validate("SELECT 1")
    assert result.referenced_tables == frozenset()
    assert result.referenced_columns == frozenset()
    assert result.referenced_functions == frozenset()
    assert result.original_sql == "SELECT 1"


def test_known_top_level_table_accepted_canonically() -> None:
    result = _validate("SELECT 1 FROM events")
    assert isinstance(result, ValidatedSql)
    assert result.referenced_tables == frozenset({"events"})
    assert result.referenced_columns == frozenset()
    assert result.referenced_functions == frozenset()


def test_aliases_are_excluded_from_referenced_tables() -> None:
    result = _validate("SELECT 1 FROM events AS e")
    assert result.referenced_tables == frozenset({"events"})


def test_implicit_alias_excluded_from_referenced_tables() -> None:
    result = _validate("SELECT 1 FROM events e")
    assert result.referenced_tables == frozenset({"events"})


def test_self_join_deduplicates_referenced_tables() -> None:
    result = _validate("SELECT 1 FROM events e JOIN events e2 ON 1 = 1")
    assert result.referenced_tables == frozenset({"events"})


def test_multiple_known_tables_returned() -> None:
    result = _validate("SELECT 1 FROM events e JOIN orders o ON 1 = 1")
    assert result.referenced_tables == frozenset({"events", "orders"})


# --- Red 2: CTE and derived sources ---


def test_cte_name_not_treated_as_physical_table() -> None:
    sql = """
    WITH x AS (
        SELECT 1 FROM events
    )
    SELECT 1 FROM x
    """
    result = _validate(sql)
    assert result.referenced_tables == frozenset({"events"})


def test_cte_shadowing_physical_name_is_internal_only() -> None:
    sql = """
    WITH events AS (
        SELECT 1
    )
    SELECT 1 FROM events
    """
    result = _validate(sql)
    assert result.referenced_tables == frozenset()


def test_physical_table_inside_shadowing_cte_is_collected() -> None:
    sql = """
    WITH events AS (
        SELECT 1 FROM orders
    )
    SELECT 1 FROM events
    """
    result = _validate(sql)
    assert result.referenced_tables == frozenset({"orders"})


def test_derived_table_alias_not_collected() -> None:
    result = _validate("SELECT 1 FROM (SELECT 1 FROM events) AS x")
    assert result.referenced_tables == frozenset({"events"})


def test_union_branch_physical_tables_collected() -> None:
    result = _validate("SELECT 1 FROM events UNION ALL SELECT 1 FROM orders")
    assert result.referenced_tables == frozenset({"events", "orders"})


def test_nested_ctes_collect_physical_inner_tables() -> None:
    sql = """
    WITH x AS (
        SELECT 1 FROM events
    ), y AS (
        SELECT 1 FROM x
    )
    SELECT 1 FROM y
    """
    result = _validate(sql)
    assert result.referenced_tables == frozenset({"events"})


def test_values_derived_source_has_no_physical_tables() -> None:
    result = _validate("SELECT 1 FROM (VALUES (1)) AS x")
    assert result.referenced_tables == frozenset()


# --- Red 3: unknown tables ---


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 FROM unknown_table",
        "SELECT 1 FROM events e JOIN unknown_table u ON 1 = 1",
        "SELECT 1 FROM (SELECT 1 FROM unknown_table) AS x",
        """
        WITH x AS (
            SELECT 1 FROM unknown_table
        )
        SELECT 1 FROM x
        """,
        "SELECT 1 FROM events UNION ALL SELECT 1 FROM unknown_table",
    ],
    ids=("root", "join", "subquery", "cte", "union-second-branch"),
)
def test_unknown_physical_tables_rejected(sql: str) -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.UNKNOWN_TABLE
    assert exc_info.value.__cause__ is None


def test_unknown_table_aliased_as_allowed_name_still_rejected() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("SELECT 1 FROM unknown_table AS events")
    assert exc_info.value.reason is SqlRejectionReason.UNKNOWN_TABLE


# --- Red 4: casing and canonical names ---


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 FROM events",
        "SELECT 1 FROM EVENTS",
        "SELECT 1 FROM Events",
        'SELECT 1 FROM "events"',
        'SELECT 1 FROM "EVENTS"',
    ],
)
def test_case_and_quoting_resolve_to_inventory_canonical(sql: str) -> None:
    result = _validate(sql)
    assert result.referenced_tables == frozenset({"events"})
    assert result.original_sql == sql


def test_ascii_only_fold_rejects_strasse_against_strasse_eszett_inventory() -> None:
    """SQLite keeps straße and strasse distinct; casefold must not equate them."""
    with pytest.raises(SqlRejectedError) as exc_info:
        validate_sql(
            'SELECT 1 FROM "strasse"',
            physical_tables=frozenset({"straße"}),
            physical_columns=EMPTY_COLUMNS,
            prompt_visible_columns=EMPTY_VISIBLE,
        )
    assert exc_info.value.reason is SqlRejectionReason.UNKNOWN_TABLE


@pytest.mark.parametrize(
    ("inventory", "sql"),
    [
        (frozenset({"café"}), 'SELECT 1 FROM "CAFÉ"'),
        (frozenset({"Σ"}), 'SELECT 1 FROM "σ"'),
        (frozenset({"İ"}), 'SELECT 1 FROM "i"'),
    ],
    ids=("cafe-acute", "sigma", "turkish-I"),
)
def test_non_ascii_distinctions_follow_sqlite_ascii_folding(
    inventory: frozenset[str], sql: str
) -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        validate_sql(
            sql,
            physical_tables=inventory,
            physical_columns=EMPTY_COLUMNS,
            prompt_visible_columns=EMPTY_VISIBLE,
        )
    assert exc_info.value.reason is SqlRejectionReason.UNKNOWN_TABLE


def test_ascii_case_inside_non_ascii_name_matches() -> None:
    result = validate_sql(
        'SELECT 1 FROM "straße"',
        physical_tables=frozenset({"Straße"}),
        physical_columns=EMPTY_COLUMNS,
        prompt_visible_columns=EMPTY_VISIBLE,
    )
    assert result.referenced_tables == frozenset({"Straße"})


def test_distinct_non_ascii_inventory_entries_remain_distinct() -> None:
    inventory = frozenset({"straße", "strasse"})
    eszett = validate_sql(
        'SELECT 1 FROM "straße"',
        physical_tables=inventory,
        physical_columns=EMPTY_COLUMNS,
        prompt_visible_columns=EMPTY_VISIBLE,
    )
    ascii_ss = validate_sql(
        'SELECT 1 FROM "strasse"',
        physical_tables=inventory,
        physical_columns=EMPTY_COLUMNS,
        prompt_visible_columns=EMPTY_VISIBLE,
    )
    assert eszett.referenced_tables == frozenset({"straße"})
    assert ascii_ss.referenced_tables == frozenset({"strasse"})


def test_inventory_fold_collision_rejected_as_type_error() -> None:
    with pytest.raises(TypeError):
        validate_sql(
            "SELECT 1",
            physical_tables=frozenset({"events", "EVENTS"}),
            physical_columns=EMPTY_COLUMNS,
            prompt_visible_columns=EMPTY_VISIBLE,
        )


def test_empty_inventory_table_name_rejected_as_type_error() -> None:
    with pytest.raises(TypeError):
        validate_sql(
            "SELECT 1",
            physical_tables=frozenset({""}),
            physical_columns=EMPTY_COLUMNS,
            prompt_visible_columns=EMPTY_VISIBLE,
        )


def test_whitespace_inventory_table_name_rejected_as_type_error() -> None:
    with pytest.raises(TypeError):
        validate_sql(
            "SELECT 1",
            physical_tables=frozenset({" events"}),
            physical_columns=EMPTY_COLUMNS,
            prompt_visible_columns=EMPTY_VISIBLE,
        )


def test_caller_owned_physical_tables_frozenset_unchanged() -> None:
    inventory = frozenset({"events"})
    before = set(inventory)
    _validate("SELECT 1 FROM EVENTS", tables=inventory)
    assert set(inventory) == before
    assert inventory == frozenset({"events"})


# --- AST non-mutation and normalized-SQL isolation ---


def test_authorize_physical_tables_does_not_mutate_parsed_expression() -> None:
    sql = "SELECT 1 FROM EVENTS"
    expression = sqlglot.parse_one(sql, read="sqlite")
    before = expression.sql(dialect="sqlite", comments=False)
    referenced = authorize_physical_tables(
        expression, physical_tables=frozenset({"events"})
    )
    after = expression.sql(dialect="sqlite", comments=False)
    assert before == after == "SELECT 1 FROM EVENTS"
    assert referenced == frozenset({"events"})


def test_normalized_sql_and_fingerprint_independent_of_canonical_auth() -> None:
    sql = "SELECT 1 FROM EVENTS"
    expected_normalized = sqlglot.parse_one(sql, read="sqlite").sql(
        dialect="sqlite", comments=False
    )
    assert expected_normalized == "SELECT 1 FROM EVENTS"
    expected_fingerprint = hashlib.sha256(
        expected_normalized.encode("utf-8")
    ).hexdigest()

    result = validate_sql(
        sql,
        physical_tables=frozenset({"events"}),
        physical_columns=EMPTY_COLUMNS,
        prompt_visible_columns=EMPTY_VISIBLE,
    )
    assert result.original_sql == sql
    assert result.normalized_sql == expected_normalized
    assert result.fingerprint == expected_fingerprint
    assert result.referenced_tables == frozenset({"events"})


# --- Empty physical-table inventory ---


def test_empty_physical_inventory_accepts_select_without_from() -> None:
    result = validate_sql(
        "SELECT 1",
        physical_tables=frozenset(),
        physical_columns=frozenset(),
        prompt_visible_columns=frozenset(),
    )
    assert result.referenced_tables == frozenset()
    assert result.referenced_columns == frozenset()
    assert result.referenced_functions == frozenset()


def test_empty_physical_inventory_rejects_from_events() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        validate_sql(
            "SELECT 1 FROM events",
            physical_tables=frozenset(),
            physical_columns=frozenset(),
            prompt_visible_columns=frozenset(),
        )
    assert exc_info.value.reason is SqlRejectionReason.UNKNOWN_TABLE


# --- Red 5: qualifiers ---


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 FROM main.events",
        "SELECT 1 FROM temp.events",
        "SELECT 1 FROM other.events",
        'SELECT 1 FROM "main"."events"',
        "SELECT 1 FROM a.b.c",
    ],
)
def test_qualified_physical_tables_rejected(sql: str) -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.QUALIFIED_TABLE


# --- Red 6: unsupported source kinds ---


def test_table_valued_function_rejected_as_unsupported_source() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("SELECT 1 FROM json_each('[1,2]')")
    assert exc_info.value.reason is SqlRejectionReason.UNSUPPORTED_TABLE_SOURCE


# --- False-authority / adversarial ---


def test_string_literal_table_name_is_not_a_physical_reference() -> None:
    result = _validate("SELECT 'events'")
    assert result.referenced_tables == frozenset()


def test_comment_table_name_is_not_a_physical_reference() -> None:
    result = _validate("SELECT 1 /* events */")
    assert result.referenced_tables == frozenset()


def test_empty_physical_inventory_rejects_known_looking_table() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(
            "SELECT 1 FROM events",
        )
    assert exc_info.value.reason is SqlRejectionReason.UNKNOWN_TABLE


def test_unused_column_inventories_remain_type_validated_only() -> None:
    result = _validate(
        "SELECT 1 FROM events",
    )
    # Passing mismatched column inventories must not affect table auth yet.
    result2 = validate_sql(
        "SELECT 1 FROM events",
        physical_tables=INVENTORY,
        physical_columns=frozenset({("nope", "col")}),
        prompt_visible_columns=frozenset({("nope", "col")}),
    )
    assert result.referenced_tables == result2.referenced_tables
    assert result.referenced_tables == frozenset({"events"})
    assert result2.referenced_columns == frozenset()


def test_structure_precedence_beats_unknown_table() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("INSERT INTO unknown_table DEFAULT VALUES")
    assert exc_info.value.reason is SqlRejectionReason.UNSUPPORTED_STATEMENT


def test_parameter_precedence_before_table_auth_when_no_tables() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("SELECT ?")
    assert exc_info.value.reason is SqlRejectionReason.PARAMETERIZED_SQL


def test_unknown_table_with_parameter_prefers_parameter_when_earlier() -> None:
    # Parameters are checked before table auth in the documented precedence.
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("SELECT 1 FROM unknown_table WHERE id = ?")
    assert exc_info.value.reason is SqlRejectionReason.PARAMETERIZED_SQL
