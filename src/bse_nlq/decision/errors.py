"""Errors for invalid ModelDecision envelopes.

All public failures map to the frozen terminal state ``invalid_model_output``.
Internal reason codes distinguish causes without inventing new terminal states.
"""

from __future__ import annotations

from enum import StrEnum

TERMINAL_INVALID_MODEL_OUTPUT = "invalid_model_output"


class InvalidModelOutputReason(StrEnum):
    """Stable internal failure categories for invalid model envelopes."""

    MALFORMED_JSON = "malformed_json"
    DUPLICATE_KEY = "duplicate_key"
    INVALID_SCHEMA = "invalid_schema"
    UNKNOWN_DECISION_KIND = "unknown_decision_kind"
    CONTRADICTORY_DECISION = "contradictory_decision"


class InvalidModelOutputError(Exception):
    """Raised when model output cannot become a valid ModelDecision.

    Callers map this exception to the ``invalid_model_output`` terminal state.
    Implementation-level exceptions (JSONDecodeError, KeyError, TypeError) are
    never the public contract.
    """

    terminal_state: str = TERMINAL_INVALID_MODEL_OUTPUT

    def __init__(
        self,
        message: str,
        *,
        reason: InvalidModelOutputReason,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
