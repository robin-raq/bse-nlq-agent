"""Errors raised while constructing a prompt."""


class PromptConstructionError(Exception):
    """Prompt inputs are invalid or metadata is not reconciled to the schema."""
