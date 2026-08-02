"""SQLGlot parsing, single-statement, normalize, and fingerprint Slice 1 tests."""

from __future__ import annotations

import hashlib
import re

import pytest
import sqlglot
from sqlglot.errors import ParseError

from bse_nlq.sql_policy import (
    InvalidSqlError,
    SqlRejectedError,
    SqlRejectionReason,
    ValidatedSql,
    validate_sql,
)

EMPTY_TABLES: frozenset[str] = frozenset()
EMPTY_COLUMNS: frozenset[tuple[str, str]] = frozenset()
EMPTY_VISIBLE: frozenset[tuple[str, str]] = frozenset()
SQL_INPUT_LIMIT = 16_384
SQL_AST_NODE_LIMIT = 512


def _validate(sql: object) -> ValidatedSql:
    return validate_sql(
        sql,  # type: ignore[arg-type]
        physical_tables=EMPTY_TABLES,
        physical_columns=EMPTY_COLUMNS,
        prompt_visible_columns=EMPTY_VISIBLE,
    )


def test_valid_select_one() -> None:
    result = _validate("SELECT 1")
    assert isinstance(result, ValidatedSql)
    assert result.original_sql == "SELECT 1"
    assert result.normalized_sql == "SELECT 1"
    assert result.fingerprint == hashlib.sha256(b"SELECT 1").hexdigest()
    assert isinstance(result.referenced_tables, frozenset)
    assert isinstance(result.referenced_columns, frozenset)
    assert isinstance(result.referenced_functions, frozenset)
    assert result.referenced_tables == frozenset()
    assert result.referenced_columns == frozenset()
    assert result.referenced_functions == frozenset()


def test_trailing_semicolon_single_statement() -> None:
    result = _validate("SELECT 1;")
    assert result.original_sql == "SELECT 1;"
    assert result.normalized_sql == "SELECT 1"


def test_outer_whitespace_trimmed_for_original_sql() -> None:
    result = _validate("  SELECT 1;  ")
    assert result.original_sql == "SELECT 1;"
    assert result.normalized_sql == "SELECT 1"


def test_internal_whitespace_preserved_in_original_sql() -> None:
    raw = "SELECT\n  1"
    result = _validate(f"  {raw}  ")
    assert result.original_sql == raw


def test_empty_sql_rejected() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("")
    assert exc_info.value.reason is SqlRejectionReason.EMPTY_SQL


def test_whitespace_only_rejected() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("   \n\t  ")
    assert exc_info.value.reason is SqlRejectionReason.EMPTY_SQL


def test_semicolon_only_rejected() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(";")
    assert exc_info.value.reason is SqlRejectionReason.EMPTY_SQL


def test_multiple_semicolons_only_rejected() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate(";;;")
    assert exc_info.value.reason is SqlRejectionReason.EMPTY_SQL


def test_multiple_statements_rejected() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        _validate("SELECT 1; SELECT 2;")
    assert exc_info.value.reason is SqlRejectionReason.MULTIPLE_STATEMENTS


def test_statement_followed_by_empty_semicolons_accepted() -> None:
    result = _validate("SELECT 1;;;")
    assert result.original_sql == "SELECT 1;;;"
    assert result.normalized_sql == "SELECT 1"


def test_bare_select_keyword_accepted_as_single_parsed_statement() -> None:
    # SQLGlot 30.14.0 accepts bare SELECT without raising; Slice 2 owns root policy.
    result = _validate("SELECT")
    assert result.original_sql == "SELECT"
    assert result.normalized_sql == "SELECT"


def test_inline_comment_preserved_in_original_stripped_in_normalized() -> None:
    result = _validate("SELECT /* comment */ 1")
    assert result.original_sql == "SELECT /* comment */ 1"
    assert result.normalized_sql == "SELECT 1"
    assert result.fingerprint == hashlib.sha256(b"SELECT 1").hexdigest()


def test_leading_comment_preserved_in_original() -> None:
    sql = "-- leading comment\nSELECT 1"
    result = _validate(sql)
    assert result.original_sql == sql
    assert result.normalized_sql == "SELECT 1"


def test_parse_error_becomes_invalid_sql_error_with_cause() -> None:
    with pytest.raises(InvalidSqlError) as exc_info:
        _validate("SELECT FROM")
    err = exc_info.value
    assert err.reason is SqlRejectionReason.PARSE_ERROR
    assert isinstance(err.__cause__, ParseError)
    message = err.args[0] if err.args else ""
    assert isinstance(message, str)
    assert message
    assert len(message) < 200
    # Public message must not dump the full ANSI-colored parser dump.
    assert "\x1b[" not in message


def test_sql_input_size_boundary_accepts_limit_and_rejects_next_character() -> None:
    prefix = "SELECT '"
    suffix = "'"
    at_limit = prefix + ("x" * (SQL_INPUT_LIMIT - len(prefix) - len(suffix))) + suffix
    above_limit = (
        prefix + ("x" * (SQL_INPUT_LIMIT + 1 - len(prefix) - len(suffix))) + suffix
    )
    assert len(at_limit) == SQL_INPUT_LIMIT
    assert len(above_limit) == SQL_INPUT_LIMIT + 1

    assert _validate(at_limit).original_sql == at_limit
    with pytest.raises(InvalidSqlError) as exc_info:
        _validate(above_limit)

    assert exc_info.value.reason is SqlRejectionReason.PARSE_ERROR
    assert exc_info.value.__cause__ is None
    assert "limit" in str(exc_info.value).lower()
    assert len(str(exc_info.value)) < 200


