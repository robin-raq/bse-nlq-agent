"""Shared fixtures for ModelDecision and prompt construction tests."""

from __future__ import annotations

import sqlite3

# Ensure sibling helpers.py is importable as `helpers` from this directory.
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from bse_nlq.db.schema import apply_schema
from bse_nlq.db.seed import load_seed_data
from bse_nlq.metadata import load_semantic_metadata
from bse_nlq.metadata.models import SemanticMetadata
from bse_nlq.prompt import DEFAULT_AS_OF, PromptInput, build_prompt
from bse_nlq.prompt.models import BuiltPrompt

_DECISION_TEST_DIR = Path(__file__).resolve().parent
if str(_DECISION_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_DECISION_TEST_DIR))


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    try:
        apply_schema(conn)
        yield conn
    finally:
        conn.close()


@pytest.fixture
def seeded_connection(connection: sqlite3.Connection) -> sqlite3.Connection:
    load_seed_data(connection)
    return connection


@pytest.fixture
def metadata(seeded_connection: sqlite3.Connection) -> SemanticMetadata:
    return load_semantic_metadata(seeded_connection)


@pytest.fixture
def prompt_input(
    seeded_connection: sqlite3.Connection, metadata: SemanticMetadata
) -> PromptInput:
    return PromptInput(
        question="How many completed events are there?",
        metadata=metadata,
        connection=seeded_connection,
        as_of=None,
    )


@pytest.fixture
def built_prompt(prompt_input: PromptInput) -> BuiltPrompt:
    return build_prompt(prompt_input)


ASSERT_DEFAULT_AS_OF = DEFAULT_AS_OF
ASSERT_EXPLICIT_AS_OF = date(2026, 1, 1)
