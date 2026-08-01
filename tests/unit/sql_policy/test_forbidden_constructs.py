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
        "WITH x AS (SAVEPOINT y) SELECT 1",
        "WITH x AS (RELEASE y) SELECT 1",
        "WITH x AS (VALUES (1)) SELECT 1",
        "WITH x AS (SELECT 1 INTERSECT SELECT 1) SELECT 1",
    ],
    ids=("savepoint-alias", "release-alias", "values", "intersect"),
)
def test_invalid_cte_query_bodies_are_forbidden(sql: str) -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.FORBIDDEN_CONSTRUCT
    assert exc_info.value.__cause__ is None


@pytest.mark.parametrize(
    "sql",
    [
        "WITH x AS (SELECT 1) SELECT 1",
        "WITH x AS ((SELECT 1)) SELECT 1",
        "WITH x AS (SELECT 1 UNION SELECT 2) SELECT 1",
    ],
    ids=("select", "parenthesized-select", "union"),
)
def test_approved_cte_query_bodies_are_accepted(sql: str) -> None:
    result = validate(sql)
    assert isinstance(result, ValidatedSql)
    assert result.original_sql == sql


@pytest.mark.parametrize(
    ("sql", "node_name"),
    [
        ("WITH x AS (INSERT INTO t DEFAULT VALUES) SELECT 1", "Insert"),
        ("WITH x AS (UPDATE t SET a = 1 RETURNING a) SELECT 1", "Update"),
        ("WITH x AS (DELETE FROM t RETURNING a) SELECT 1", "Delete"),
        (
            "WITH x AS (MERGE INTO t USING s ON t.id = s.id "
            "WHEN MATCHED THEN UPDATE SET a = 1) SELECT 1",
            "Merge",
        ),
        ("WITH x AS (CREATE TABLE t(a INTEGER)) SELECT 1", "Create"),
        ("WITH x AS (DROP TABLE t) SELECT 1", "Drop"),
        ("WITH x AS (PRAGMA table_info(t)) SELECT 1", "Pragma"),
        ("WITH x AS (ATTACH DATABASE 'a.db' AS a) SELECT 1", "Attach"),
        ("WITH x AS (DETACH DATABASE a) SELECT 1", "Detach"),
        ("WITH x AS (VACUUM) SELECT 1", "Command"),
        ("WITH x AS (ANALYZE t) SELECT 1", "Analyze"),
        ("WITH x AS (BEGIN) SELECT 1", "Transaction"),
        ("WITH x AS (COMMIT) SELECT 1", "Commit"),
        ("WITH x AS (ROLLBACK) SELECT 1", "Rollback"),
    ],
    ids=(
        "insert",
        "update",
        "delete",
        "merge",
        "create",
        "drop",
        "pragma",
        "attach",
        "detach",
        "command",
        "analyze",
        "transaction",
        "commit",
        "rollback",
    ),
)
def test_reachable_forbidden_nodes_inside_ctes_are_rejected(
    sql: str, node_name: str
) -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.FORBIDDEN_CONSTRUCT
    assert str(exc_info.value) == f"Forbidden SQL construct: {node_name}"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 AS value",
        "SELECT e.event_id FROM events AS e",
        "SELECT REPLACE('abc', 'a', 'x') AS replaced",
    ],
    ids=("projection-alias", "table-alias", "replace-function-alias"),
)
def test_valid_aliases_remain_accepted(sql: str) -> None:
    result = validate(sql)
    assert isinstance(result, ValidatedSql)


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
