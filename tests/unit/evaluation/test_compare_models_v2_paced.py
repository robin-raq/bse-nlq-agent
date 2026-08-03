"""Offline checks for the paired prompt version 2 comparison schedule."""

from __future__ import annotations

from evaluation.model_comparison.compare_models import _load_manifest
from evaluation.model_comparison.compare_models_v2_paced import (
    _base_schedule,
    _paired_latency,
    _provider_metrics,
    _recommendation,
    _targeted_cases,
)


def _attempt(
    case_id: str,
    provider: str,
    attempt: int,
    *,
    terminal: str = "answered",
    error_class: str | None = None,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "provider": provider,
        "attempt": attempt,
        "actual_terminal": terminal,
        "error_class": error_class,
    }


def test_base_schedule_has_twenty_scored_attempts_per_provider() -> None:
    _, cases = _load_manifest()

    schedule = _base_schedule(cases)

    assert len(schedule) == 20
    assert sum(case.category == "answerable_sql" for case, _ in schedule) == 16
    assert sum(case.category == "behavior" for case, _ in schedule) == 4


def test_targeted_answerable_case_requires_a_real_disagreement() -> None:
    _, cases = _load_manifest()
    target = next(case for case in cases if case.case_id == "average_ticket_price")
    attempts = [
        _attempt(target.case_id, provider, attempt)
        for attempt in (1, 2)
        for provider in ("openai", "groq")
    ]

    assert _targeted_cases((target,), attempts) == []

    attempts[-1] = _attempt(
        target.case_id,
        "groq",
        2,
        terminal="query_rejected",
        error_class="sql_policy_rejection",
    )
    assert _targeted_cases((target,), attempts) == [(target, 3)]


def test_targeted_behavior_case_runs_when_provider_outcomes_differ() -> None:
    _, cases = _load_manifest()
    target = next(case for case in cases if case.case_id == "unsafe_injection_pressure")
    attempts = [
        _attempt(target.case_id, "openai", 1, terminal="unsupported"),
        _attempt(target.case_id, "groq", 1, terminal="query_rejected"),
    ]

    assert _targeted_cases((target,), attempts) == [(target, 2)]


def test_targeted_schedule_is_capped_at_three_cases() -> None:
    _, cases = _load_manifest()
    answerable = tuple(case for case in cases if case.category == "answerable_sql")
    attempts = [
        _attempt(
            case.case_id,
            provider,
            attempt,
            terminal="query_rejected" if provider == "groq" else "answered",
            error_class="sql_policy_rejection" if provider == "groq" else None,
        )
        for case in answerable
        for attempt in (1, 2)
        for provider in ("openai", "groq")
    ]

    assert len(_targeted_cases(answerable, attempts)) == 3


def _passing_metrics() -> dict[str, object]:
    return {
        "completed_answerable_correct": 16,
        "completed_answerable_total": 16,
        "stable_answerable_passes": 8,
        "structured_output_valid_rate": 1.0,
        "sql_policy_acceptance_rate": 1.0,
        "behavior_passes": 4,
        "end_to_end_successes": 20,
        "scheduled_calls": 20,
    }


def test_recommendation_requires_better_p95_latency() -> None:
    metrics = {"openai": _passing_metrics(), "groq": _passing_metrics()}
    paired = {
        "openai": {"median_ms": 10_000, "p95_ms": 20_000},
        "groq": {"median_ms": 4_000, "p95_ms": 21_000},
    }

    recommendation = _recommendation(metrics, paired)

    assert recommendation["decision"] == "inconclusive_more_data_needed"


def test_recommendation_accepts_better_median_and_p95_latency() -> None:
    metrics = {"openai": _passing_metrics(), "groq": _passing_metrics()}
    paired = {
        "openai": {"median_ms": 10_000, "p95_ms": 20_000},
        "groq": {"median_ms": 4_000, "p95_ms": 8_000},
    }

    recommendation = _recommendation(metrics, paired)

    assert recommendation["decision"] == "recommend_groq_for_review"


def _scored_attempt(
    provider: str,
    attempt: int,
    latency_ms: int,
    *,
    error_class: str | None = None,
) -> dict[str, object]:
    return {
        "provider": provider,
        "category": "answerable_sql",
        "case_id": "count",
        "attempt": attempt,
        "structured_output_valid": True,
        "generated_sql": "SELECT COUNT(*) FROM events",
        "sql_policy_accepted": True,
        "error_class": error_class,
        "notes": [],
        "latency_ms": latency_ms,
        "total_tokens": 5_000,
    }


def test_primary_metrics_exclude_adaptive_targeted_attempts() -> None:
    attempts = [
        _scored_attempt(provider, attempt, latency)
        for attempt, latency in ((1, 1_000), (2, 2_000))
        for provider in ("openai", "groq")
    ]
    attempts.extend(
        [
            _scored_attempt("openai", 3, 30_000),
            _scored_attempt("groq", 3, 100, error_class="wrong_terminal_behavior"),
        ]
    )

    openai = _provider_metrics(attempts, "openai")
    groq = _provider_metrics(attempts, "groq")
    paired = _paired_latency(attempts)

    assert openai["completed_answerable_correct"] == 2
    assert openai["completed_answerable_total"] == 2
    assert openai["targeted_answerable_correct"] == 1
    assert groq["completed_answerable_correct"] == 2
    assert groq["completed_answerable_total"] == 2
    assert groq["targeted_answerable_correct"] == 0
    assert paired["sample_size"] == 2
    assert paired["openai"]["median_ms"] == 1_500
    assert paired["groq"]["median_ms"] == 1_500
