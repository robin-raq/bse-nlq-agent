"""Public errors for the database layer."""

from __future__ import annotations


class DatabaseBuildError(Exception):
    """Raised when persistent database construction cannot complete.

    Destination preconditions, atomic publication failures, and artifact
    validation failures surface as this type. Unexpected underlying failures
    are attached as ``__cause__`` when wrapped.
    """
