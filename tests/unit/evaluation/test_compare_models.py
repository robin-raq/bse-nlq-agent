"""Focused offline checks for comparison scheduling and scoring."""

from __future__ import annotations

from evaluation.model_comparison.compare_models import (
    _invariant_passed,
    _load_manifest,
    _provider_order,
    _sample_percentile,
)

from bse_nlq.db.execution import RawQueryResult
from bse_nlq.service import QueryResult, TerminalState


def test_manifest_has_only_live_eligible_taxonomy() -> None:
    _, cases = _load_manifest()

    assert len([case for case in cases if case.category == "answerable_sql"]) == 8
    assert len([case for case in cases if case.category == "behavior"]) == 4
    assert all(case.category != "fault_injection" for case in cases)


def test_provider_order_alternates_by_case_and_attempt() -> None:
    assert _provider_order(0, 1) == ("openai", "groq")
    assert _provider_order(1, 1) == ("groq", "openai")
    assert _provider_order(0, 2) == ("groq", "openai")
    assert _provider_order(0, 3) == ("openai", "groq")


def test_answer_invariant_uses_execution_value_not_rendered_text() -> None:
    correct = QueryResult(
        terminal_state=TerminalState.ANSWERED,
        answer="misleading rendered text",
        raw_result=RawQueryResult(columns=("count",), rows=((4,),)),
    )
    wrong = QueryResult(
        terminal_state=TerminalState.ANSWERED,
        answer="4",
        raw_result=RawQueryResult(columns=("count",), rows=((5,),)),
    )

    assert _invariant_passed("scalar_4", correct)
    assert not _invariant_passed("scalar_4", wrong)


def test_clarification_requires_metric_period_and_baseline() -> None:
    incomplete = QueryResult(
        terminal_state=TerminalState.CLARIFICATION_REQUIRED,
        message="Which revenue metric and time period?",
    )
    complete = QueryResult(
        terminal_state=TerminalState.CLARIFICATION_REQUIRED,
        message="Which revenue metric, time period, and comparison baseline?",
    )

    assert not _invariant_passed("clarifies_metric_period_baseline", incomplete)
    assert _invariant_passed("clarifies_metric_period_baseline", complete)


def test_p95_uses_frozen_nearest_rank_method() -> None:
    assert _sample_percentile(list(range(1, 25)), 0.95) == 23
