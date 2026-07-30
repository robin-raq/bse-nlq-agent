"""JSON Schema inventory stays aligned with the runtime validator."""

from __future__ import annotations

from types import MappingProxyType

from bse_nlq.decision import (
    ALLOWED_DECISION_KEYS,
    DECISION_STATUSES,
    model_decision_json_schema,
    model_decision_json_schema_text,
)


def test_schema_required_keys_match_runtime_allowlist() -> None:
    schema = model_decision_json_schema()
    assert frozenset(schema["required"]) == ALLOWED_DECISION_KEYS
    assert frozenset(schema["properties"]) == ALLOWED_DECISION_KEYS


def test_schema_enum_matches_decision_statuses() -> None:
    schema = model_decision_json_schema()
    assert frozenset(schema["properties"]["status"]["enum"]) == DECISION_STATUSES


def test_schema_rejects_additional_properties_at_object_boundary() -> None:
    schema = model_decision_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["type"] == "object"


def test_schema_is_immutable_mapping() -> None:
    schema = model_decision_json_schema()
    assert isinstance(schema, MappingProxyType)
    try:
        schema["title"] = "mutated"  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("schema mapping must reject mutation")


def test_schema_text_is_stable_and_sorted() -> None:
    first = model_decision_json_schema_text()
    second = model_decision_json_schema_text()
    assert first == second
    assert first.endswith("\n")
    assert '"clarification"' in first
    assert "openai" not in first.lower()
    assert "groq" not in first.lower()
