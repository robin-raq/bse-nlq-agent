"""Typed prompt-input and built-prompt boundaries."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any

from bse_nlq.metadata.models import SemanticMetadata

# Frozen default as_of from docs/planning/decisions.md and schema-design.md.
DEFAULT_AS_OF: date = date(2026, 3, 15)

# Bumped only when application prompt policy text changes intentionally.
APPLICATION_POLICY_VERSION: int = 2


@dataclass(frozen=True, slots=True)
class PromptInput:
    """Frozen inputs required for one deterministic prompt generation.

    The caller supplies a SQLite connection already carrying the application
    schema (and typically the seed). This object never opens a database path.
    """

    question: str
    metadata: SemanticMetadata
    connection: sqlite3.Connection
    as_of: date | None = None

    def resolved_as_of(self) -> date:
        """Return the explicit as_of, or the frozen default when omitted."""
        return DEFAULT_AS_OF if self.as_of is None else self.as_of


@dataclass(frozen=True, slots=True)
class BuiltPrompt:
    """Provider-neutral prompt: system instructions, user content, schema."""

    system_instructions: str
    user_content: str
    response_schema: MappingProxyType[str, Any]
    as_of: date
    policy_version: int = APPLICATION_POLICY_VERSION

    def canonical_text(self) -> str:
        """Byte-stable rendering used for determinism checks and diagnostics."""
        schema_json = _stable_json(dict(self.response_schema))
        parts = (
            f"policy_version={self.policy_version}",
            f"as_of={self.as_of.isoformat()}",
            "===SYSTEM===",
            self.system_instructions,
            "===USER===",
            self.user_content,
            "===RESPONSE_SCHEMA===",
            schema_json,
        )
        text = "\n".join(parts)
        # Normalize only structural trailing whitespace at end-of-string.
        return text.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"

    def canonical_bytes(self) -> bytes:
        return self.canonical_text().encode("utf-8")


def _stable_json(value: Any) -> str:
    import json

    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
