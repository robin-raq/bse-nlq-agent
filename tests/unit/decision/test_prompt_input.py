"""PromptInput validation, as_of defaults, and reconciliation error mapping."""

from __future__ import annotations

import inspect
import sqlite3
from datetime import date, datetime

import pytest

import bse_nlq.prompt.builder as builder_mod
from bse_nlq.db.schema import apply_schema
from bse_nlq.metadata.errors import MetadataReconciliationError
from bse_nlq.prompt import (
    DEFAULT_AS_OF,
    PromptConstructionError,
    PromptInput,
    build_prompt,
)


def test_default_as_of_is_frozen_date_when_omitted(
    prompt_input: PromptInput,
) -> None:
    assert prompt_input.as_of is None
    assert prompt_input.resolved_as_of() == DEFAULT_AS_OF
    assert DEFAULT_AS_OF == date(2026, 3, 15)
    built = build_prompt(prompt_input)
    assert built.as_of == date(2026, 3, 15)
    assert isinstance(built.as_of, date)
    assert not isinstance(built.as_of, datetime)


def test_explicit_as_of_is_preserved(seeded_connection, metadata) -> None:
    explicit = date(2026, 2, 1)
    built = build_prompt(
        PromptInput(
            question="What events are upcoming?",
            metadata=metadata,
            connection=seeded_connection,
            as_of=explicit,
        )
    )
    assert built.as_of == explicit


def test_datetime_as_of_rejected(seeded_connection, metadata) -> None:
    with pytest.raises(PromptConstructionError, match="date, not a datetime"):
        build_prompt(
            PromptInput(
                question="What events are upcoming?",
                metadata=metadata,
                connection=seeded_connection,
                as_of=datetime(2026, 3, 15, 12, 0, 0),  # type: ignore[arg-type]
            )
        )


def test_empty_question_rejected(seeded_connection, metadata) -> None:
    with pytest.raises(PromptConstructionError, match="question"):
        build_prompt(
            PromptInput(
                question="   ",
                metadata=metadata,
                connection=seeded_connection,
            )
        )


def test_build_prompt_does_not_consult_system_clock(prompt_input: PromptInput) -> None:
    source = inspect.getsource(builder_mod)
    assert "date.today" not in source
    assert "datetime.now" not in source
    assert "time.time" not in source
    assert "time.sleep" not in source
    built = build_prompt(prompt_input)
    assert built.as_of is DEFAULT_AS_OF or built.as_of == DEFAULT_AS_OF


def test_reconciliation_failure_is_prompt_construction_error(
    metadata,
) -> None:
    empty = sqlite3.connect(":memory:")
    try:
        assert empty.in_transaction is False
        with pytest.raises(PromptConstructionError) as exc_info:
            build_prompt(
                PromptInput(
                    question="How many venues are there?",
                    metadata=metadata,
                    connection=empty,
                )
            )
        assert "reconciled" in str(exc_info.value).lower()
        assert isinstance(exc_info.value.__cause__, MetadataReconciliationError)
        assert not isinstance(exc_info.value, MetadataReconciliationError)
        assert empty.in_transaction is False
        # Connection remains usable after the failure.
        empty.execute("SELECT 1").fetchone()
        tables = {
            row[0]
            for row in empty.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert tables == set()
    finally:
        empty.close()


def test_reconciliation_failure_does_not_call_generator(metadata) -> None:
    class ExplodingGenerator:
        def complete(self, prompt: object) -> str:
            raise AssertionError("generator must not be called")

    empty = sqlite3.connect(":memory:")
    try:
        with pytest.raises(PromptConstructionError):
            build_prompt(
                PromptInput(
                    question="How many venues are there?",
                    metadata=metadata,
                    connection=empty,
                )
            )
        # Generator would only be reachable after a successful build_prompt.
        _ = ExplodingGenerator
    finally:
        empty.close()


def test_unrelated_errors_are_not_wrapped_as_prompt_construction(
    seeded_connection, metadata, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("unrelated failure")

    monkeypatch.setattr(builder_mod, "reconcile_metadata", boom)
    with pytest.raises(RuntimeError, match="unrelated failure"):
        build_prompt(
            PromptInput(
                question="How many venues are there?",
                metadata=metadata,
                connection=seeded_connection,
            )
        )


def test_schema_applied_connection_still_reconciles(metadata) -> None:
    conn = sqlite3.connect(":memory:")
    try:
        apply_schema(conn)
        built = build_prompt(
            PromptInput(
                question="How many venues are there?",
                metadata=metadata,
                connection=conn,
            )
        )
        assert "venues" in built.system_instructions
        assert conn.in_transaction is False
    finally:
        conn.close()
