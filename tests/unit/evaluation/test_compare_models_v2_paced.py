"""Offline checks for the paired prompt version 2 comparison schedule."""

from __future__ import annotations

from evaluation.model_comparison.compare_models import _load_manifest
from evaluation.model_comparison.compare_models_v2_paced import (
    _base_schedule,
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
