"""U2 Slice 2: whole-tree forbidden constructs and recursive CTEs."""

from __future__ import annotations

import pytest
from policy_test_helpers import validate

from bse_nlq.sql_policy import SqlRejectedError, SqlRejectionReason, ValidatedSql


def test_literal_drop_string_not_forbidden() -> None:
    result = validate("SELECT 'DROP TABLE events'")
    assert isinstance(result, ValidatedSql)


def test_nested_insert_in_cte_forbidden() -> None:
    sql = "WITH x AS (INSERT INTO t DEFAULT VALUES) SELECT 1"
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.FORBIDDEN_CONSTRUCT
    assert exc_info.value.__cause__ is None


def test_nested_delete_in_cte_forbidden() -> None:
    sql = "WITH x AS (DELETE FROM t) SELECT 1"
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.FORBIDDEN_CONSTRUCT


def test_nested_pragma_in_cte_forbidden() -> None:
    sql = "WITH x AS (PRAGMA table_info(events)) SELECT 1"
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.FORBIDDEN_CONSTRUCT


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO events DEFAULT VALUES",
        "UPDATE events SET name = 'x'",
        "DELETE FROM events",
        "REPLACE INTO events(id) VALUES(1)",
        "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET x = 1",
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
        "GRANT SELECT ON events TO u",
        "REVOKE SELECT ON events FROM u",
    ],
)
def test_forbidden_families_as_root_are_unsupported_not_forbidden(sql: str) -> None:
    """Root check wins over whole-tree forbidden (precedence)."""
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.UNSUPPORTED_STATEMENT


def test_recursive_cte_rejected() -> None:
    sql = """
    WITH RECURSIVE x(n) AS (
        SELECT 1
        UNION ALL
        SELECT n + 1 FROM x
    )
    SELECT n FROM x
    """
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.RECURSIVE_CTE
    assert exc_info.value.__cause__ is None


def test_ordinary_cte_accepted() -> None:
    result = validate("WITH x AS (SELECT 1 AS n) SELECT n FROM x")
    assert isinstance(result, ValidatedSql)


def test_multiple_ctes_one_recursive_rejected() -> None:
    sql = """
    WITH RECURSIVE
      a AS (SELECT 1 AS n),
      x(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM x)
    SELECT n FROM x
    """
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.RECURSIVE_CTE


def test_identifier_named_update_not_forbidden() -> None:
    result = validate('SELECT "update" FROM events')
    assert isinstance(result, ValidatedSql)
