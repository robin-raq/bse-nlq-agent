"""Slice 4D: SQL function allowlist and deterministic-clock rejection.

The allowlist is sized to what the 14 executable anchors and the PRD's own
correctly-implemented example questions actually need: SUM and COALESCE
(anchors), plus COUNT (the ``COUNT(*)``-only star policy from Slice 4B already
assumes COUNT is otherwise a legitimate function). AVG is deliberately
excluded: the frozen ``average_ticket_price`` metric forbids naive
``AVG(unit_price_cents)`` in favor of the quantity-weighted ``SUM(...) /
SUM(...)`` form the anchors already use, so no anchor or correctly-implemented
PRD question needs it.
"""

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
        ("orders", "id"),
        ("orders", "amount"),
    }
)
VISIBLE_COLUMNS = PHYSICAL_COLUMNS


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


def test_forbidden_function_reason_value_is_stable() -> None:
    assert SqlRejectionReason.FORBIDDEN_FUNCTION.value == "forbidden_function"


def test_sum_is_allowed_and_recorded() -> None:
    result = _validate("SELECT SUM(amount) FROM orders")

    assert result.referenced_functions == frozenset({"SUM"})


def test_coalesce_is_allowed_and_recorded() -> None:
    result = _validate("SELECT COALESCE(amount, 0) FROM orders")

    assert result.referenced_functions == frozenset({"COALESCE"})


def test_count_star_is_allowed_and_recorded() -> None:
    result = _validate("SELECT COUNT(*) FROM orders")

    assert result.referenced_functions == frozenset({"COUNT"})


def test_count_column_is_allowed_and_recorded() -> None:
    result = _validate("SELECT COUNT(id) FROM orders")

    assert result.referenced_functions == frozenset({"COUNT"})


def test_referenced_functions_only_includes_functions_actually_present() -> None:
    result = _validate("SELECT id FROM orders")

    assert result.referenced_functions == frozenset()


def test_multiple_allowed_functions_all_recorded() -> None:
    result = _validate("SELECT SUM(amount), COUNT(*), COALESCE(amount, 0) FROM orders")

    assert result.referenced_functions == frozenset({"SUM", "COUNT", "COALESCE"})


def test_function_inside_cte_is_checked() -> None:
    sql = "WITH x AS (SELECT AVG(amount) AS a FROM orders) SELECT a FROM x"

    assert _rejection_reason(sql) is SqlRejectionReason.FORBIDDEN_FUNCTION


@pytest.mark.parametrize(
    "sql",
    (
        "SELECT AVG(amount) FROM orders",
        "SELECT MIN(amount) FROM orders",
        "SELECT MAX(amount) FROM orders",
        "SELECT ABS(amount) FROM orders",
        "SELECT ROUND(amount) FROM orders",
        "SELECT UPPER('x')",
    ),
)
def test_functions_outside_the_allowlist_are_rejected(sql: str) -> None:
    assert _rejection_reason(sql) is SqlRejectionReason.FORBIDDEN_FUNCTION


@pytest.mark.parametrize(
    "sql",
    (
        "SELECT CURRENT_DATE",
        "SELECT CURRENT_TIME",
        "SELECT CURRENT_TIMESTAMP",
        "SELECT date('now')",
        "SELECT date('now', 'localtime')",
        "SELECT datetime('now')",
        "SELECT datetime('now', 'utc')",
        "SELECT julianday('now')",
        "SELECT strftime('%s', 'now')",
        "SELECT unixepoch()",
    ),
)
def test_every_machine_clock_form_is_rejected(sql: str) -> None:
    assert _rejection_reason(sql) is SqlRejectionReason.FORBIDDEN_FUNCTION


def test_explicit_date_literal_comparison_needs_no_function_and_is_unaffected() -> None:
    # The anchors never call a date function; they compare literal ISO date
    # strings against columns. This must keep working untouched.
    result = _validate("SELECT id FROM events WHERE id > 0")

    assert result.referenced_functions == frozenset()
