"""Static DDL safety tests.

Inspects the raw DDL text for clock-dependent tokens and CREATE TRIGGER,
independent of any applied connection.
"""

import re

from bse_nlq.db.schema import _SCHEMA_SQL

_CLOCK_DEPENDENT_TOKENS = (
    "CURRENT_DATE",
    "CURRENT_TIME",
    "CURRENT_TIMESTAMP",
    "date('now')",
    "datetime('now')",
    "time('now')",
    "localtime",
)


def test_ddl_contains_no_clock_dependent_tokens() -> None:
    ddl_lower = _SCHEMA_SQL.lower()
    for token in _CLOCK_DEPENDENT_TOKENS:
        assert token.lower() not in ddl_lower, f"clock-dependent token found: {token}"


def test_ddl_contains_no_now_literal() -> None:
    assert not re.search(r"\bnow\b", _SCHEMA_SQL, flags=re.IGNORECASE)


def test_ddl_contains_no_create_trigger() -> None:
    assert not re.search(r"create\s+trigger", _SCHEMA_SQL, flags=re.IGNORECASE)


def test_timestamp_checks_use_null_safe_is_strftime() -> None:
    """Exactly three timestamp CHECKs must use IS strftime, never = strftime.

    A silent IS→= swap on any of start_local, purchased_at, or refunded_at
    must fail this static guard. Unrelated IS / = / strftime uses elsewhere
    in the DDL are ignored.
    """
    normalized = re.sub(r"\s+", " ", _SCHEMA_SQL)
    columns = ("start_local", "purchased_at", "refunded_at")
    is_matches = re.findall(
        r"CHECK\s*\(\s*(start_local|purchased_at|refunded_at)\s+IS\s+strftime\s*\(",
        normalized,
        flags=re.IGNORECASE,
    )
    eq_matches = re.findall(
        r"CHECK\s*\(\s*(start_local|purchased_at|refunded_at)\s*=\s*strftime\s*\(",
        normalized,
        flags=re.IGNORECASE,
    )
    assert sorted(name.lower() for name in is_matches) == sorted(columns)
    assert eq_matches == []
