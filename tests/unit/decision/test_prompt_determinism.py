"""Prompt determinism across equivalent inputs."""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import date

from bse_nlq.db.schema import apply_schema
from bse_nlq.db.seed import load_seed_data
from bse_nlq.metadata import load_semantic_metadata
from bse_nlq.prompt import PromptInput, build_prompt


def _fresh_prompt(question: str = "How many venues are there?") -> bytes:
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    load_seed_data(conn)
    metadata = load_semantic_metadata(conn)
    built = build_prompt(
        PromptInput(
            question=question,
            metadata=metadata,
            connection=conn,
            as_of=date(2026, 3, 15),
        )
    )
    payload = built.canonical_bytes()
    conn.close()
    return payload


def test_repeated_calls_are_byte_identical(prompt_input) -> None:
    first = build_prompt(prompt_input).canonical_bytes()
    second = build_prompt(prompt_input).canonical_bytes()
    assert first == second


def test_fresh_connections_yield_identical_prompts() -> None:
    assert _fresh_prompt() == _fresh_prompt()


def test_cwd_and_system_date_do_not_affect_prompt(prompt_input, tmp_path) -> None:
    first = build_prompt(prompt_input).canonical_bytes()
    original_cwd = os.getcwd()
    tz_was_set = "TZ" in os.environ
    original_tz = os.environ.get("TZ")
    try:
        os.chdir(tmp_path)
        os.environ["TZ"] = "Pacific/Honolulu"
        if hasattr(time, "tzset"):
            time.tzset()
        second = build_prompt(prompt_input).canonical_bytes()
        assert first == second
        assert os.getcwd() == str(tmp_path)
    finally:
        os.chdir(original_cwd)
        if tz_was_set:
            assert original_tz is not None
            os.environ["TZ"] = original_tz
        elif "TZ" in os.environ:
            del os.environ["TZ"]
        if hasattr(time, "tzset"):
            time.tzset()


def test_timezone_state_restored_after_determinism_probe(prompt_input) -> None:
    """Changing TZ+tzset must not permanently alter later prompt builds."""
    if not hasattr(time, "tzset"):
        return

    baseline = build_prompt(prompt_input).canonical_bytes()
    tz_was_set = "TZ" in os.environ
    original_tz = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "Pacific/Honolulu"
        time.tzset()
        during = build_prompt(prompt_input).canonical_bytes()
        assert during == baseline
    finally:
        if tz_was_set:
            assert original_tz is not None
            os.environ["TZ"] = original_tz
        elif "TZ" in os.environ:
            del os.environ["TZ"]
        time.tzset()

    after = build_prompt(prompt_input).canonical_bytes()
    assert after == baseline
    if tz_was_set:
        assert os.environ.get("TZ") == original_tz
    else:
        assert "TZ" not in os.environ


def test_independently_loaded_metadata_is_equivalent() -> None:
    left = _fresh_prompt("What is gross ticket revenue?")
    right = _fresh_prompt("What is gross ticket revenue?")
    assert left == right


def test_canonical_text_normalizes_newlines(prompt_input) -> None:
    text = build_prompt(prompt_input).canonical_text()
    assert "\r" not in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n\n")
