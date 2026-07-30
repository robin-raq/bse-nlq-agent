"""Duplicate JSON object key rejection for ModelDecision."""

from __future__ import annotations

import pytest

from bse_nlq.decision import (
    InvalidModelOutputError,
    InvalidModelOutputReason,
    parse_model_decision_json,
)


def test_duplicate_top_level_key_rejected_even_when_values_identical() -> None:
    raw = (
        '{"status":"sql_generated","status":"sql_generated",'
        '"sql":"SELECT 1","clarification":null,"explanation":null}'
    )
    with pytest.raises(InvalidModelOutputError) as exc_info:
        parse_model_decision_json(raw)
    assert exc_info.value.reason is InvalidModelOutputReason.DUPLICATE_KEY
    assert exc_info.value.terminal_state == "invalid_model_output"


def test_duplicate_top_level_key_with_conflicting_values_rejected() -> None:
    raw = (
        '{"status":"sql_generated","sql":"SELECT 1","sql":"SELECT 2",'
        '"clarification":null,"explanation":null}'
    )
    with pytest.raises(InvalidModelOutputError) as exc_info:
        parse_model_decision_json(raw)
    assert exc_info.value.reason is InvalidModelOutputReason.DUPLICATE_KEY


def test_duplicate_key_inside_nested_object_rejected() -> None:
    # ModelDecision itself is flat; the parser must still reject nested
    # duplicate keys if a malformed payload introduces a nested object.
    raw = (
        '{"status":"sql_generated","sql":"SELECT 1","clarification":null,'
        '"explanation":{"reason":"x","reason":"x"}}'
    )
    with pytest.raises(InvalidModelOutputError) as exc_info:
        parse_model_decision_json(raw)
    assert exc_info.value.reason is InvalidModelOutputReason.DUPLICATE_KEY


def test_ordinary_json_loads_would_collapse_duplicates() -> None:
    """Document why object_pairs_hook is required."""
    import json

    collapsed = json.loads('{"sql":"SELECT 1","sql":"SELECT 2"}')
    assert collapsed == {"sql": "SELECT 2"}
