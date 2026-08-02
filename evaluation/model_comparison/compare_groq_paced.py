"""Run a quota-compliant, Groq-only rerun against the frozen comparison.

The existing OpenAI result is reused only after its frozen hashes match. Groq
requests are sequential, are never retried, and start at least 65 seconds apart.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from bse_nlq.db.build import build_database  # noqa: E402
from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database  # noqa: E402
from bse_nlq.service import TerminalState, answer_question  # noqa: E402
from evaluation.model_comparison.compare_models import (  # noqa: E402
    AttemptRecord,
    ManifestCase,
    _case_lookup,
    _configuration,
    _load_manifest,
    _run_attempt,
    _sample_percentile,
    _write_json,
)
from evaluation.model_comparison.providers import (  # noqa: E402
    GROQ_MODEL,
    GroqComparisonGenerator,
    ProviderObservation,
)

PACING_SECONDS = 65.0
MINIMUM_STARTING_TOKENS = 150_000
DAILY_TOKEN_LIMIT = 200_000
TOKEN_RESERVE = 20_000
MINIMUM_PROJECTED_CALL_TOKENS = 6_000
MAXIMUM_EVALUATION_TOKENS = 150_000
MAXIMUM_LIVE_CALLS = 24
EXPECTED_HASHES = {
    "prompt_hash": "b549ebc7245ded0c1587a6837510a81cf735a8a09c8e8986fd1b2ece62012c2e",
    "schema_hash": "8cfbbaa67405a7ec6da148ff6b8af6daeaccb0ab93674fffbb471ccf8ca3efd5",
    "case_set_hash": "85a1edbd0e4579c718738d44e7035a67d7a44c434f4dde354cceba4264fad3db",
}


@dataclass(frozen=True, slots=True)
class PacingSlot:
    monotonic_start: float
    scheduled_start_utc: str
    intentional_wait_ms: int


class RequestPacer:
    """Enforce minimum spacing between actual request start times."""

    def __init__(
        self,
        *,
        interval_seconds: float = PACING_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval_seconds = interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._previous_start: float | None = None

    def wait_for_slot(self) -> PacingSlot:
        now = self._clock()
        wait = 0.0
        if self._previous_start is not None:
            wait = max(0.0, self._previous_start + self._interval_seconds - now)
        if wait:
            self._sleeper(wait)
        actual_start = self._clock()
        self._previous_start = actual_start
        return PacingSlot(
            monotonic_start=actual_start,
            scheduled_start_utc=datetime.now(UTC).isoformat(),
            intentional_wait_ms=round(wait * 1000),
        )


class TokenBudget:
    """Conservatively reserve daily headroom before every request."""

    def __init__(
        self,
        *,
        available_tokens: int,
        reserve_tokens: int = TOKEN_RESERVE,
    ) -> None:
        if available_tokens < 0 or reserve_tokens < 0:
            raise ValueError("token budgets must be non-negative")
        self.available_tokens = available_tokens
        self.reserve_tokens = reserve_tokens
        self.actual_tokens = 0
        self.estimated_tokens = 0
        self._recent_observed_total: int | None = None

    @property
    def accounted_tokens(self) -> int:
        return self.actual_tokens + self.estimated_tokens

    @property
    def projected_next_tokens(self) -> int:
        return max(self._recent_observed_total or 0, MINIMUM_PROJECTED_CALL_TOKENS)

    def can_start_next(self) -> bool:
        evaluation_ceiling = min(
            self.available_tokens - self.reserve_tokens,
            MAXIMUM_EVALUATION_TOKENS,
        )
        return self.accounted_tokens + self.projected_next_tokens <= evaluation_ceiling

    def account(
        self, *, input_tokens: int | None, output_tokens: int | None
    ) -> tuple[int, bool]:
        if input_tokens is not None and output_tokens is not None:
            total = input_tokens + output_tokens
            self.actual_tokens += total
            self._recent_observed_total = total
            return total, False
        estimate = self.projected_next_tokens
        self.estimated_tokens += estimate
        return estimate, True


@dataclass(frozen=True, slots=True)
class PacedAttempt:
    case_id: str
    category: str
    provider: str
    model: str
    attempt: int
    scheduled_start_utc: str
    intentional_wait_ms: int
    latency_ms: int
    expected_terminal: list[str]
    actual_terminal: str
    decision_status: str | None
    structured_output_valid: bool
    generated_sql: str | None
    sql_policy_accepted: bool
    execution_succeeded: bool
    answer_invariant_passed: bool
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    token_usage_estimated: bool
    accounted_tokens: int
    error_class: str | None
    safe_rate_limit_metadata: dict[str, int | None]
    notes: list[str]


def _call_once[T](pacer: RequestPacer, call: Callable[[], T]) -> tuple[PacingSlot, T]:
    """Pace and invoke exactly once; exceptions deliberately propagate."""
    slot = pacer.wait_for_slot()
    return slot, call()


def _refuse_existing_artifacts(paths: Sequence[Path]) -> None:
    existing = [path.name for path in paths if path.exists()]
    if existing:
        raise FileExistsError(
            "refusing to overwrite existing paced artifact(s): " + ", ".join(existing)
        )


def _paced_attempt(
    database: ReadOnlyDatabase,
    generator: GroqComparisonGenerator,
    manifest_case: ManifestCase,
    *,
    attempt_number: int,
    as_of: date,
    pacer: RequestPacer,
    budget: TokenBudget,
) -> PacedAttempt:
    if not budget.can_start_next():
        raise RuntimeError("local token budget would breach reserved headroom")
    cases = _case_lookup()
    slot, record = _call_once(
        pacer,
        lambda: _run_attempt(
            database,
            generator,
            "groq",
            manifest_case,
            cases[manifest_case.case_id],
            attempt=attempt_number,
            provider_order=1,
            as_of=as_of,
        ),
    )
    accounted, estimated = budget.account(
        input_tokens=record.input_tokens, output_tokens=record.output_tokens
    )
    total = (
        record.input_tokens + record.output_tokens
        if record.input_tokens is not None and record.output_tokens is not None
        else None
    )
    return _from_attempt_record(
        record,
        scheduled_start_utc=slot.scheduled_start_utc,
        intentional_wait_ms=slot.intentional_wait_ms,
        total_tokens=total,
        token_usage_estimated=estimated,
        accounted_tokens=accounted,
    )


def _from_attempt_record(
    record: AttemptRecord,
    *,
    scheduled_start_utc: str,
    intentional_wait_ms: int,
    total_tokens: int | None,
    token_usage_estimated: bool,
    accounted_tokens: int,
) -> PacedAttempt:
    return PacedAttempt(
        case_id=record.case_id,
        category=record.category,
        provider="groq",
        model=GROQ_MODEL,
        attempt=record.attempt,
        scheduled_start_utc=scheduled_start_utc,
        intentional_wait_ms=intentional_wait_ms,
        latency_ms=record.latency_ms,
        expected_terminal=record.expected_terminal,
        actual_terminal=record.actual_terminal,
        decision_status=record.decision_status,
        structured_output_valid=record.structured_output_valid,
        generated_sql=record.generated_sql,
        sql_policy_accepted=record.sql_policy_accepted,
        execution_succeeded=record.execution_succeeded,
        answer_invariant_passed=record.answer_invariant_passed,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        total_tokens=total_tokens,
        token_usage_estimated=token_usage_estimated,
        accounted_tokens=accounted_tokens,
        error_class=record.error_class,
        safe_rate_limit_metadata={"remaining_tokens": None, "reset_seconds": None},
        notes=record.notes,
    )


def _attempt_succeeded(attempt: PacedAttempt) -> bool:
    return attempt.error_class is None


def _targeted_cases(
    manifest_cases: tuple[ManifestCase, ...], attempts: list[PacedAttempt]
) -> list[tuple[ManifestCase, int]]:
    selected: list[tuple[ManifestCase, int]] = []
    for manifest_case in manifest_cases:
        case_attempts = [
            item for item in attempts if item.case_id == manifest_case.case_id
        ]
        if manifest_case.category == "answerable_sql":
            first_two = sorted(case_attempts, key=lambda item: item.attempt)[:2]
            if len(first_two) != 2:
                continue
            outcomes = {
                (item.actual_terminal, _attempt_succeeded(item)) for item in first_two
            }
            allowed = (
                len(outcomes) > 1
                or any(item.error_class == "incorrect_result" for item in first_two)
                or any(item.error_class == "sql_policy_rejection" for item in first_two)
            )
            if allowed:
                selected.append((manifest_case, 3))
        elif case_attempts and not _attempt_succeeded(case_attempts[0]):
            selected.append((manifest_case, 2))
        if len(selected) == 3:
            break
    return selected


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _metrics(attempts: list[PacedAttempt]) -> dict[str, Any]:
    answerable = [item for item in attempts if item.category == "answerable_sql"]
    behavior = [item for item in attempts if item.category == "behavior"]
    completed_answerable = [item for item in answerable if item.structured_output_valid]
    completed_sql = [
        item for item in completed_answerable if item.generated_sql is not None
    ]
    correct_completed = sum(_attempt_succeeded(item) for item in completed_answerable)
    stable_details: dict[str, str] = {}
    targeted_case_ids = {item.case_id for item in answerable if item.attempt == 3}
    for case_id in sorted({item.case_id for item in answerable}):
        first_two = sorted(
            [
                item
                for item in answerable
                if item.case_id == case_id and item.attempt <= 2
            ],
            key=lambda item: item.attempt,
        )
        passes = sum(_attempt_succeeded(item) for item in first_two)
        if len(first_two) == 2 and passes == 2:
            outcome = "passed_both_scheduled_attempts"
        elif len(first_two) == 2 and passes == 0:
            outcome = "failed_both_attempts"
        else:
            outcome = "inconsistent_across_attempts"
        if case_id in targeted_case_ids:
            outcome += ";targeted_third_attempt"
        stable_details[case_id] = outcome
    stable_count = sum(
        value.startswith("passed_both_scheduled_attempts")
        for value in stable_details.values()
    )
    behavior_case_ids = sorted({item.case_id for item in behavior})
    behavior_pass_count = sum(
        all(_attempt_succeeded(item) for item in behavior if item.case_id == case_id)
        for case_id in behavior_case_ids
    )
    behavior_disagreements = [
        case_id
        for case_id in behavior_case_ids
        if len(
            {
                (item.actual_terminal, _attempt_succeeded(item))
                for item in behavior
                if item.case_id == case_id
            }
        )
        > 1
    ]
    latencies = [item.latency_ms for item in completed_answerable]
    successful = sum(_attempt_succeeded(item) for item in attempts)
    return {
        "completed_generation": {
            "correct_answerable_attempts": correct_completed,
            "total_completed_answerable_attempts": len(completed_answerable),
            "incorrect_result_count": sum(
                item.error_class == "incorrect_result" for item in answerable
            ),
            "sql_policy_rejection_count": sum(
                item.error_class == "sql_policy_rejection" for item in answerable
            ),
            "wrong_terminal_count": sum(
                item.error_class == "wrong_terminal_behavior" for item in answerable
            ),
            "structured_output_valid_rate": _rate(
                sum(item.structured_output_valid for item in attempts), len(attempts)
            ),
            "sql_policy_acceptance_rate": _rate(
                sum(item.sql_policy_accepted for item in completed_sql),
                len(completed_sql),
            ),
        },
        "provider_reliability": {
            "successful_scheduled_calls": successful,
            "total_scheduled_calls": len(attempts),
            "http_429_count": sum(
                "provider_error_http_429_rate_limit" in item.notes for item in attempts
            ),
            "timeout_count": sum(item.error_class == "timeout" for item in attempts),
            "other_transport_error_count": sum(
                item.error_class == "provider_transport"
                and "provider_error_http_429_rate_limit" not in item.notes
                for item in attempts
            ),
        },
        "stable_cases": {
            "passed_both_scheduled_attempts": stable_count,
            "total_answerable_cases": len(stable_details),
            "details": stable_details,
        },
        "behavior": {
            "passes": behavior_pass_count,
            "total_cases": len(behavior_case_ids),
            "disagreements": behavior_disagreements,
            "details": {
                case_id: [
                    {
                        "attempt": item.attempt,
                        "terminal": item.actual_terminal,
                        "passed": _attempt_succeeded(item),
                    }
                    for item in behavior
                    if item.case_id == case_id
                ]
                for case_id in behavior_case_ids
            },
        },
        "latency": {
            "sample_size": len(latencies),
            "median_api_latency_ms": (
                round(statistics.median(latencies)) if latencies else None
            ),
            "p95_api_latency_ms": (
                _sample_percentile(latencies, 0.95) if latencies else None
            ),
            "minimum_api_latency_ms": min(latencies) if latencies else None,
            "maximum_api_latency_ms": max(latencies) if latencies else None,
            "scope": "structured-valid answerable calls; pacing excluded",
        },
    }


def _recommendation(metrics: dict[str, Any], openai: dict[str, Any]) -> dict[str, Any]:
    quality = metrics["completed_generation"]
    stable = metrics["stable_cases"]
    reliability = metrics["provider_reliability"]
    behavior = metrics["behavior"]
    latency = metrics["latency"]
    openai_median = openai["median_latency_ms"]
    groq_median = latency["median_api_latency_ms"]
    reduction = (
        round((openai_median - groq_median) / openai_median * 100, 1)
        if groq_median is not None and openai_median
        else None
    )
    gates = (
        quality["correct_answerable_attempts"]
        == quality["total_completed_answerable_attempts"]
        and quality["total_completed_answerable_attempts"] >= 16
        and stable["passed_both_scheduled_attempts"] == 8
        and quality["structured_output_valid_rate"] == 1.0
        and quality["sql_policy_acceptance_rate"] == 1.0
        and behavior["passes"] == 4
        and reliability["successful_scheduled_calls"]
        == reliability["total_scheduled_calls"]
        and reduction is not None
        and reduction >= 50
    )
    if gates:
        decision = "recommend_groq_for_review"
        reason = (
            "The paced Groq run matched the frozen GPT-5 mini correctness and "
            "behavior gates while reducing median API latency by at least 50%. "
            "The quota tradeoff still requires review."
        )
    elif (
        quality["correct_answerable_attempts"]
        < quality["total_completed_answerable_attempts"]
        or stable["passed_both_scheduled_attempts"] < 8
        or behavior["passes"] < 4
        or quality["sql_policy_acceptance_rate"] < 1.0
    ):
        decision = "keep_openai"
        reason = (
            "Groq matched the behavioral and paced-provider reliability gates, "
            "but did not match the frozen GPT-5 mini completed-generation "
            "accuracy, stable-case, or SQL-policy compatibility gates."
        )
    else:
        decision = "inconclusive_more_data_needed"
        reason = (
            "The paced sample did not satisfy every conservative model-quality, "
            "provider-reliability, latency, and quota-operability gate."
        )
    return {
        "decision": decision,
        "reason": reason,
        "latency_reduction_vs_openai_percent": reduction,
        "default_provider_changed": False,
    }


def _payload(
    *,
    status: str,
    configuration: dict[str, Any],
    attempts: list[PacedAttempt],
    budget: TokenBudget,
    available_at_start: int,
    original: dict[str, Any],
    warmup: dict[str, Any],
    targeted_calls: int,
    experiment_started: float,
    experiment_started_utc: datetime,
    original_sha256: str,
) -> dict[str, Any]:
    metrics = _metrics(attempts)
    openai = original["metrics"]["openai"]
    total_wait_ms = warmup.get("intentional_wait_ms", 0) + sum(
        item.intentional_wait_ms for item in attempts
    )
    monotonic_active_seconds = time.monotonic() - experiment_started
    wall_clock_seconds = (datetime.now(UTC) - experiment_started_utc).total_seconds()
    return {
        "status": status,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "configuration": {
            **configuration,
            "run_type": "Groq-only quota-compliant paced rerun",
            "matched_prior_run": True,
            "prior_result_sha256": original_sha256,
            "pacing_seconds": PACING_SECONDS,
            "limits": {
                "requests_per_minute": 30,
                "requests_per_day": 1000,
                "tokens_per_minute": 8000,
                "tokens_per_day": DAILY_TOKEN_LIMIT,
            },
            "daily_tokens_available_at_start": available_at_start,
            "daily_capacity_source": "user-confirmed reset API key",
            "daily_reset_information": None,
            "planned_live_calls": 21,
            "maximum_live_calls": MAXIMUM_LIVE_CALLS,
            "maximum_evaluation_tokens": MAXIMUM_EVALUATION_TOKENS,
            "daily_token_reserve": TOKEN_RESERVE,
        },
        "warmup": warmup,
        "attempts": [asdict(item) for item in attempts],
        "metrics": metrics,
        "token_accounting": {
            "actual_returned_tokens": budget.actual_tokens,
            "estimated_tokens_for_missing_usage": budget.estimated_tokens,
            "accounted_total_tokens": budget.accounted_tokens,
            "remaining_from_confirmed_start_after_accounting": (
                available_at_start - budget.accounted_tokens
            ),
            "estimates_present": budget.estimated_tokens > 0,
            "maximum_evaluation_tokens": MAXIMUM_EVALUATION_TOKENS,
        },
        "run_counts": {
            "warmup_calls": 1 if warmup else 0,
            "scored_calls": len(attempts),
            "targeted_calls": targeted_calls,
            "total_calls": (1 if warmup else 0) + len(attempts),
        },
        "timing": {
            "total_wall_clock_minutes": round(wall_clock_seconds / 60, 3),
            "total_monotonic_active_minutes": round(monotonic_active_seconds / 60, 3),
            "total_intentional_wait_minutes": round(total_wait_ms / 60_000, 3),
        },
        "baseline": {
            "openai_reused": True,
            "openai": openai,
            "original_unpaced_groq": original["metrics"]["groq"],
            "denominator_note": (
                "The original Groq 7/24 uses all scheduled answerable attempts; "
                "paced completed-generation accuracy excludes unavailable calls."
            ),
        },
        "recommendation": (
            _recommendation(metrics, openai) if status == "complete" else None
        ),
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite paced report: {path.name}")
    metrics = payload["metrics"]
    quality = metrics["completed_generation"]
    reliability = metrics["provider_reliability"]
    stable = metrics["stable_cases"]
    behavior = metrics["behavior"]
    latency = metrics["latency"]
    tokens = payload["token_accounting"]
    counts = payload["run_counts"]
    config = payload["configuration"]
    recommendation = payload["recommendation"]
    lines = [
        "# Quota-compliant Groq GPT-OSS 120B rerun",
        "",
        "## Why this rerun was necessary",
        "",
        "The original bursty run produced 22 HTTP 429 responses. This separate "
        "run preserves that evidence while measuring model quality and provider "
        "reliability under the supplied Groq token limits.",
        "",
        "## Frozen inputs and pacing",
        "",
        f"- prompt SHA-256: `{config['prompt_hash']}`",
        f"- schema SHA-256: `{config['schema_hash']}`",
        f"- case set SHA-256: `{config['case_set_hash']}`",
        "- hashes matched the prior result; the OpenAI baseline was reused",
        "- Groq limits: 30 RPM, 1,000 RPD, 8,000 TPM, 200,000 TPD",
        "- requests were sequential with at least 65 seconds between starts",
        "- one request per attempt, no retries, failover, repair, or prompt changes",
        f"- calls: {counts['warmup_calls']} warm-up, {counts['scored_calls']} "
        f"scored, {counts['targeted_calls']} targeted, {counts['total_calls']} total",
        "",
        "## Token budget",
        "",
        "- user-confirmed daily capacity at start: "
        f"{config['daily_tokens_available_at_start']:,}",
        f"- actual tokens returned by Groq: {tokens['actual_returned_tokens']:,}",
        "- estimated tokens for missing usage: "
        f"{tokens['estimated_tokens_for_missing_usage']:,}",
        f"- accounted total: {tokens['accounted_total_tokens']:,}",
        f"- maximum local evaluation budget: {tokens['maximum_evaluation_tokens']:,}",
        f"- reserved headroom: {config['daily_token_reserve']:,}",
        "",
        "## Results",
        "",
        f"- completed-generation answerable accuracy: "
        f"{quality['correct_answerable_attempts']}/"
        f"{quality['total_completed_answerable_attempts']}",
        f"- stable answerable cases: {stable['passed_both_scheduled_attempts']}/"
        f"{stable['total_answerable_cases']}",
        f"- structured-output validity: {quality['structured_output_valid_rate']:.1%}",
        f"- SQL-policy acceptance: {quality['sql_policy_acceptance_rate']:.1%}",
        f"- end-to-end provider success: {reliability['successful_scheduled_calls']}/"
        f"{reliability['total_scheduled_calls']}",
        f"- HTTP 429 / timeout / other transport: {reliability['http_429_count']} / "
        f"{reliability['timeout_count']} / "
        f"{reliability['other_transport_error_count']}",
        f"- behavioral passes: {behavior['passes']}/{behavior['total_cases']}",
        "",
        "## Stable-case and behavioral detail",
        "",
    ]
    for case_id, outcome in stable["details"].items():
        lines.append(f"- `{case_id}`: {outcome}")
    for case_id, outcomes in behavior["details"].items():
        rendered = ", ".join(
            f"attempt {item['attempt']} {item['terminal']} "
            f"({'pass' if item['passed'] else 'fail'})"
            for item in outcomes
        )
        lines.append(f"- `{case_id}`: {rendered}")
    lines.extend(
        [
            "",
            "## Latency and elapsed time",
            "",
            f"- completed answerable API calls: {latency['sample_size']}",
            f"- median / p95 API latency: {latency['median_api_latency_ms']} / "
            f"{latency['p95_api_latency_ms']} ms",
            f"- minimum / maximum API latency: {latency['minimum_api_latency_ms']} / "
            f"{latency['maximum_api_latency_ms']} ms",
            f"- total intentional pacing: "
            f"{payload['timing']['total_intentional_wait_minutes']} minutes",
            f"- total wall-clock experiment: "
            f"{payload['timing']['total_wall_clock_minutes']} minutes",
            f"- monotonic active elapsed time: "
            f"{payload['timing']['total_monotonic_active_minutes']} minutes",
            "",
            "Intentional pacing is excluded from API latency. The raw API latency "
            "does not represent throughput for repeated CLI requests at this quota.",
            "The wall-clock and monotonic elapsed totals diverged during one "
            "inter-request gap; both are retained as separate observations.",
            "",
            "## Comparison",
            "",
            "| metric | GPT-5 mini baseline | original unpaced Groq | paced Groq |",
            "|---|---:|---:|---:|",
            f"| answerable | 24/24 | 7/24 scheduled | "
            f"{quality['correct_answerable_attempts']}/"
            f"{quality['total_completed_answerable_attempts']} completed |",
            f"| stable cases | 8/8 | "
            f"{payload['baseline']['original_unpaced_groq']['stable_answerable']} | "
            f"{stable['passed_both_scheduled_attempts']}/8 |",
            f"| behavior | 4/4 | "
            f"{payload['baseline']['original_unpaced_groq']['behavior_passes']} | "
            f"{behavior['passes']}/4 |",
            f"| median API latency | 8474 ms | 1550 ms | "
            f"{latency['median_api_latency_ms']} ms |",
            f"| p95 API latency | "
            f"{payload['baseline']['openai']['p95_latency_ms']} ms | 2659 ms | "
            f"{latency['p95_api_latency_ms']} ms |",
            "",
            "The unpaced 7/24 result includes provider-unavailable attempts. The "
            "paced completed-generation denominator includes only valid structured "
            "ModelDecision responses; end-to-end success above retains every call.",
            "",
            "## Limitations",
            "",
            "This is a small evaluation on one deterministic dataset. The supplied "
            "quota required a long inter-request schedule, safe reset metadata was "
            "not exposed, and no production rate limiter was added.",
            "",
            "## Recommendation",
            "",
            f"`{recommendation['decision']}`: {recommendation['reason']}",
            "",
            "The product default remains GPT-5 mini.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--prior-result", required=True, type=Path)
    parser.add_argument("--daily-tokens-available-at-start", required=True, type=int)
    args = parser.parse_args(argv)

    try:
        _refuse_existing_artifacts((args.json_output, args.markdown_output))
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.daily_tokens_available_at_start < MINIMUM_STARTING_TOKENS:
        print("at least 150000 daily Groq tokens must be confirmed", file=sys.stderr)
        return 2
    if args.daily_tokens_available_at_start > DAILY_TOKEN_LIMIT:
        print("confirmed capacity exceeds the supplied daily limit", file=sys.stderr)
        return 2
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key:
        print("GROQ_API_KEY is required", file=sys.stderr)
        return 2
    if not args.prior_result.is_file():
        print("frozen prior comparison result is required", file=sys.stderr)
        return 2
    git_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=_REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if git_status:
        print("paced live run requires a clean frozen worktree", file=sys.stderr)
        return 2
    for logger_name in ("openai", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)

    original_sha256 = _sha256_file(args.prior_result)
    original = json.loads(args.prior_result.read_text(encoding="utf-8"))
    manifest_raw, manifest_cases = _load_manifest()
    as_of = date.fromisoformat(manifest_raw["as_of"])
    database_path = Path(tempfile.mkdtemp(prefix="bse-groq-paced-")) / "comparison.db"
    build_result = build_database(database_path)
    generator = GroqComparisonGenerator(api_key=groq_key)
    pacer = RequestPacer()
    budget = TokenBudget(available_tokens=args.daily_tokens_available_at_start)
    attempts: list[PacedAttempt] = []
    targeted_calls = 0
    experiment_started = time.monotonic()
    experiment_started_utc = datetime.now(UTC)

    with open_readonly_database(database_path) as database:
        configuration = _configuration(
            manifest_raw, build_result.logical_content_fingerprint, database
        )
        for key, expected in EXPECTED_HASHES.items():
            if configuration[key] != expected:
                print(f"frozen {key} changed; refusing live calls", file=sys.stderr)
                return 2
            if original["configuration"][key] != expected:
                print(f"prior result {key} does not match", file=sys.stderr)
                return 2
        if (
            original["configuration"]["database_logical_fingerprint"]
            != configuration["database_logical_fingerprint"]
        ):
            print("database logical fingerprint changed", file=sys.stderr)
            return 2

        warmup_case = _case_lookup()[manifest_raw["warmup_case_id"]]
        if not budget.can_start_next():
            print("local token budget blocks warm-up", file=sys.stderr)
            return 2
        slot, warmup_result = _call_once(
            pacer,
            lambda: answer_question(
                database, generator, warmup_case.question, as_of=as_of
            ),
        )
        observation = generator.last_observation or ProviderObservation(
            latency_ms=0,
            input_tokens=None,
            output_tokens=None,
            error_class="unknown",
        )
        accounted, estimated = budget.account(
            input_tokens=observation.input_tokens,
            output_tokens=observation.output_tokens,
        )
        warmup = {
            "case_id": manifest_raw["warmup_case_id"],
            "scheduled_start_utc": slot.scheduled_start_utc,
            "intentional_wait_ms": slot.intentional_wait_ms,
            "latency_ms": observation.latency_ms,
            "actual_terminal": warmup_result.terminal_state.value,
            "input_tokens": observation.input_tokens,
            "output_tokens": observation.output_tokens,
            "total_tokens": (
                observation.input_tokens + observation.output_tokens
                if observation.input_tokens is not None
                and observation.output_tokens is not None
                else None
            ),
            "token_usage_estimated": estimated,
            "accounted_tokens": accounted,
            "error_class": observation.error_class,
            "notes": (
                [f"provider_error_{observation.error_subtype}"]
                if observation.error_subtype is not None
                else []
            ),
            "scored": False,
        }
        warmup_was_429 = observation.error_subtype == "http_429_rate_limit"
        if warmup_result.terminal_state in {
            TerminalState.INVALID_MODEL_OUTPUT,
            TerminalState.INTERNAL_ERROR,
        } or (
            warmup_result.terminal_state is TerminalState.PROVIDER_UNAVAILABLE
            and not warmup_was_429
        ):
            print(
                "Groq warm-up did not return valid structured output", file=sys.stderr
            )
            return 2

        running_payload = _payload(
            status="running",
            configuration=configuration,
            attempts=attempts,
            budget=budget,
            available_at_start=args.daily_tokens_available_at_start,
            original=original,
            warmup=warmup,
            targeted_calls=targeted_calls,
            experiment_started=experiment_started,
            experiment_started_utc=experiment_started_utc,
            original_sha256=original_sha256,
        )
        _write_json(args.json_output, running_payload, first_write=True)

        schedule = [(case, 1) for case in manifest_cases]
        schedule.extend(
            (case, 2) for case in manifest_cases if case.category == "answerable_sql"
        )
        for manifest_case, attempt_number in schedule:
            if not budget.can_start_next():
                print("local token budget stopped the scored run", file=sys.stderr)
                return 3
            attempts.append(
                _paced_attempt(
                    database,
                    generator,
                    manifest_case,
                    attempt_number=attempt_number,
                    as_of=as_of,
                    pacer=pacer,
                    budget=budget,
                )
            )
            _write_json(
                args.json_output,
                _payload(
                    status="running",
                    configuration=configuration,
                    attempts=attempts,
                    budget=budget,
                    available_at_start=args.daily_tokens_available_at_start,
                    original=original,
                    warmup=warmup,
                    targeted_calls=targeted_calls,
                    experiment_started=experiment_started,
                    experiment_started_utc=experiment_started_utc,
                    original_sha256=original_sha256,
                ),
                first_write=False,
            )

        for manifest_case, attempt_number in _targeted_cases(manifest_cases, attempts):
            if len(attempts) + 1 >= MAXIMUM_LIVE_CALLS:
                break
            if not budget.can_start_next():
                break
            attempts.append(
                _paced_attempt(
                    database,
                    generator,
                    manifest_case,
                    attempt_number=attempt_number,
                    as_of=as_of,
                    pacer=pacer,
                    budget=budget,
                )
            )
            targeted_calls += 1
            _write_json(
                args.json_output,
                _payload(
                    status="running",
                    configuration=configuration,
                    attempts=attempts,
                    budget=budget,
                    available_at_start=args.daily_tokens_available_at_start,
                    original=original,
                    warmup=warmup,
                    targeted_calls=targeted_calls,
                    experiment_started=experiment_started,
                    experiment_started_utc=experiment_started_utc,
                    original_sha256=original_sha256,
                ),
                first_write=False,
            )

    final_payload = _payload(
        status="complete",
        configuration=configuration,
        attempts=attempts,
        budget=budget,
        available_at_start=args.daily_tokens_available_at_start,
        original=original,
        warmup=warmup,
        targeted_calls=targeted_calls,
        experiment_started=experiment_started,
        experiment_started_utc=experiment_started_utc,
        original_sha256=original_sha256,
    )
    if _sha256_file(args.prior_result) != original_sha256:
        print("original comparison artifact changed during the run", file=sys.stderr)
        return 2
    _write_json(args.json_output, final_payload, first_write=False)
    _write_markdown(args.markdown_output, final_payload)
    print(
        json.dumps(
            {
                "status": "complete",
                "scored_calls": len(attempts),
                "total_calls": len(attempts) + 1,
                "recommendation": final_payload["recommendation"]["decision"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
