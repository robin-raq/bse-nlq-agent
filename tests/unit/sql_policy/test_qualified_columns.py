"""Slice 4B qualified-column binding and star-policy tests."""

from __future__ import annotations

from pathlib import Path

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


def test_slice_4b_rejection_reason_values_are_stable() -> None:
    assert SqlRejectionReason.PROJECTION_STAR.value == "projection_star"
    assert (
        SqlRejectionReason.UNKNOWN_COLUMN_QUALIFIER.value == "unknown_column_qualifier"
    )
    assert SqlRejectionReason.UNKNOWN_COLUMN.value == "unknown_column"
    assert SqlRejectionReason.EXCLUDED_COLUMN.value == "excluded_column"
    assert (
        SqlRejectionReason.UNSUPPORTED_COLUMN_REFERENCE.value
        == "unsupported_column_reference"
    )


def test_local_qualified_physical_column_records_canonical_identity() -> None:
    result = _validate("SELECT E.ID FROM EVENTS AS E")

    assert result.referenced_columns == frozenset({("events", "id")})


def test_qualified_correlation_climbs_to_nearest_lexical_scope() -> None:
    result = _validate(
        "SELECT e.id FROM events AS e "
        "WHERE EXISTS ("
        "SELECT 1 FROM orders AS o WHERE o.event_id = e.id"
        ")"
    )

    assert result.referenced_columns == frozenset(
        {("events", "id"), ("orders", "event_id")}
    )


def test_inner_qualifier_shadows_outer_qualifier() -> None:
    result = _validate(
        "SELECT e.id FROM events AS e "
        "WHERE EXISTS (SELECT 1 FROM orders AS e WHERE e.id > 0)"
    )

    assert result.referenced_columns == frozenset({("events", "id"), ("orders", "id")})


def test_missing_inner_column_does_not_fall_back_to_outer_qualifier() -> None:
    sql = (
        "SELECT e.name FROM events AS e "
        "WHERE EXISTS (SELECT 1 FROM orders AS e WHERE e.name = 'x')"
    )

    assert _rejection_reason(sql) is SqlRejectionReason.UNKNOWN_COLUMN


def test_missing_near_internal_column_does_not_fall_back_to_outer_physical() -> None:
    sql = (
        "WITH x AS (SELECT source.id AS event_id FROM events AS source) "
        "SELECT e.name FROM events AS e "
        "WHERE EXISTS ("
        "SELECT 1 FROM x AS e WHERE EXISTS (SELECT 1 WHERE e.name = 'x')"
        ")"
    )

    assert _rejection_reason(sql) is SqlRejectionReason.UNKNOWN_COLUMN


def test_unknown_qualified_column_is_distinct_from_unknown_qualifier() -> None:
    assert (
        _rejection_reason("SELECT e.missing FROM events AS e")
        is SqlRejectionReason.UNKNOWN_COLUMN
    )
    assert (
        _rejection_reason("SELECT missing.id FROM events AS e")
        is SqlRejectionReason.UNKNOWN_COLUMN_QUALIFIER
    )


def test_alias_replaces_physical_table_name_as_qualifier() -> None:
    assert (
        _rejection_reason("SELECT events.id FROM events AS e")
        is SqlRejectionReason.UNKNOWN_COLUMN_QUALIFIER
    )


def test_excluded_qualified_physical_column_is_rejected() -> None:
    assert (
        _rejection_reason("SELECT o.order_ref FROM orders AS o")
        is SqlRejectionReason.EXCLUDED_COLUMN
    )


def test_correlated_excluded_physical_column_is_rejected() -> None:
    sql = (
        "SELECT 1 FROM orders AS o "
        "WHERE EXISTS (SELECT 1 WHERE o.order_ref = 'private')"
    )

    assert _rejection_reason(sql) is SqlRejectionReason.EXCLUDED_COLUMN