def test_ast_complexity_boundary_accepts_limit_and_rejects_next_node() -> None:
    at_limit = "SELECT " + ", ".join("1" for _ in range(SQL_AST_NODE_LIMIT - 1))
    above_limit = "SELECT " + ", ".join("1" for _ in range(SQL_AST_NODE_LIMIT))
    assert sum(1 for _ in sqlglot.parse_one(at_limit, read="sqlite").walk()) == 512
    assert sum(1 for _ in sqlglot.parse_one(above_limit, read="sqlite").walk()) == 513

    assert _validate(at_limit).original_sql == at_limit
    with pytest.raises(InvalidSqlError) as exc_info:
        _validate(above_limit)

    assert exc_info.value.reason is SqlRejectionReason.PARSE_ERROR
    assert exc_info.value.__cause__ is None
    assert "complex" in str(exc_info.value).lower()


def test_parser_recursion_error_becomes_invalid_sql_error_with_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recursion_error = RecursionError("adversarial nesting")

    def recurse(*args: object, **kwargs: object) -> list[object]:
        raise recursion_error

    monkeypatch.setattr(sqlglot, "parse", recurse)

    with pytest.raises(InvalidSqlError) as exc_info:
        _validate("SELECT 1")

    assert exc_info.value.reason is SqlRejectionReason.PARSE_ERROR
    assert exc_info.value.__cause__ is recursion_error
    assert "complex" in str(exc_info.value).lower()


def test_unexpected_parser_error_propagates_without_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    programming_error = RuntimeError("parser integration defect")

    def fail(*args: object, **kwargs: object) -> list[object]:
        raise programming_error

    monkeypatch.setattr(sqlglot, "parse", fail)

    with pytest.raises(RuntimeError) as exc_info:
        _validate("SELECT 1")

    assert exc_info.value is programming_error


def test_fingerprint_is_64_lowercase_hex() -> None:
    result = _validate("SELECT 1")
    assert re.fullmatch(r"[0-9a-f]{64}", result.fingerprint)


def test_casing_and_whitespace_normalize_consistently() -> None:
    a = _validate("select 1")
    b = _validate("  SELECT   1  ")
    assert a.normalized_sql == b.normalized_sql == "SELECT 1"
    assert a.fingerprint == b.fingerprint
    assert a.original_sql == "select 1"
    assert b.original_sql == "SELECT   1"


def test_structurally_different_statements_differ_in_fingerprint() -> None:
    a = _validate("SELECT 1")
    b = _validate("SELECT 2")
    assert a.fingerprint != b.fingerprint
    assert a.normalized_sql != b.normalized_sql


def test_original_sql_never_replaced_by_normalized() -> None:
    result = _validate("select /* keep */ 1")
    assert result.original_sql == "select /* keep */ 1"
    assert result.normalized_sql == "SELECT 1"
    assert result.original_sql != result.normalized_sql


def test_non_string_input_raises_type_error() -> None:
    with pytest.raises(TypeError):
        _validate(123)
    with pytest.raises(TypeError):
        _validate(b"SELECT 1")


def test_inventories_must_be_frozensets() -> None:
    with pytest.raises(TypeError):
        validate_sql(
            "SELECT 1",
            physical_tables={"events"},  # type: ignore[arg-type]
            physical_columns=EMPTY_COLUMNS,
            prompt_visible_columns=EMPTY_VISIBLE,
        )
    with pytest.raises(TypeError):
        validate_sql(
            "SELECT 1",
            physical_tables=EMPTY_TABLES,
            physical_columns={("events", "id")},  # type: ignore[arg-type]
            prompt_visible_columns=EMPTY_VISIBLE,
        )


def test_inventories_are_not_mutated() -> None:
    tables = frozenset({"events"})
    columns = frozenset({("events", "id")})
    visible = frozenset({("events", "id")})
    validate_sql(
        "SELECT 1",
        physical_tables=tables,
        physical_columns=columns,
        prompt_visible_columns=visible,
    )
    assert tables == frozenset({"events"})
    assert columns == frozenset({("events", "id")})
    assert visible == frozenset({("events", "id")})


def test_input_string_is_not_mutated() -> None:
    sql = "  SELECT 1  "
    before = sql
    _validate(sql)
    assert sql == before


def test_repeated_validation_equal_and_independent() -> None:
    first = _validate("SELECT 1")
    second = _validate("SELECT 1")
    assert first == second
    assert first is not second
    assert isinstance(first.referenced_tables, frozenset)
    assert isinstance(second.referenced_tables, frozenset)


def test_output_immutable() -> None:
    from dataclasses import FrozenInstanceError

    result = _validate("SELECT 1")
    with pytest.raises(FrozenInstanceError):
        result.normalized_sql = "SELECT 2"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        result.referenced_tables.add("x")  # type: ignore[attr-defined]


def test_slice3_rejects_unknown_physical_tables() -> None:
    with pytest.raises(SqlRejectedError) as exc_info:
        validate_sql(
            "SELECT 1 FROM nonexistent_table",
            physical_tables=frozenset({"events"}),
            physical_columns=frozenset({("events", "id")}),
            prompt_visible_columns=frozenset({("events", "id")}),
        )
    assert exc_info.value.reason is SqlRejectionReason.UNKNOWN_TABLE
