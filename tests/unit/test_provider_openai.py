"""Offline tests for the production OpenAI adapter boundary."""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError

from bse_nlq.cli import render_cli_output
from bse_nlq.generator import ProviderUnavailableError
from bse_nlq.prompt.models import DEFAULT_AS_OF, BuiltPrompt
from bse_nlq.provider_openai import OpenAIRawGenerator
from bse_nlq.service import QueryResult, TerminalState

_FAKE_KEY = "sk-test-openai-secret-value"
_RAW_PAYLOAD = "raw-openai-provider-payload-must-not-leak"


class _FakeResponses:
    def __init__(self, *, error: Exception) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        raise self.error


def _prompt() -> BuiltPrompt:
    return BuiltPrompt(
        system_instructions="system",
        user_content="user",
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


def test_openai_provider_error_maps_without_sensitive_text() -> None:
    provider_error = APIConnectionError(
        message=f"{_RAW_PAYLOAD} {_FAKE_KEY}",
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )
    client = SimpleNamespace(responses=_FakeResponses(error=provider_error))
    generator = OpenAIRawGenerator(api_key=_FAKE_KEY)
    generator._client = client  # type: ignore[method-assign]

    with pytest.raises(ProviderUnavailableError) as caught:
        generator.complete(_prompt())

    message = str(caught.value)
    assert message == "OpenAI provider request failed"
    assert _FAKE_KEY not in message
    assert _RAW_PAYLOAD not in message
    assert len(client.responses.calls) == 1


def test_provider_unavailable_cli_output_hides_injected_provider_text() -> None:
    """Service/CLI must not surface provider exception text to the user."""
    result = QueryResult(terminal_state=TerminalState.PROVIDER_UNAVAILABLE)
    output = render_cli_output(result)

    assert _FAKE_KEY not in output
    assert _RAW_PAYLOAD not in output
    assert "provider is currently unavailable" in output
    assert "OpenAI provider request failed" not in output
