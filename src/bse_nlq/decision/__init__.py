"""Strict ModelDecision contract: parse, validate, and JSON Schema.

Provider responses map to four required fields. Local validation owns
status-specific null/non-null invariants. Malformed or contradictory output
maps to the public ``invalid_model_output`` terminal behavior.
"""

from bse_nlq.decision.errors import (
    InvalidModelOutputError,
    InvalidModelOutputReason,
)
from bse_nlq.decision.models import (
    ALLOWED_DECISION_KEYS,
    DECISION_STATUSES,
    DecisionStatus,
    ModelDecision,
)
from bse_nlq.decision.schema import (
    model_decision_json_schema,
    model_decision_json_schema_text,
)
from bse_nlq.decision.validate import (
    parse_model_decision_json,
    validate_model_decision,
)

__all__ = [
    "ALLOWED_DECISION_KEYS",
    "DECISION_STATUSES",
    "DecisionStatus",
    "InvalidModelOutputError",
    "InvalidModelOutputReason",
    "ModelDecision",
    "model_decision_json_schema",
    "model_decision_json_schema_text",
    "parse_model_decision_json",
    "validate_model_decision",
]
