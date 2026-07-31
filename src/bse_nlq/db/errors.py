"""Public errors for the database layer."""

from __future__ import annotations


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
