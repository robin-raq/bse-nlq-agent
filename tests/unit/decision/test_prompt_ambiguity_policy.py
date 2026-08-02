"""Revenue-ranking ambiguity default (disclosed gross default, not silent).

`SYSTEM_RULES` is static regardless of the user's question, so these
assertions run against `built_prompt.system_instructions` directly rather
than needing a live model call — they prove the *policy text* was changed
correctly and narrowly. Whether the real model actually follows it is
verified separately via the live evaluation (`evaluation/`), never as part
of the offline, credential-free test suite.
"""

from __future__ import annotations

from bse_nlq.prompt.models import BuiltPrompt


def test_revenue_ranking_default_is_documented(built_prompt: BuiltPrompt) -> None:
    text = built_prompt.system_instructions
    assert "gross ticket revenue" in text.lower()
    assert "gross_ticket_revenue_cents" in text
    assert "disclose" in text.lower()


def test_revenue_ranking_default_asks_at_most_one_clarification(
    built_prompt: BuiltPrompt,
) -> None:
    text = built_prompt.system_instructions.lower()
    assert "at most one clarifying question" in text
    assert "never two" in text


def test_explicit_gross_or_net_wording_still_honored(built_prompt: BuiltPrompt) -> None:
    text = built_prompt.system_instructions.lower()
    assert "must be honored directly" in text
    assert "never override an explicit choice" in text


def test_open_ended_status_question_still_requires_clarification(
    built_prompt: BuiltPrompt,
) -> None:
    text = built_prompt.system_instructions.lower()
    assert "how are sales doing" in text
    assert "must still ask for metric, period, and comparison baseline" in text


def test_subjective_best_event_still_requires_clarification(
    built_prompt: BuiltPrompt,
) -> None:
    text = built_prompt.system_instructions.lower()
    assert "what was the best event" in text
    assert "must still ask for a success metric and period" in text


def test_sold_out_ambiguity_still_requires_clarification(
    built_prompt: BuiltPrompt,
) -> None:
    text = built_prompt.system_instructions.lower()
    assert "sold-out questions must still ask" in text


def test_old_unconditional_blanket_ambiguity_rule_is_gone(
    built_prompt: BuiltPrompt,
) -> None:
    # The narrowing replaced this unconditional line rather than merely
    # adding a carve-out alongside it.
    text = built_prompt.system_instructions
    assert (
        "Do not silently resolve frozen ambiguities (bare revenue, best event, "
        "how are sales doing, sold out)." not in text
    )


def test_revenue_default_scope_is_limited_to_explicit_revenue_metric(
    built_prompt: BuiltPrompt,
) -> None:
    text = built_prompt.system_instructions.lower()
    assert "this default applies only to explicit ranking/aggregation" in text
    assert "that name" in text and "revenue" in text
