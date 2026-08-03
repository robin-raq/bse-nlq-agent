"""Focused offline checks for comparison scheduling and scoring."""

from __future__ import annotations

from evaluation.model_comparison.compare_models import (
    AttemptRecord,
    _invariant_passed,
    _load_manifest,
    _paired_response_keys,
    _provider_metrics,
    _provider_order,
    _recommendation,
    _sample_percentile,
)

from bse_nlq.db.execution import RawQueryResult
from bse_nlq.service import QueryResult, TerminalState


def test_manifest_has_only_live_eligible_taxonomy() -> None:
    _, cases = _load_manifest()

    assert len([case for case in cases if case.category == "answerable_sql"]) == 8
    assert len([case for case in cases if case.category == "behavior"]) == 4
    assert all(case.category != "fault_injection" for case in cases)
    injection = next(
        case for case in cases if case.case_id == "unsafe_injection_pressure"
    )
    assert injection.expected_terminal == ("unsupported", "query_rejected")


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


def _attempt(
    provider: str,
    attempt: int,
    *,
    latency_ms: int,
    error_class: str | None = None,
) -> AttemptRecord:
    succeeded = error_class is None
    return AttemptRecord(
        case_id="count",
        category="answerable_sql",
        provider=provider,  # type: ignore[arg-type]
        model="model",
        attempt=attempt,
        provider_order=1,
        expected_terminal=["answered"],
        actual_terminal="answered" if succeeded else "provider_unavailable",
        decision_status="sql_generated" if succeeded else None,
        structured_output_valid=succeeded,
        generated_sql="SELECT COUNT(*) FROM events" if succeeded else None,
        sql_policy_accepted=succeeded,
        execution_succeeded=succeeded,
        answer_invariant_passed=succeeded,
        latency_ms=latency_ms,
        input_tokens=100 if succeeded else None,
        output_tokens=20 if succeeded else None,
        error_class=error_class,
        notes=[],
    )


def test_latency_uses_only_pairs_where_both_providers_responded() -> None:
    attempts = [
        _attempt("openai", 1, latency_ms=9000),
        _attempt("groq", 1, latency_ms=1500),
        _attempt("openai", 2, latency_ms=8000),
        _attempt("groq", 2, latency_ms=80, error_class="provider_transport"),
    ]
    paired = _paired_response_keys(attempts)

    metrics = _provider_metrics(attempts, "groq", 1, paired)

    assert paired == frozenset({("count", 1)})
    assert metrics["provider_response_rate"] == 0.5
    assert metrics["structured_output_valid_rate"] == 1.0
    assert metrics["policy_acceptance_rate"] == 1.0
    assert metrics["latency_sample_size"] == 1
    assert metrics["median_latency_ms"] == 1500
    assert metrics["failed_request_count"] == 1
    assert metrics["failed_request_median_latency_ms"] == 80


def test_recommendation_rejects_lower_repeated_attempt_correctness() -> None:
    common = {
        "first_attempt_answerable": "8/8",
        "stable_answerable": "7/8",
        "provider_response_rate": 1.0,
        "invalid_structured_output_count": 0,
        "policy_rejection_count": 0,
        "behavior_passes": "4/4",
        "median_latency_ms": 10000,
        "p95_latency_ms": 15000,
    }
    openai = {**common, "correct_attempts": "23/24"}
    groq = {
        **common,
        "correct_attempts": "22/24",
        "median_latency_ms": 1000,
        "p95_latency_ms": 2000,
    }

    recommendation = _recommendation({"openai": openai, "groq": groq})

    assert recommendation["decision"] == "keep_openai"
