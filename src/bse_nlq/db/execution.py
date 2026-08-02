"""Default-deny SQLite authorizer and controlled execution boundary (U3).

Accepts only ``ValidatedSql`` and executes ``validated_sql.original_sql``,
never a raw string or ``normalized_sql``. A ``sqlite3.Connection`` authorizer
allows exactly three action codes — ``SQLITE_SELECT`` unconditionally,
``SQLITE_READ`` only for tables/columns in the query's own
``referenced_tables`` / ``referenced_columns``, and ``SQLITE_FUNCTION`` only
for the same fixed function allowlist the static policy already enforces
(``bse_nlq.sql_policy.function_policy.ALLOWED_FUNCTION_NAMES``) — and denies
every other action code, including unknown ones, by a single catch-all
default-deny branch. This is deliberately not a general SQLite-authorizer
framework: it is scoped to authorizing exactly what the already-validated
query is permitted to touch.

A progress handler bounds total VDBE instructions; row and column counts are
hard-capped with overflow rejection rather than silent truncation. Both
callbacks are installed immediately before execution and removed in
``finally`` so a failure never leaves them attached to the connection for a
later, unrelated query.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from bse_nlq.db.errors import ExecutionErrorReason, SqlExecutionError
from bse_nlq.db.runtime import ReadOnlyDatabase
from bse_nlq.sql_policy.function_policy import ALLOWED_FUNCTION_NAMES
from bse_nlq.sql_policy.models import ValidatedSql
from bse_nlq.sql_policy.scope_policy import fold_sqlite_identifier

# Real anchor queries run in roughly 1,000-1,700 VDBE opcodes against the
# 109-row seed. This budget gives ~500x headroom while still bounding a
# runaway or adversarial query.
_PROGRESS_OPCODE_INTERVAL = 1000
_MAX_PROGRESS_CALLS = 1000

# The dataset has 109 total rows across all six tables; both caps are
# generous relative to any legitimate join or aggregate over it.
_MAX_ROWS = 500
_MAX_COLUMNS = 20

_Authorizer = Callable[[int, str | None, str | None, str | None, str | None], int]


@dataclass(frozen=True, slots=True)
class RawQueryResult:
    """Immutable raw execution result: column names and row tuples."""

    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]


def execute_validated_sql(
    database: ReadOnlyDatabase, validated_sql: ValidatedSql
) -> RawQueryResult:
    """Execute statically-validated SQL under default-deny SQLite safeguards.

    Raises ``SqlExecutionError`` for authorizer denial, opcode-budget
    exhaustion, row/column overflow, or any other SQLite execution failure,
    with the reason distinguishing each case and the original SQLite
    exception preserved as ``__cause__`` where one exists. Programming
    defects and ``KeyboardInterrupt`` / ``SystemExit`` propagate unchanged.
    """
    if not isinstance(validated_sql, ValidatedSql):
        raise TypeError("validated_sql must be ValidatedSql")

    connection = database._connection
    authorizer = _build_authorizer(validated_sql)
    progress_calls = [0]

    def _progress() -> int:
        progress_calls[0] += 1
        return 1 if progress_calls[0] > _MAX_PROGRESS_CALLS else 0

    connection.set_authorizer(authorizer)
    connection.set_progress_handler(_progress, _PROGRESS_OPCODE_INTERVAL)
    try:
        cursor = connection.execute(validated_sql.original_sql)
        description = cursor.description or ()
        if len(description) > _MAX_COLUMNS:
            raise SqlExecutionError(
                f"Result has too many columns: {len(description)}",
                reason=ExecutionErrorReason.COLUMN_LIMIT_EXCEEDED,
            )
        columns = tuple(column[0] for column in description)
        rows: list[tuple[object, ...]] = []
        for row in cursor:
            rows.append(tuple(row))
            if len(rows) > _MAX_ROWS:
                raise SqlExecutionError(
                    f"Result exceeds the row limit of {_MAX_ROWS}",
                    reason=ExecutionErrorReason.ROW_LIMIT_EXCEEDED,
                )
        return RawQueryResult(columns=columns, rows=tuple(rows))
    except sqlite3.DatabaseError as error:
        # sqlite3 gives no single structured signal that distinguishes these
        # cases consistently: denying a whole statement (write/PRAGMA/ATTACH/
        # transaction/schema change) or a column/table read raises
        # DatabaseError with sqlite_errorcode SQLITE_AUTH and either "not
        # authorized" or "access to ... is prohibited" wording; denying a
        # function raises OperationalError (still a DatabaseError subclass)
        # with the "not authorized to use function" wording but an unrelated
        # sqlite_errorcode (SQLITE_ERROR). Neither signal alone covers every
        # denial path, so both are checked.
        message = str(error)
        if "interrupted" in message:
            raise SqlExecutionError(
                "SQL exceeded the execution instruction budget",
                reason=ExecutionErrorReason.EXECUTION_BUDGET_EXCEEDED,
            ) from error
        if (
            getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_AUTH
            or "not authorized" in message
        ):
            raise SqlExecutionError(
                "SQL execution was denied by the authorizer",
                reason=ExecutionErrorReason.AUTHORIZATION_DENIED,
            ) from error
        raise SqlExecutionError(
            "SQL execution failed", reason=ExecutionErrorReason.EXECUTION_FAILED
        ) from error
    except sqlite3.Error as error:
        raise SqlExecutionError(
            "SQL execution failed", reason=ExecutionErrorReason.EXECUTION_FAILED
        ) from error
    finally:
        connection.set_progress_handler(None, 0)
        connection.set_authorizer(None)


def _build_authorizer(validated_sql: ValidatedSql) -> _Authorizer:
    referenced_tables = {
        fold_sqlite_identifier(table) for table in validated_sql.referenced_tables
    }
    referenced_columns = {
        (fold_sqlite_identifier(table), fold_sqlite_identifier(column))
        for table, column in validated_sql.referenced_columns
    }

    def authorize(
        action: int,
        arg1: str | None,
        arg2: str | None,
        dbname: str | None,  # noqa: ARG001 - fixed sqlite3 authorizer signature
        source: str | None,  # noqa: ARG001 - fixed sqlite3 authorizer signature
    ) -> int:
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            return _authorize_read(arg1, arg2, referenced_tables, referenced_columns)
        if action == sqlite3.SQLITE_FUNCTION:
            name = arg2.upper() if arg2 else ""
            if name in ALLOWED_FUNCTION_NAMES:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        # Default-deny: writes, schema changes, PRAGMA, ATTACH/DETACH,
        # transactions/savepoints, and any action code not explicitly
        # authorized above, including ones not yet defined by SQLite.
        return sqlite3.SQLITE_DENY

    return authorize


def _authorize_read(
    table: str | None,
    column: str | None,
    referenced_tables: set[str],
    referenced_columns: set[tuple[str, str]],
) -> int:
    if not table or fold_sqlite_identifier(table) not in referenced_tables:
        return sqlite3.SQLITE_DENY
    if not column:
        # SQLite issues a READ with an empty column name for row-existence
        # checks such as COUNT(*); the table-level check above already
        # authorized this table.
        return sqlite3.SQLITE_OK
    identity = (fold_sqlite_identifier(table), fold_sqlite_identifier(column))
    if identity in referenced_columns:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY
