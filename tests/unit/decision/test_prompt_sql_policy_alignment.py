"""Prompt rules expose the SQL policy needed for one shot generation."""

from __future__ import annotations

import hashlib

from bse_nlq.prompt import PromptInput, build_prompt
from bse_nlq.prompt.models import APPLICATION_POLICY_VERSION
from bse_nlq.prompt.policy import SYSTEM_RULES


def test_sql_policy_alignment_bumps_prompt_policy_version() -> None:
    assert APPLICATION_POLICY_VERSION == 2
    assert "policy_version=2" in SYSTEM_RULES


def test_prompt_names_the_complete_sql_function_allowlist() -> None:
    assert "Use only SUM, COUNT, and COALESCE as named SQL functions." in SYSTEM_RULES
    assert "Do not use AVG, ROUND, or NULLIF" in SYSTEM_RULES


def test_prompt_gives_policy_compatible_weighted_average_arithmetic() -> None:
    assert "quantity weighted average ticket price in integer cents" in SYSTEM_RULES
    assert "CASE WHEN SUM(quantity) = 0 THEN NULL" in SYSTEM_RULES
    assert (
        "(2 * SUM(line_gross_cents) + SUM(quantity)) / (2 * SUM(quantity))"
        in SYSTEM_RULES
    )
    assert "(2 * SUM(quantity)) END" in SYSTEM_RULES
    assert "Do not use floating point literals for this calculation." in SYSTEM_RULES


def test_prompt_policy_v2_comparison_hash_is_frozen(
    prompt_input: PromptInput,
) -> None:
    prompt = build_prompt(
        PromptInput(
            question="How many events are still scheduled?",
            metadata=prompt_input.metadata,
            connection=prompt_input.connection,
            as_of=prompt_input.resolved_as_of(),
        )
    )

    assert hashlib.sha256(prompt.canonical_bytes()).hexdigest() == (
        "214bbf9f0260a5a33da06251c0dd0cbde2435d8d1f86d411363d7a35b90bc1e7"
    )
