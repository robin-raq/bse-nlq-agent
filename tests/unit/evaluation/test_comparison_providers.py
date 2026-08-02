"""Offline tests for the comparison-only provider adapters."""

from __future__ import annotations

import json
from types import MappingProxyType, SimpleNamespace

import httpx
import pytest
from evaluation.model_comparison.providers import (
    GROQ_MODEL,
    GroqComparisonGenerator,
)
from openai import APIConnectionError

from bse_nlq.decision.errors import InvalidModelOutputError
from bse_nlq.generator import ProviderUnavailableError, decide_from_raw_generator
from bse_nlq.prompt.models import DEFAULT_AS_OF, BuiltPrompt

_FAKE_KEY = "test-groq-secret-value"
_RAW_PAYLOAD = "raw-provider-payload-must-not-leak"


class _FakeCompletions:
    def __init__(self, response: object | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _prompt() -> BuiltPrompt:
    return BuiltPrompt(
        system_instructions="same system instructions",
        user_content="same user content",
        response_schema=MappingProxyType(
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["status", "sql", "clarification", "explanation"],
                "properties": {},
            }
        ),
        as_of=DEFAULT_AS_OF,
    )


def _response(content: str) -> object:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=123, completion_tokens=45),
    )


def test_valid_groq_strict_response_and_exactly_one_generation() -> None:
    raw = json.dumps(
        {
            "status": "unsupported",
            "sql": None,
            "clarification": None,
            "explanation": "Not answerable from the database.",
        }
    )
    completions = _FakeCompletions(_response(raw))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    generator = GroqComparisonGenerator(api_key=_FAKE_KEY, client=client)

    decision = decide_from_raw_generator(generator, _prompt())

    assert decision.status.value == "unsupported"
    assert len(completions.calls) == 1
    request = completions.calls[0]
    assert request["model"] == GROQ_MODEL
    assert request["temperature"] == 0
    assert request["messages"] == [
        {"role": "system", "content": "same system instructions"},
        {"role": "user", "content": "same user content"},
    ]
    response_format = request["response_format"]
    assert isinstance(response_format, dict)
    assert response_format["json_schema"]["strict"] is True
    assert generator.last_observation is not None
    assert generator.last_observation.input_tokens == 123
    assert generator.last_observation.output_tokens == 45


def test_malformed_groq_response_maps_through_local_parser() -> None:
    completions = _FakeCompletions(_response("not valid JSON"))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    generator = GroqComparisonGenerator(api_key=_FAKE_KEY, client=client)

    with pytest.raises(InvalidModelOutputError):
        decide_from_raw_generator(generator, _prompt())

    assert len(completions.calls) == 1


def test_missing_groq_api_key_fails_before_client_use() -> None:
    with pytest.raises(ValueError, match="GROQ_API_KEY is required"):
        GroqComparisonGenerator(api_key="  ")


def test_groq_provider_error_maps_without_sensitive_text() -> None:
    provider_error = APIConnectionError(
        message=f"{_RAW_PAYLOAD} {_FAKE_KEY}",
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat"),
    )
    completions = _FakeCompletions(error=provider_error)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    generator = GroqComparisonGenerator(api_key=_FAKE_KEY, client=client)

    with pytest.raises(ProviderUnavailableError) as caught:
        generator.complete(_prompt())

    message = str(caught.value)
    assert _FAKE_KEY not in message
    assert _RAW_PAYLOAD not in message
    assert message == "Groq provider request failed"
    assert len(completions.calls) == 1
    assert generator.last_observation is not None
    assert generator.last_observation.error_class == "provider_transport"
    assert generator.last_observation.error_subtype == "connection_error"
