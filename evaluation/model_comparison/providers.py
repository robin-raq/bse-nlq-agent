"""Comparison-only provider adapters with sanitized observations.

These adapters implement the application's existing ``RawModelGenerator``
protocol. They deliberately do not participate in product provider selection.
Both make one SDK request, disable SDK retries, and retain only latency and
token counts from the response.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from openai import APIError, APITimeoutError, OpenAI

from bse_nlq.generator import ProviderUnavailableError
from bse_nlq.prompt.models import BuiltPrompt

OPENAI_MODEL = "gpt-5-mini"
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
REQUEST_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    """Safe metadata from the most recent provider request."""

    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    error_class: str | None = None
    error_subtype: str | None = None


class OpenAIComparisonGenerator:
    """GPT-5 mini through OpenAI Responses, configured for this experiment."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = OPENAI_MODEL,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required")
        self._client = client or OpenAI(
            api_key=api_key,
            max_retries=0,
            timeout=timeout,
        )
        self._model = model
        self.last_observation: ProviderObservation | None = None

    def complete(self, prompt: BuiltPrompt) -> str:
        """Return one strict ModelDecision JSON response."""
        self.last_observation = None
        started = time.perf_counter()
        try:
            response = self._client.responses.create(
                model=self._model,
                instructions=prompt.system_instructions,
                input=prompt.user_content,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "ModelDecision",
                        "schema": dict(prompt.response_schema),
                        "strict": True,
                    }
                },
            )
        except APITimeoutError as error:
            self._record_failure(started, "timeout")
            raise ProviderUnavailableError(
                "OpenAI provider request timed out"
            ) from error
        except APIError as error:
            self._record_failure(
                started,
                "provider_transport",
                error_subtype=_safe_api_error_subtype(error),
            )
            raise ProviderUnavailableError("OpenAI provider request failed") from error

        usage = getattr(response, "usage", None)
        self.last_observation = ProviderObservation(
            latency_ms=_elapsed_ms(started),
            input_tokens=_optional_int(getattr(usage, "input_tokens", None)),
            output_tokens=_optional_int(getattr(usage, "output_tokens", None)),
        )
        return str(response.output_text)

    def _record_failure(
        self,
        started: float,
        error_class: str,
        *,
        error_subtype: str | None = None,
    ) -> None:
        self.last_observation = ProviderObservation(
            latency_ms=_elapsed_ms(started),
            input_tokens=None,
            output_tokens=None,
            error_class=error_class,
            error_subtype=error_subtype,
        )


class GroqComparisonGenerator:
    """GPT-OSS 120B through Groq Chat Completions strict output mode."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = GROQ_MODEL,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("GROQ_API_KEY is required")
        self._client = client or OpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            max_retries=0,
            timeout=timeout,
        )
        self._model = model
        self.last_observation: ProviderObservation | None = None

    def complete(self, prompt: BuiltPrompt) -> str:
        """Return one strict ModelDecision JSON response."""
        self.last_observation = None
        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": prompt.system_instructions},
                    {"role": "user", "content": prompt.user_content},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "ModelDecision",
                        "strict": True,
                        "schema": dict(prompt.response_schema),
                    },
                },
                temperature=0,
            )
        except APITimeoutError as error:
            self._record_failure(started, "timeout")
            raise ProviderUnavailableError("Groq provider request timed out") from error
        except APIError as error:
            self._record_failure(
                started,
                "provider_transport",
                error_subtype=_safe_api_error_subtype(error),
            )
            raise ProviderUnavailableError("Groq provider request failed") from error

        usage = getattr(response, "usage", None)
        self.last_observation = ProviderObservation(
            latency_ms=_elapsed_ms(started),
            input_tokens=_optional_int(getattr(usage, "prompt_tokens", None)),
            output_tokens=_optional_int(getattr(usage, "completion_tokens", None)),
        )
        choices = getattr(response, "choices", ())
        if not choices:
            return ""
        content = choices[0].message.content
        return "" if content is None else str(content)

    def _record_failure(
        self,
        started: float,
        error_class: str,
        *,
        error_subtype: str | None = None,
    ) -> None:
        self.last_observation = ProviderObservation(
            latency_ms=_elapsed_ms(started),
            input_tokens=None,
            output_tokens=None,
            error_class=error_class,
            error_subtype=error_subtype,
        )


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _safe_api_error_subtype(error: APIError) -> str:
    """Return a fixed diagnostic label without provider text or payloads."""
    status_code = getattr(error, "status_code", None)
    if status_code == 400:
        return "http_400_request_rejected"
    if status_code in {401, 403}:
        return "http_authentication_or_permission"
    if status_code == 429:
        return "http_429_rate_limit"
    if isinstance(status_code, int) and 500 <= status_code <= 599:
        return "http_5xx_provider_service"
    if isinstance(status_code, int):
        return "http_other_status"
    return "connection_error"


__all__ = [
    "GROQ_BASE_URL",
    "GROQ_MODEL",
    "OPENAI_MODEL",
    "REQUEST_TIMEOUT_SECONDS",
    "GroqComparisonGenerator",
    "OpenAIComparisonGenerator",
    "ProviderObservation",
]
