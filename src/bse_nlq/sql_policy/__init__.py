"""Static SQL policy: parse, validate shape/structure, return ValidatedSql.

Slice 1: public imports, immutable models, SQL-policy errors, SQLGlot SQLite
parsing, outer-trim, empty/semicolon rejection, exactly-one meaningful
statement, deterministic normalization, and fingerprinting.

Slice 2: allowed SELECT/UNION roots and CTE bodies, whole-tree
forbidden-construct rejection, recursive-CTE rejection, and
parameter/placeholder rejection.

Slice 3: physical-table authorization from SQLGlot ``scope.sources`` with
canonical ``referenced_tables`` output.

Slice 4A: canonical ``physical_columns`` / ``prompt_visible_columns``
inventories and internal CTE/derived/Union output-name schemas for duplicate
and arity detection.

Slice 4B: qualified physical/internal column binding, qualified lexical
correlation, prompt-exclusion enforcement, canonical ``referenced_columns``,
and ``COUNT(*)``-only star policy.

Slice 4C: unqualified column binding local to each scope (ambiguity-first, no
outer climbing) and ORDER BY projection-alias resolution.

Slice 4D: a fixed function allowlist (``SUM``, ``COUNT``, ``COALESCE``)
default-denies every other call, including every machine-clock form
(``CURRENT_DATE``/``CURRENT_TIME``/``CURRENT_TIMESTAMP``,
``date``/``datetime``/``julianday``/``strftime``/``unixepoch``); allowed names
populate ``referenced_functions``. This package does not open SQLite or
execute SQL.
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
