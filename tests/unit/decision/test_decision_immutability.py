"""Immutability and source-isolation for ModelDecision."""

from __future__ import annotations

import pytest

from bse_nlq.decision import DecisionStatus, validate_model_decision


def test_returned_decision_fields_are_immutable() -> None:
    decision = validate_model_decision(
        {
            "status": "sql_generated",
            "sql": "SELECT 1",
            "clarification": None,
            "explanation": None,
        }
    )
    with pytest.raises(AttributeError):
        decision.status = DecisionStatus.UNSUPPORTED  # type: ignore[misc]
    with pytest.raises(AttributeError):
        decision.sql = "SELECT 2"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        decision.clarification = "nope"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        decision.explanation = "nope"  # type: ignore[misc]


def test_mutating_source_mapping_after_validation_does_not_alter_decision() -> None:
    source = {
        "status": "sql_generated",
        "sql": "SELECT 1",
        "clarification": None,
        "explanation": None,
    }
    decision = validate_model_decision(source)
    source["status"] = "unsupported"
    source["sql"] = None
    source["explanation"] = "changed"
    assert decision.status is DecisionStatus.SQL_GENERATED
    assert decision.sql == "SELECT 1"
    assert decision.explanation is None


def test_mutating_source_string_objects_cannot_rewrite_decision_sql() -> None:
    # str is immutable; ensure we did not keep a mutable buffer alias.
    sql = "SELECT quantity FROM order_items"
    decision = validate_model_decision(
        {
            "status": "sql_generated",
            "sql": sql,
            "clarification": None,
            "explanation": None,
        }
    )
    assert decision.sql == "SELECT quantity FROM order_items"
    assert decision.sql is not None