def test_correlated_internal_source_validates_without_recording_internal_pair() -> None:
    result = _validate(
        "WITH x AS (SELECT e.id AS event_id FROM events AS e) "
        "SELECT x.event_id FROM x "
        "WHERE EXISTS (SELECT 1 WHERE x.event_id > 0)"
    )

    assert result.referenced_columns == frozenset({("events", "id")})


def test_unknown_internal_output_is_rejected_as_unknown_column() -> None:
    assert (
        _rejection_reason(
            "WITH x AS (SELECT e.id AS event_id FROM events AS e) "
            "SELECT x.missing FROM x"
        )
        is SqlRejectionReason.UNKNOWN_COLUMN
    )


@pytest.mark.parametrize(
    "sql",
    (
        "SELECT * FROM events",
        "SELECT e.* FROM events AS e",
        "SELECT 1 WHERE EXISTS (SELECT * FROM events)",
    ),
)
def test_projection_stars_are_rejected(sql: str) -> None:
    assert _rejection_reason(sql) is SqlRejectionReason.PROJECTION_STAR


def test_count_star_is_allowed_without_column_reference() -> None:
    result = _validate("SELECT COUNT(*) FROM events AS e")

    assert result.referenced_columns == frozenset()


def test_qualified_star_inside_count_is_not_count_star() -> None:
    assert (
        _rejection_reason("SELECT COUNT(e.*) FROM events AS e")
        is SqlRejectionReason.PROJECTION_STAR
    )


def test_qualified_columns_bind_in_join_filter_and_order_contexts() -> None:
    result = _validate(
        "SELECT e.id FROM events AS e "
        "JOIN orders AS o ON o.event_id = e.id "
        "WHERE o.id > 0 ORDER BY e.name"
    )

    assert result.referenced_columns == frozenset(
        {
            ("events", "id"),
            ("events", "name"),
            ("orders", "event_id"),
            ("orders", "id"),
        }
    )


def test_sqlglot_values_union_synthetic_star_remains_supported() -> None:
    result = _validate("SELECT e.id FROM events AS e UNION VALUES (1)")

    assert result.referenced_columns == frozenset({("events", "id")})


def test_unqualified_binding_remains_deferred_to_slice_4c() -> None:
    result = _validate("SELECT missing, order_ref FROM orders")

    assert result.referenced_columns == frozenset()


def test_projection_alias_binding_remains_deferred_to_slice_4c() -> None:
    result = _validate("SELECT e.id AS value FROM events AS e ORDER BY value")

    assert result.referenced_columns == frozenset({("events", "id")})


@pytest.mark.parametrize(
    "sql",
    (
        "WITH x AS (SELECT e.id) SELECT 1 FROM events AS e",
        "SELECT 1 FROM events AS e JOIN (SELECT e.id AS value) AS x ON 1 = 1",
    ),
)
def test_cte_and_derived_scopes_do_not_gain_lateral_outer_lookup(sql: str) -> None:
    assert _rejection_reason(sql) is SqlRejectionReason.UNKNOWN_COLUMN_QUALIFIER


def test_multipart_column_reference_is_rejected_explicitly() -> None:
    assert (
        _rejection_reason("SELECT main.e.id FROM events AS e")
        is SqlRejectionReason.UNSUPPORTED_COLUMN_REFERENCE
    )


def test_internal_schema_programming_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import bse_nlq.sql_policy.column_policy as policy

    programming_error = TypeError("schema implementation defect")

    def fail(*args: object, **kwargs: object) -> object:
        raise programming_error

    monkeypatch.setattr(policy, "output_schema_for_scope", fail)

    with pytest.raises(TypeError) as exc_info:
        _validate(
            "WITH x AS (SELECT e.id AS event_id FROM events AS e) "
            "SELECT x.event_id FROM x"
        )

    assert exc_info.value is programming_error


def test_column_policy_has_no_external_authority_or_ast_mutation() -> None:
    import bse_nlq.sql_policy.column_policy as policy

    source = Path(policy.__file__).read_text(encoding="utf-8")
    assert "optimizer.qualify" not in source
    assert "sqlite3" not in source
    assert ".execute(" not in source
    assert ".set(" not in source
