"""Focused offline checks for the quota-compliant Groq rerun."""

from __future__ import annotations

from pathlib import Path

import pytest
from evaluation.model_comparison.compare_groq_paced import (
    RequestPacer,
    TokenBudget,
    _call_once,
    _refuse_existing_artifacts,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_pacer_keeps_request_starts_at_least_65_seconds_apart() -> None:
    clock = FakeClock()
    pacer = RequestPacer(clock=clock.monotonic, sleeper=clock.sleep)

    first = pacer.wait_for_slot()
    clock.now += 2.0
    second = pacer.wait_for_slot()

    assert first.intentional_wait_ms == 0
    assert second.intentional_wait_ms == 63_000
    assert second.monotonic_start - first.monotonic_start == 65.0


def test_pacing_wait_is_separate_from_provider_latency() -> None:
    clock = FakeClock()
    pacer = RequestPacer(clock=clock.monotonic, sleeper=clock.sleep)
    pacer.wait_for_slot()
    clock.now += 5.0

    slot, result = _call_once(pacer, lambda: {"latency_ms": 1_550})

    assert slot.intentional_wait_ms == 60_000
    assert result["latency_ms"] == 1_550


def test_call_once_does_not_retry_after_rate_limit() -> None:
    clock = FakeClock()
    calls = 0

    def rate_limited() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("sanitized 429")

    with pytest.raises(RuntimeError, match="sanitized 429"):
        _call_once(
            RequestPacer(clock=clock.monotonic, sleeper=clock.sleep), rate_limited
        )

    assert calls == 1


def test_token_budget_stops_at_maximum_local_evaluation_budget() -> None:
    budget = TokenBudget(available_tokens=200_000, reserve_tokens=20_000)
    for _ in range(24):
        budget.account(input_tokens=5_000, output_tokens=1_000)

    assert budget.accounted_tokens == 144_000
    assert budget.projected_next_tokens == 6_000
    assert budget.can_start_next()

    budget.account(input_tokens=5_000, output_tokens=1_000)
    assert not budget.can_start_next()


def test_token_budget_stops_before_reserved_daily_headroom() -> None:
    budget = TokenBudget(available_tokens=150_000, reserve_tokens=20_000)
    for _ in range(21):
        budget.account(input_tokens=5_000, output_tokens=1_000)

    assert budget.accounted_tokens == 126_000
    assert not budget.can_start_next()


def test_missing_usage_is_accounted_as_a_marked_estimate() -> None:
    budget = TokenBudget(available_tokens=200_000, reserve_tokens=20_000)

    budget.account(input_tokens=None, output_tokens=None)

    assert budget.accounted_tokens == 6_000
    assert budget.estimated_tokens == 6_000
    assert budget.actual_tokens == 0


def test_paced_run_refuses_to_overwrite_original_or_new_artifacts(
    tmp_path: Path,
) -> None:
    original = tmp_path / "comparison-2026-08-02.json"
    paced = tmp_path / "comparison-2026-08-02-groq-paced.json"
    original.write_text("preserved", encoding="utf-8")

    _refuse_existing_artifacts((paced,))
    assert original.read_text(encoding="utf-8") == "preserved"

    paced.write_text("checkpoint", encoding="utf-8")
    with pytest.raises(FileExistsError):
        _refuse_existing_artifacts((paced,))
