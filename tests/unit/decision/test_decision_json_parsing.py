"""Raw JSON parsing failures for ModelDecision."""

from __future__ import annotations

import json
import math

import pytest
from helpers import decision_json

from bse_nlq.decision import (
    DecisionStatus,
    InvalidModelOutputError,
    InvalidModelOutputReason,
    ModelDecision,
    parse_model_decision_json,
    validate_model_decision,
)


def test_valid_sql_generated_parses() -> None:
    decision = parse_model_decision_json(
        decision_json(status="sql_generated", sql="SELECT 1")
    )
    assert decision == ModelDecision(
        status=DecisionStatus.SQL_GENERATED,
        sql="SELECT 1",
        clarification=None,
        explanation=None,
    )


def test_malformed_json_maps_to_invalid_model_output() -> None:
    with pytest.raises(InvalidModelOutputError) as exc_info:
        parse_model_decision_json("{not json")
    assert exc_info.value.terminal_state == "invalid_model_output"
    assert exc_info.value.reason is InvalidModelOutputReason.MALFORMED_JSON
    assert not isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_non_object_top_level_rejected() -> None:
    with pytest.raises(InvalidModelOutputError) as exc_info:
        parse_model_decision_json('["sql_generated"]')
    assert exc_info.value.reason is InvalidModelOutputReason.INVALID_SCHEMA


def test_unknown_keys_rejected() -> None:
    with pytest.raises(InvalidModelOutputError) as unknown:
        parse_model_decision_json(
            '{"status":"sql_generated","sql":"SELECT 1",'
            '"clarification":null,"explanation":null,"extra":true}'
        )
    assert unknown.value.reason is InvalidModelOutputReason.INVALID_SCHEMA


def test_missing_keys_rejected() -> None:
    with pytest.raises(InvalidModelOutputError) as missing:
        parse_model_decision_json(
            '{"status":"sql_generated","sql":"SELECT 1","clarification":null}'
        )
    assert missing.value.reason is InvalidModelOutputReason.INVALID_SCHEMA


def test_wrong_primitive_types_rejected() -> None:
    with pytest.raises(InvalidModelOutputError):
        parse_model_decision_json(
            json.dumps(
                {
                    "status": "sql_generated",
                    "sql": 1,
                    "clarification": None,
                    "explanation": None,
                }
            )
        )
    with pytest.raises(InvalidModelOutputError):
        parse_model_decision_json(
            json.dumps(
                {
                    "status": ["sql_generated"],
                    "sql": "SELECT 1",
                    "clarification": None,
                    "explanation": None,
                }
            )
        )


def test_invalid_decision_kind_rejected() -> None:
    with pytest.raises(InvalidModelOutputError) as exc_info:
        parse_model_decision_json(decision_json(status="maybe", sql="SELECT 1"))
    assert exc_info.value.reason is InvalidModelOutputReason.UNKNOWN_DECISION_KIND


def test_empty_and_whitespace_strings_rejected() -> None:
    with pytest.raises(InvalidModelOutputError):
        parse_model_decision_json(decision_json(status="sql_generated", sql="   "))
    with pytest.raises(InvalidModelOutputError):
        parse_model_decision_json(
            decision_json(
                status="clarification_required",
                clarification="",
            )
        )


def test_nested_structure_where_scalar_required_rejected() -> None:
    with pytest.raises(InvalidModelOutputError):
        validate_model_decision(
            {
                "status": "sql_generated",
                "sql": {"query": "SELECT 1"},
                "clarification": None,
                "explanation": None,
            }
        )


def test_non_finite_float_rejected_on_object_entrypoint() -> None:
    with pytest.raises(InvalidModelOutputError):
        validate_model_decision(
            {
                "status": "sql_generated",
                "sql": math.nan,
                "clarification": None,
                "explanation": None,
            }
        )
    with pytest.raises(InvalidModelOutputError):
        validate_model_decision(
            {
                "status": "sql_generated",
                "sql": math.inf,
                "clarification": None,
                "explanation": None,
            }
        )


def test_public_error_hides_keyerror_and_typeerror() -> None:
    with pytest.raises(InvalidModelOutputError) as exc_info:
        validate_model_decision({"status": "sql_generated"})
    assert not isinstance(exc_info.value, KeyError)
    assert not isinstance(exc_info.value, TypeError)
    assert exc_info.value.terminal_state == "invalid_model_output"
