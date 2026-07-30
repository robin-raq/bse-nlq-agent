"""Immutable typed ModelDecision envelope."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DecisionStatus(StrEnum):
    """Frozen model decision kinds (ARCHITECTURE.md Model contract)."""

    SQL_GENERATED = "sql_generated"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"


DECISION_STATUSES: frozenset[str] = frozenset(status.value for status in DecisionStatus)

ALLOWED_DECISION_KEYS: frozenset[str] = frozenset(
    {"status", "sql", "clarification", "explanation"}
)


@dataclass(frozen=True, slots=True)
class ModelDecision:
    """Validated, immutable model decision.

    All four fields are always present. Status-specific null/non-null
    combinations are enforced by the validator, not by optional attributes.
    """

    status: DecisionStatus
    sql: str | None
    clarification: str | None
    explanation: str | None

    @property
    def is_executable(self) -> bool:
        """True only when the decision carries SQL for later validation."""
        return self.status is DecisionStatus.SQL_GENERATED
