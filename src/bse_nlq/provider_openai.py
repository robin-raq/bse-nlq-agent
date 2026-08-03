"""OpenAI adapter: the one production ``RawModelGenerator`` implementation.

GPT-5 mini through the OpenAI Responses API, requesting the ModelDecision
JSON Schema as strict structured output. No fallback provider, no second
semantic attempt, no SQL repair. The OpenAI SDK's own bounded internal
transport retries are the only retry behavior; every ``openai.APIError``
(connection failure, timeout, rate limiting, service error, or
authentication/authorization failure) is translated to
``ProviderUnavailableError`` after those retries are exhausted.
"""

from __future__ import annotations

from openai import APIError, OpenAI

from bse_nlq.decision import model_decision_json_schema
from bse_nlq.generator import ProviderUnavailableError
from bse_nlq.prompt.models import BuiltPrompt

DEFAULT_MODEL = "gpt-5-mini"


class OpenAIRawGenerator:
    """``RawModelGenerator`` backed by the OpenAI Responses API."""

    def __init__(self, *, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete(self, prompt: BuiltPrompt) -> str:
        """Return the raw response text exactly once per call.

        Raises ``ProviderUnavailableError`` for any transport/auth/rate-limit
        failure the SDK surfaces. Never raises for a malformed or
        contradictory response body — that is ``parse_model_decision_json``'s
        concern, applied by the caller.
        """
        schema = dict(model_decision_json_schema())
        try:
            response = self._client.responses.create(
                model=self._model,
                instructions=prompt.system_instructions,
                input=prompt.user_content,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "ModelDecision",
                        "schema": schema,
                        "strict": True,
                    }
                },
            )
        except APIError as error:
            raise ProviderUnavailableError("OpenAI provider request failed") from error
        return response.output_text


__all__ = ["DEFAULT_MODEL", "OpenAIRawGenerator"]
