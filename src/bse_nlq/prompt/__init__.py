"""Deterministic prompt construction from schema introspection and metadata.

Builds one provider-neutral prompt representation per question. Does not call
a model, open a database path, or execute SQL.
"""

from bse_nlq.prompt.builder import build_prompt
from bse_nlq.prompt.errors import PromptConstructionError
from bse_nlq.prompt.models import (
    APPLICATION_POLICY_VERSION,
    DEFAULT_AS_OF,
    BuiltPrompt,
    PromptInput,
)
from bse_nlq.prompt.schema_render import render_physical_schema
from bse_nlq.prompt.semantic_render import render_semantic_context

__all__ = [
    "APPLICATION_POLICY_VERSION",
    "DEFAULT_AS_OF",
    "BuiltPrompt",
    "PromptConstructionError",
    "PromptInput",
    "build_prompt",
    "render_physical_schema",
    "render_semantic_context",
]
