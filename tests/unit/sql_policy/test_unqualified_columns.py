"""Slice 4C unqualified-column binding and ORDER BY alias tests."""

from __future__ import annotations

import pytest

from bse_nlq.sql_policy import (
    SqlRejectedError,
    SqlRejectionReason,
    ValidatedSql,
    validate_sql,
)

TABLES = frozenset({"events", "orders"})
PHYSICAL_COLUMNS = frozenset(
    {
        ("events", "id"),
        ("events", "name"),
        ("orders", "id"),
        ("orders", "event_id"),
        ("orders", "order_ref"),
    }
)
VISIBLE_COLUMNS = PHYSICAL_COLUMNS - {("orders", "order_ref")}


def _validate(sql: str) -> ValidatedSql:
    return validate_sql(
        sql,
        physical_tables=TABLES,
        physical_columns=PHYSICAL_COLUMNS,
        prompt_visible_columns=VISIBLE_COLUMNS,
    )


def _rejection_reason(sql: str) -> SqlRejectionReason:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(sql)
    return exc_info.value.reason


def test_unqualified_physical_column_from_one_local_source_binds() -> None:
    result = _validate("SELECT id FROM events")

    assert result.referenced_columns == frozenset({("events", "id")})


def test_unqualified_output_column_from_local_cte_binds() -> None:
    result = _validate(
        "WITH x AS (SELECT id AS event_id FROM events) SELECT event_id FROM x"
    )

    assert result.referenced_columns == frozenset({("events", "id")})


def test_unqualified_output_column_from_local_derived_table_binds() -> None:
    result = _validate("SELECT event_id FROM (SELECT id AS event_id FROM events) AS x")

    assert result.referenced_columns == frozenset({("events", "id")})


def test_unqualified_column_ambiguous_across_two_local_sources() -> None:
    sql = "SELECT id FROM events JOIN orders ON orders.event_id = events.id"

    assert _rejection_reason(sql) is SqlRejectionReason.AMBIGUOUS_COLUMN


def test_unqualified_column_ambiguous_across_self_join() -> None:
    sql = "SELECT id FROM orders AS o1 JOIN orders AS o2 ON o1.id = o2.id"

    assert _rejection_reason(sql) is SqlRejectionReason.AMBIGUOUS_COLUMN


def test_unqualified_excluded_physical_column_is_rejected() -> None:
    assert (
        _rejection_reason("SELECT order_ref FROM orders")
        is SqlRejectionReason.EXCLUDED_COLUMN
    )


def test_unknown_unqualified_column_is_rejected() -> None:
    assert (
        _rejection_reason("SELECT missing FROM events")
        is SqlRejectionReason.UNKNOWN_COLUMN
    )


def test_zero_local_candidates_rejected_as_unknown_not_climbed() -> None:
    # "name" exists on the outer "events" source but the inner scope's only
    # local source is "orders", which has no "name" column. Per the Slice 4C
    # locked rule, zero local candidates never climbs to the outer scope.
    sql = (
        "SELECT e.name FROM events AS e "
        "WHERE EXISTS (SELECT 1 FROM orders WHERE name > 0)"
    )

    assert _rejection_reason(sql) is SqlRejectionReason.UNKNOWN_COLUMN


def test_order_by_alias_wins_over_local_column_of_the_same_name() -> None:
    # SQLite prefers the result-column alias for ORDER BY; "id" here resolves
    # to the projection alias, not a fresh unqualified "id" lookup.
    result = _validate("SELECT name AS id FROM events ORDER BY id")

    assert result.referenced_columns == frozenset({("events", "name")})


def test_order_by_alias_only_applies_within_order_by() -> None:
    # The same name in WHERE is an ordinary unqualified lookup, not an alias
    # reference, per the Slice 4C ORDER-BY-only scope exclusion.
    sql = "SELECT id AS value FROM events WHERE value > 0"

    assert _rejection_reason(sql) is SqlRejectionReason.UNKNOWN_COLUMN


def test_order_by_alias_over_aggregate_with_group_by_matches_anchor_pattern() -> None:
    # Mirrors the take-home anchors' own shape, e.g.
    # "SUM(...) AS x ... ORDER BY x DESC, <qualified tiebreaker>".
    result = _validate(
        "SELECT SUM(id) AS total FROM events GROUP BY name ORDER BY total DESC"
    )

    assert result.referenced_columns == frozenset(
        {("events", "id"), ("events", "name")}
    )


def test_unqualified_excluded_having_column_is_rejected() -> None:
    # SQLGlot's scope.columns omits unqualified HAVING refs; they must still
    # be authorized. order_ref is physical but prompt-excluded.
    assert (
        _rejection_reason("SELECT COUNT(*) FROM orders HAVING order_ref = 'secret'")
        is SqlRejectionReason.EXCLUDED_COLUMN
    )


def test_unqualified_unknown_having_column_is_rejected() -> None:
    assert (
        _rejection_reason("SELECT COUNT(*) FROM orders HAVING no_such_col = 1")
        is SqlRejectionReason.UNKNOWN_COLUMN
    )


def test_qualified_excluded_having_column_still_rejected() -> None:
    # Qualified HAVING refs are already present in scope.columns; keep that path.
    assert (
        _rejection_reason(
            "SELECT COUNT(*) FROM orders AS o HAVING o.order_ref = 'secret'"
        )
        is SqlRejectionReason.EXCLUDED_COLUMN
    )


def test_unqualified_allowed_having_physical_column_binds() -> None:
    # Column appears only in HAVING so scope.columns is empty for it; the
    # HAVING walk must still bind and record the physical identity.
    result = _validate("SELECT COUNT(*) FROM orders HAVING id > 0")

    assert result.referenced_columns == frozenset({("orders", "id")})


def test_having_does_not_resolve_projection_alias() -> None:
    # Slice 4C: WHERE / JOIN ON / GROUP BY / HAVING never see alias binding.
    # "total" is only a projection alias here, so HAVING total is unknown.
    assert (
        _rejection_reason(
            "SELECT SUM(id) AS total FROM events GROUP BY name HAVING total > 0"
        )
        is SqlRejectionReason.UNKNOWN_COLUMN
    )
