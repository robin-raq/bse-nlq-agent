"""SQL-policy errors for static validation."""

from __future__ import annotations

from enum import StrEnum


class SqlRejectionReason(StrEnum):
    """Closed reasons for SQL-policy failures in the current U2 slices.

    Slice 1 uses ``empty_sql``, ``multiple_statements``, and ``parse_error``.
    Slice 2 adds ``unsupported_statement``, ``forbidden_construct``,
    ``recursive_cte``, and ``parameterized_sql``. Slice 3 adds
    ``unknown_table``, ``qualified_table``, and ``unsupported_table_source``.
    Slice 4A adds ``ambiguous_column`` (duplicate internal outputs),
    ``invalid_cte_column_list`` (explicit CTE list arity mismatch), and
    ``invalid_union_arity`` (Union branch arity mismatch). Slice 4B adds
    qualified-column, exclusion, unsupported-column, and projection-star
    reasons. This is not a terminal-state enum.
    """

    EMPTY_SQL = "empty_sql"
    MULTIPLE_STATEMENTS = "multiple_statements"
    PARSE_ERROR = "parse_error"
    UNSUPPORTED_STATEMENT = "unsupported_statement"
    FORBIDDEN_CONSTRUCT = "forbidden_construct"
    RECURSIVE_CTE = "recursive_cte"
    PARAMETERIZED_SQL = "parameterized_sql"
    UNKNOWN_TABLE = "unknown_table"
    QUALIFIED_TABLE = "qualified_table"
    UNSUPPORTED_TABLE_SOURCE = "unsupported_table_source"
    AMBIGUOUS_COLUMN = "ambiguous_column"
    INVALID_CTE_COLUMN_LIST = "invalid_cte_column_list"
    INVALID_UNION_ARITY = "invalid_union_arity"
    PROJECTION_STAR = "projection_star"
    UNKNOWN_COLUMN_QUALIFIER = "unknown_column_qualifier"
    UNKNOWN_COLUMN = "unknown_column"
    EXCLUDED_COLUMN = "excluded_column"
    UNSUPPORTED_COLUMN_REFERENCE = "unsupported_column_reference"


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
