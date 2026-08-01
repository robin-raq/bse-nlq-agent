"""SQL-policy errors for static validation."""

from __future__ import annotations

from enum import StrEnum


class SqlRejectionReason(StrEnum):
    """Closed reasons for SQL-policy failures in the current U2 slices.

    Slice 1 uses ``empty_sql``, ``multiple_statements``, and ``parse_error``.
    Slice 2 adds ``unsupported_statement``, ``forbidden_construct``,
    ``recursive_cte``, and ``parameterized_sql``. This is not a terminal-state
    enum.
    """

    EMPTY_SQL = "empty_sql"
    MULTIPLE_STATEMENTS = "multiple_statements"
    PARSE_ERROR = "parse_error"
    UNSUPPORTED_STATEMENT = "unsupported_statement"
    FORBIDDEN_CONSTRUCT = "forbidden_construct"
    RECURSIVE_CTE = "recursive_cte"
    PARAMETERIZED_SQL = "parameterized_sql"


class SqlPolicyError(Exception):
    """Base error for static SQL-policy validation failures."""


class InvalidSqlError(SqlPolicyError):
    """Raised when SQL cannot be parsed into a usable statement.

    SQLGlot parse failures surface as this type with the original parse
    exception attached as ``__cause__``. Programming defects are never
    converted to this type. This phase does not map onto application terminal
    states.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: SqlRejectionReason = SqlRejectionReason.PARSE_ERROR,
    ) -> None:
        super().__init__(message)
        self.reason = reason


class SqlRejectedError(SqlPolicyError):
    """Raised when parsed SQL is rejected by an application policy rule.

    Distinguishes policy rejection from malformed SQL (``InvalidSqlError``).
    This phase does not map onto application terminal states.
    """

    def __init__(self, message: str, *, reason: SqlRejectionReason) -> None:
        super().__init__(message)
        self.reason = reason
