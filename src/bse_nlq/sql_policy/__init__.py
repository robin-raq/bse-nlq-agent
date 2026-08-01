"""Static SQL policy: parse, validate shape, and return immutable ValidatedSql.

Slice 1 provides public imports, immutable models, SQL-policy errors, SQLGlot
SQLite parsing, outer-trim, empty/semicolon rejection, exactly-one meaningful
statement enforcement, deterministic normalization, and fingerprinting. Table,
column, star, function, date, parameter, and forbidden-construct policy remain
later slices. This package does not open SQLite or execute SQL.
"""

from __future__ import annotations

from bse_nlq.sql_policy.errors import (
    InvalidSqlError,
    SqlPolicyError,
    SqlRejectedError,
    SqlRejectionReason,
)
from bse_nlq.sql_policy.models import ValidatedSql
from bse_nlq.sql_policy.validator import validate_sql

__all__ = [
    "InvalidSqlError",
    "SqlPolicyError",
    "SqlRejectedError",
    "SqlRejectionReason",
    "ValidatedSql",
    "validate_sql",
]
