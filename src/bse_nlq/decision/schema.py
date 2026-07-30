"""Deterministic JSON Schema for ModelDecision structured-output configuration.

Shape constraints are shared with the runtime validator. Cross-field status
invariants remain application-owned; JSON Schema alone does not enforce them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from bse_nlq.decision.models import ALLOWED_DECISION_KEYS, DECISION_STATUSES

# Stable field order matching the frozen architecture table.
_FIELD_ORDER: tuple[str, ...] = ("status", "sql", "clarification", "explanation")


def model_decision_json_schema() -> Mapping[str, Any]:
    """Return an immutable JSON Schema object for ModelDecision.

    Provider-neutral: no OpenAI- or Groq-specific wrappers. Every object
    boundary sets ``additionalProperties`` to false. Required keys and enum
    values match the runtime contract exactly.
    """
    status_enum = sorted(DECISION_STATUSES)
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ModelDecision",
        "type": "object",
        "additionalProperties": False,
        "required": list(_FIELD_ORDER),
        "properties": {
            "status": {
                "type": "string",
                "enum": status_enum,
            },
            "sql": {
                "type": ["string", "null"],
            },
            "clarification": {
                "type": ["string", "null"],
            },
            "explanation": {
                "type": ["string", "null"],
            },
        },
    }
    # Sanity: schema inventory cannot drift from ALLOWED_DECISION_KEYS.
    assert frozenset(schema["required"]) == ALLOWED_DECISION_KEYS
    assert frozenset(schema["properties"]) == ALLOWED_DECISION_KEYS
    return MappingProxyType(schema)


def model_decision_json_schema_text() -> str:
    """Serialize the schema with stable key ordering and LF newlines."""
    return (
        json.dumps(
            dict(model_decision_json_schema()),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )
