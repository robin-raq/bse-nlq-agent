"""Public errors for the database layer."""

from __future__ import annotations

from enum import StrEnum


class DatabaseBuildError(Exception):
    """Raised when persistent database construction cannot complete.

    Destination preconditions, atomic publication failures, and artifact
    validation failures surface as this type. Unexpected underlying failures
    are attached as ``__cause__`` when wrapped.
    """


class DatabaseRuntimeError(Exception):
    """Raised when a read-only runtime database cannot be opened or used.

    Path preconditions, connection configuration failures, metadata readiness
    failures, close failures, and use-after-close surface as this type.
    Expected underlying failures are attached as ``__cause__`` when wrapped.
    Normalization is localized to the specific path, SQLite, or metadata
    operation that can legitimately raise it — never a broad type-based catch
    around unrelated code. Programming defects (for example ``AttributeError``,
    or a ``RuntimeError`` / ``TypeError`` / ``ValueError`` raised by a bug
    rather than an actual path, SQLite, or metadata failure) and
    ``KeyboardInterrupt`` / ``SystemExit`` are never converted to this type.
    This phase does not map the error onto application terminal states.
    """


class ExecutionErrorReason(StrEnum):
    """Closed reasons for controlled-execution failures.

    Not a terminal-state enum; the query service maps these later.
    """

    ROW_LIMIT_EXCEEDED = "row_limit_exceeded"
    COLUMN_LIMIT_EXCEEDED = "column_limit_exceeded"
    EXECUTION_BUDGET_EXCEEDED = "execution_budget_exceeded"
    AUTHORIZATION_DENIED = "authorization_denied"
    EXECUTION_FAILED = "execution_failed"


class SqlExecutionError(Exception):
    """Raised when validated SQL cannot be executed under the safety controls.

    Row/column overflow, opcode-budget exhaustion, authorizer denial, and
    other SQLite execution failures surface as this type with ``reason`` set
    and, for wrapped SQLite failures, the original exception preserved as
    ``__cause__``. Programming defects and ``KeyboardInterrupt`` /
    ``SystemExit`` are never converted to this type. This phase does not map
    the error onto application terminal states.
    """

    def __init__(self, message: str, *, reason: ExecutionErrorReason) -> None:
        super().__init__(message)
        self.reason = reason
