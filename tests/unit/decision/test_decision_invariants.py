"""Cross-field ModelDecision status invariants."""

from __future__ import annotations

import pytest
from helpers import decision_json

from bse_nlq.decision import (
    DecisionStatus,
    InvalidModelOutputError,
    InvalidModelOutputReason,
    parse_model_decision_json,
)


def test_sql_generated_requires_sql_forbids_clarification_and_explanation() -> None:
    decision = parse_model_decision_json(
        decision_json(status="sql_generated", sql="SELECT COUNT(*) FROM events")
    )
    assert decision.status is DecisionStatus.SQL_GENERATED
    assert decision.sql is not None
    assert decision.clarification is None
    assert decision.explanation is None
    assert decision.is_executable is True


@pytest.mark.parametrize(
    "payload",
    [
        decision_json(status="sql_generated"),
        decision_json(
            status="sql_generated",
            sql="SELECT 1",
            clarification="Which metric?",
        ),
        decision_json(
            status="sql_generated",
            sql="SELECT 1",
            explanation="The answer is 42",
        ),
    ],
)
def test_sql_generated_contradictions_rejected(payload: str) -> None:
    with pytest.raises(InvalidModelOutputError) as exc_info:
        parse_model_decision_json(payload)
    assert exc_info.value.reason is InvalidModelOutputReason.CONTRADICTORY_DECISION
    assert exc_info.value.terminal_state == "invalid_model_output"


def test_clarification_required_invariants() -> None:
    decision = parse_model_decision_json(
        decision_json(
            status="clarification_required",
            clarification="Gross or net ticket revenue?",
        )
    )
    assert decision.status is DecisionStatus.CLARIFICATION_REQUIRED
    assert decision.sql is None
    assert decision.explanation is None
    assert decision.is_executable is False


@pytest.mark.parametrize(
    "payload",
    [
        decision_json(status="clarification_required"),
        decision_json(
            status="clarification_required",
            clarification="Need metric",
            sql="SELECT 1",
        ),
        decision_json(
            status="clarification_required",
            clarification="Need metric",
            explanation="unsupported shape",
        ),
    ],
)
def test_clarification_contradictions_rejected(payload: str) -> None:
    with pytest.raises(InvalidModelOutputError) as exc_info:
        parse_model_decision_json(payload)
    assert exc_info.value.reason is InvalidModelOutputReason.CONTRADICTORY_DECISION


def test_unsupported_invariants() -> None:
    decision = parse_model_decision_json(
        decision_json(
            status="unsupported",
            explanation="relative_time_of_day",
        )
    )
    assert decision.status is DecisionStatus.UNSUPPORTED
    assert decision.sql is None
    assert decision.clarification is None
    assert decision.is_executable is False


@pytest.mark.parametrize(
    "payload",
    [
        decision_json(status="unsupported"),
        decision_json(
            status="unsupported",
            explanation="relative_time_of_day",
            sql="SELECT 1",
        ),
        decision_json(
            status="unsupported",
            explanation="relative_time_of_day",
            clarification="What time?",
        ),
    ],
)
def test_unsupported_contradictions_rejected(payload: str) -> None:
    with pytest.raises(InvalidModelOutputError) as exc_info:
        parse_model_decision_json(payload)
    assert exc_info.value.reason is InvalidModelOutputReason.CONTRADICTORY_DECISION


def test_forbidden_sql_on_non_answerable_is_not_executable() -> None:
    with pytest.raises(InvalidModelOutputError):
        parse_model_decision_json(
            decision_json(
                status="clarification_required",
                clarification="Gross or net?",
                sql="SELECT 1",
            )
        )
