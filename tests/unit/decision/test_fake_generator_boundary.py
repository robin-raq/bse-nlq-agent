"""Offline fake-generator boundary between prompt construction and parsing."""

from __future__ import annotations

import pytest
from helpers import decision_json

from bse_nlq.decision import (
    DecisionStatus,
    InvalidModelOutputError,
    ModelDecision,
)
from bse_nlq.generator import decide_from_raw_generator
from bse_nlq.prompt import build_prompt


class FakeRawGenerator:
    """Test double that records prompts and returns a preset raw string."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[object] = []

    def complete(self, prompt: object) -> str:
        self.calls.append(prompt)
        return self.response


def test_exact_prompt_passed_once_and_parsed_once(prompt_input) -> None:
    prompt = build_prompt(prompt_input)
    fake = FakeRawGenerator(
        decision_json(status="sql_generated", sql="SELECT COUNT(*) FROM venues")
    )
    decision = decide_from_raw_generator(fake, prompt)
    assert len(fake.calls) == 1
    assert fake.calls[0] is prompt
    assert decision.status is DecisionStatus.SQL_GENERATED
    assert decision.sql == "SELECT COUNT(*) FROM venues"
    assert decision.is_executable is True


def test_malformed_output_maps_to_invalid_model_output(prompt_input) -> None:
    prompt = build_prompt(prompt_input)
    fake = FakeRawGenerator("{not-json")
    with pytest.raises(InvalidModelOutputError) as exc_info:
        decide_from_raw_generator(fake, prompt)
    assert exc_info.value.terminal_state == "invalid_model_output"
    assert len(fake.calls) == 1


def test_clarification_and_unsupported_remain_non_executable(prompt_input) -> None:
    prompt = build_prompt(prompt_input)
    clarification = decide_from_raw_generator(
        FakeRawGenerator(
            decision_json(
                status="clarification_required",
                clarification="Gross or net ticket revenue?",
            )
        ),
        prompt,
    )
    assert clarification.is_executable is False
    assert clarification.sql is None

    unsupported = decide_from_raw_generator(
        FakeRawGenerator(
            decision_json(
                status="unsupported",
                explanation="relative_time_of_day",
            )
        ),
        prompt,
    )
    assert unsupported.is_executable is False
    assert unsupported.sql is None


def test_answerable_sql_forwarded_without_execution(prompt_input) -> None:
    prompt = build_prompt(prompt_input)
    sql = "SELECT event_id FROM events WHERE status = 'completed'"
    decision = decide_from_raw_generator(
        FakeRawGenerator(decision_json(status="sql_generated", sql=sql)),
        prompt,
    )
    assert isinstance(decision, ModelDecision)
    assert decision.sql == sql
    # No query execution API is invoked in this phase; SQL is carried only.


def test_generator_not_called_twice_for_semantic_repair(prompt_input) -> None:
    prompt = build_prompt(prompt_input)

    class CountingGenerator(FakeRawGenerator):
        def complete(self, prompt: object) -> str:
            super().complete(prompt)
            if len(self.calls) > 1:
                raise AssertionError("generator called more than once")
            return self.response

    fake = CountingGenerator(decision_json(status="sql_generated", sql="SELECT 1"))
    decide_from_raw_generator(fake, prompt)
    assert len(fake.calls) == 1
