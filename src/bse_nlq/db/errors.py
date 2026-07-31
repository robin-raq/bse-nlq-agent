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
    failures, and use-after-close surface as this type. Unexpected underlying
    failures are attached as ``__cause__`` when wrapped. This phase does not
    map the error onto application terminal states.
    """
