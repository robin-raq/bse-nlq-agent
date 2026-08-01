"""U2 Slice 2: allowed query-root families and unsupported roots."""

from __future__ import annotations

import pytest
from policy_test_helpers import validate

from bse_nlq.sql_policy import SqlRejectedError, SqlRejectionReason, ValidatedSql


def test_select_accepted() -> None:
    result = validate("SELECT 1")
    assert isinstance(result, ValidatedSql)
    assert result.original_sql == "SELECT 1"
    assert result.referenced_tables == frozenset()


def test_nonrecursive_cte_accepted() -> None:
    sql = "WITH x AS (SELECT 1 AS value) SELECT value FROM x"
    result = validate(sql)
    assert isinstance(result, ValidatedSql)
    assert result.original_sql == sql


def test_nested_subquery_accepted() -> None:
    result = validate("SELECT 1 WHERE 1 IN (SELECT 2)")
    assert isinstance(result, ValidatedSql)


def test_parenthesized_select_accepted() -> None:
    result = validate("(SELECT 1)")
    assert isinstance(result, ValidatedSql)
    assert result.original_sql == "(SELECT 1)"


def test_union_accepted() -> None:
    result = validate("SELECT 1 UNION SELECT 2")
    assert isinstance(result, ValidatedSql)


def test_union_all_accepted() -> None:
    result = validate("SELECT 1 UNION ALL SELECT 2")
    assert isinstance(result, ValidatedSql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 INTERSECT SELECT 1",
        "SELECT 1 EXCEPT SELECT 2",
        "VALUES (1)",
        "INSERT INTO events DEFAULT VALUES",
        "UPDATE events SET name = 'x'",
        "DELETE FROM events",
        "CREATE TABLE x(id INTEGER)",
        "DROP TABLE events",
        "ALTER TABLE events ADD COLUMN x TEXT",
        "TRUNCATE TABLE events",
        "PRAGMA table_info(events)",
        "ATTACH DATABASE 'x.db' AS x",
        "DETACH DATABASE x",
        "VACUUM",
        "ANALYZE",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT x",
        "RELEASE x",
        "GRANT SELECT ON events TO u",
        "REVOKE SELECT ON events FROM u",
        "REPLACE INTO events(id) VALUES(1)",
        "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET x = 1",
    ],
)
def test_unsupported_roots_rejected(sql: str) -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.UNSUPPORTED_STATEMENT
    assert exc_info.value.__cause__ is None


def test_mixed_casing_select_accepted() -> None:
    result = validate("select 1")
    assert isinstance(result, ValidatedSql)


def test_comments_and_whitespace_select_accepted() -> None:
    result = validate("  /* c */ SELECT /* x */ 1  ")
    assert result.original_sql == "/* c */ SELECT /* x */ 1"


def test_allowed_query_then_forbidden_second_statement() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        validate("SELECT 1; DROP TABLE events")
    assert exc_info.value.reason is SqlRejectionReason.MULTIPLE_STATEMENTS


def test_forbidden_statement_with_trailing_empty_semicolons_unsupported() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        validate("DROP TABLE events;;;")
    assert exc_info.value.reason is SqlRejectionReason.UNSUPPORTED_STATEMENT
