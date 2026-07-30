"""Provider-neutral generation boundary for offline tests and future adapters.

``QueryGenerator`` isolates nondeterministic provider code. This module defines
only the protocol and a one-shot parse helper. No OpenAI, Groq, HTTP, retries,
or provider selection lives here.
"""

from __future__ import annotations

from typing import Protocol

from bse_nlq.decision.models import ModelDecision
from bse_nlq.decision.validate import parse_model_decision_json
from bse_nlq.prompt.models import BuiltPrompt, PromptInput


class QueryGenerator(Protocol):
    """One semantic generation attempt: prompt input to ModelDecision."""

    def generate(self, request: PromptInput) -> ModelDecision:
        """Produce exactly one ModelDecision for the request."""


class RawModelGenerator(Protocol):
    """Returns one raw model-response string for a built prompt."""

    def complete(self, prompt: BuiltPrompt) -> str:
        """Return the raw provider payload string exactly once per call."""


def decide_from_raw_generator(
    generator: RawModelGenerator,
    prompt: BuiltPrompt,
) -> ModelDecision:
    """Call the generator once and parse the raw response once.

    The raw response string is passed to ``parse_model_decision_json`` so
    duplicate JSON keys are detected. Adapters must not ``json.loads`` first.

    Malformed or contradictory payloads raise InvalidModelOutputError, which
    maps to the frozen ``invalid_model_output`` terminal behavior.
    """
    raw = generator.complete(prompt)
    return parse_model_decision_json(raw)


__all__ = [
    "QueryGenerator",
    "RawModelGenerator",
    "decide_from_raw_generator",
]
