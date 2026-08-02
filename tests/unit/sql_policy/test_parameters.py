"""U2 Slice 2: parameter and placeholder rejection."""

from __future__ import annotations

import pytest
from policy_test_helpers import validate

from bse_nlq.sql_policy import SqlRejectedError, SqlRejectionReason, ValidatedSql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT ?",
        "SELECT :value",
        "SELECT @value",
        "SELECT $1",
        "SELECT $name",
        "SELECT 1 LIMIT ?",
        "SELECT 1 OFFSET :n",
        "SELECT 1 WHERE id = ?",
        "SELECT (?)",
        "SELECT 1 + ?",
        "SELECT ABS(?)",
        "WITH x AS (SELECT ? AS v) SELECT v FROM x",
        "SELECT 1 WHERE 1 IN (SELECT ?)",
        "SELECT 1 UNION SELECT ?",
        "SELECT 1 UNION ALL SELECT $1",
        "SELECT 1 UNION SELECT :value",
        "SELECT 1 UNION SELECT @value",
        "SELECT a.$1",
    ],
)
def test_parameters_rejected(sql: str) -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.PARAMETERIZED_SQL
    assert exc_info.value.__cause__ is None


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT '$1'",
        "SELECT '?'",
        "SELECT ':value'",
        "SELECT '@value'",
    ],
)
def test_parameter_like_string_literals_accepted(sql: str) -> None:
    result = validate(sql)
    assert isinstance(result, ValidatedSql)


@pytest.mark.parametrize(
    "sql",
    [
        'SELECT "$1"',
        'SELECT "$name"',
    ],
)
def test_parameter_like_quoted_identifiers_not_misclassified_as_parameterized(
    sql: str,
) -> None:
    # A double-quoted "$1" / "$name" is a column identifier, not a parameter;
    # structure policy must not reject it as PARAMETERIZED_SQL. With no FROM
    # clause it has no local source, so Slice 4C's unqualified-column binding
    # now rejects it as UNKNOWN_COLUMN instead — proving the distinction.
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.UNKNOWN_COLUMN


def test_unsupported_root_beats_parameter_precedence() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        validate("INSERT INTO events VALUES (?)")
    assert exc_info.value.reason is SqlRejectionReason.UNSUPPORTED_STATEMENT


def test_forbidden_nested_beats_parameter_when_both_present() -> None:
    # Supported Select root with nested Insert; Insert wins before params.
    sql = "WITH x AS (INSERT INTO t DEFAULT VALUES) SELECT ?"
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.FORBIDDEN_CONSTRUCT


def test_recursive_beats_parameter_precedence() -> None:
    sql = """
    WITH RECURSIVE x(n) AS (
        SELECT ?
        UNION ALL
        SELECT n + 1 FROM x
    )
    SELECT n FROM x
    """
    with pytest.raises(SqlRejectedError) as exc_info:
        validate(sql)
    assert exc_info.value.reason is SqlRejectionReason.RECURSIVE_CTE
