"""Parse and validate ModelDecision envelopes fail-closed."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

from bse_nlq.decision.errors import (
    InvalidModelOutputError,
    InvalidModelOutputReason,
)
from bse_nlq.decision.models import (
    ALLOWED_DECISION_KEYS,
    DecisionStatus,
    ModelDecision,
)


def parse_model_decision_json(text: str) -> ModelDecision:
    """Parse a raw JSON string into a validated immutable ModelDecision.

    Duplicate object keys at any nesting level are rejected before ordinary
    ``dict`` construction can silently keep only the last value.

    Provider adapters must pass the raw model-response text to this function.
    Do not call ``json.loads`` and then ``validate_model_decision`` for raw
    provider payloads: ordinary ``json.loads`` collapses duplicate keys before
    validation can detect them.
    """
    if not isinstance(text, str):
        raise InvalidModelOutputError(
            "model decision payload must be a JSON string",
            reason=InvalidModelOutputReason.INVALID_SCHEMA,
        )
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
    except InvalidModelOutputError:
        raise
    except json.JSONDecodeError as exc:
        raise InvalidModelOutputError(
            f"malformed JSON: {exc.msg}",
            reason=InvalidModelOutputReason.MALFORMED_JSON,
        ) from None
    return validate_model_decision(payload)


def validate_model_decision(payload: object) -> ModelDecision:
    """Validate a decoded Python object as a ModelDecision.

    Accepts only a mapping with the four required fields. Non-finite floats and
    other non-JSON scalar shapes fail closed.

    Runtime code must obtain ``ModelDecision`` instances through this validator
    (or ``parse_model_decision_json``) rather than constructing the dataclass
    directly. Direct construction does not enforce status invariants.
    """
    if not isinstance(payload, Mapping):
        raise InvalidModelOutputError(
            "model decision must be a JSON object",
            reason=InvalidModelOutputReason.INVALID_SCHEMA,
        )

    # Copy before reading so later mutation of the caller's mapping cannot
    # affect validation mid-flight or the returned decision.
    raw = dict(payload)

    unknown = set(raw) - ALLOWED_DECISION_KEYS
    if unknown:
        raise InvalidModelOutputError(
            "unknown keys: " + ", ".join(sorted(map(str, unknown))),
            reason=InvalidModelOutputReason.INVALID_SCHEMA,
        )

    missing = ALLOWED_DECISION_KEYS - set(raw)
    if missing:
        raise InvalidModelOutputError(
            "missing required keys: " + ", ".join(sorted(missing)),
            reason=InvalidModelOutputReason.INVALID_SCHEMA,
        )

    status = _parse_status(raw["status"])
    sql = _parse_nullable_string(raw["sql"], "sql")
    clarification = _parse_nullable_string(raw["clarification"], "clarification")
    explanation = _parse_nullable_string(raw["explanation"], "explanation")

    _enforce_status_invariants(
        status=status,
        sql=sql,
        clarification=clarification,
        explanation=explanation,
    )

    return ModelDecision(
        status=status,
        sql=sql,
        clarification=clarification,
        explanation=explanation,
    )


def _parse_status(value: object) -> DecisionStatus:
    if not isinstance(value, str) or not value.strip():
        raise InvalidModelOutputError(
            "status must be a non-empty string decision kind",
            reason=InvalidModelOutputReason.INVALID_SCHEMA,
        )
    try:
        return DecisionStatus(value)
    except ValueError:
        raise InvalidModelOutputError(
            f"unknown decision kind: {value!r}",
            reason=InvalidModelOutputReason.UNKNOWN_DECISION_KIND,
        ) from None


def _parse_nullable_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidModelOutputError(
            f"{field} must be a string or null",
            reason=InvalidModelOutputReason.INVALID_SCHEMA,
        )
    if isinstance(value, bool) or not isinstance(value, str):
        raise InvalidModelOutputError(
            f"{field} must be a string or null",
            reason=InvalidModelOutputReason.INVALID_SCHEMA,
        )
    if not value.strip():
        raise InvalidModelOutputError(
            f"{field} must be null or a non-empty string",
            reason=InvalidModelOutputReason.INVALID_SCHEMA,
        )
    return value


def _enforce_status_invariants(
    *,
    status: DecisionStatus,
    sql: str | None,
    clarification: str | None,
    explanation: str | None,
) -> None:
    """Enforce the frozen null/non-null matrix for each decision kind."""
    if status is DecisionStatus.SQL_GENERATED:
        if sql is None:
            raise InvalidModelOutputError(
                "sql_generated requires nonempty sql",
                reason=InvalidModelOutputReason.CONTRADICTORY_DECISION,
            )
        if clarification is not None:
            raise InvalidModelOutputError(
                "sql_generated must not include clarification",
                reason=InvalidModelOutputReason.CONTRADICTORY_DECISION,
            )
        if explanation is not None:
            raise InvalidModelOutputError(
                "sql_generated must not include explanation",
                reason=InvalidModelOutputReason.CONTRADICTORY_DECISION,
            )
        return

    if status is DecisionStatus.CLARIFICATION_REQUIRED:
        if clarification is None:
            raise InvalidModelOutputError(
                "clarification_required requires nonempty clarification",
                reason=InvalidModelOutputReason.CONTRADICTORY_DECISION,
            )
        if sql is not None:
            raise InvalidModelOutputError(
                "clarification_required must not include sql",
                reason=InvalidModelOutputReason.CONTRADICTORY_DECISION,
            )
        if explanation is not None:
            raise InvalidModelOutputError(
                "clarification_required must not include explanation",
                reason=InvalidModelOutputReason.CONTRADICTORY_DECISION,
            )
        return

    # DecisionStatus.UNSUPPORTED
    if explanation is None:
        raise InvalidModelOutputError(
            "unsupported requires nonempty explanation",
            reason=InvalidModelOutputReason.CONTRADICTORY_DECISION,
        )
    if sql is not None:
        raise InvalidModelOutputError(
            "unsupported must not include sql",
            reason=InvalidModelOutputReason.CONTRADICTORY_DECISION,
        )
    if clarification is not None:
        raise InvalidModelOutputError(
            "unsupported must not include clarification",
            reason=InvalidModelOutputReason.CONTRADICTORY_DECISION,
        )


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise InvalidModelOutputError(
                f"duplicate JSON object key: {key!r}",
                reason=InvalidModelOutputReason.DUPLICATE_KEY,
            )
        seen.add(key)
        result[key] = value
    return result
