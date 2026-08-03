"""Run the paired prompt version 2 comparison with paced Groq requests."""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from bse_nlq.db.build import build_database  # noqa: E402
from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database  # noqa: E402
from bse_nlq.service import TerminalState, answer_question  # noqa: E402
from evaluation.model_comparison.compare_groq_paced import (  # noqa: E402
    DAILY_TOKEN_LIMIT,
    MAXIMUM_EVALUATION_TOKENS,
    MAXIMUM_LIVE_CALLS,
    MINIMUM_STARTING_TOKENS,
    PACING_SECONDS,
    TOKEN_RESERVE,
    RequestPacer,
    TokenBudget,
    _call_once,
    _refuse_existing_artifacts,
)
from evaluation.model_comparison.compare_models import (  # noqa: E402
    ManifestCase,
    ProviderName,
    _case_lookup,
    _configuration,
    _load_manifest,
    _provider_order,
    _run_attempt,
    _sample_percentile,
    _write_json,
)
from evaluation.model_comparison.providers import (  # noqa: E402
    GROQ_MODEL,
    OPENAI_MODEL,
    GroqComparisonGenerator,
    OpenAIComparisonGenerator,
    ProviderObservation,
)

EXPECTED_HASHES = {
    "prompt_hash": "214bbf9f0260a5a33da06251c0dd0cbde2435d8d1f86d411363d7a35b90bc1e7",
    "schema_hash": "8cfbbaa67405a7ec6da148ff6b8af6daeaccb0ab93674fffbb471ccf8ca3efd5",
    "case_set_hash": "85a1edbd0e4579c718738d44e7035a67d7a44c434f4dde354cceba4264fad3db",
}
EXPECTED_DATABASE_FINGERPRINT = (
    "428dae0b3d8d9b473a99be9606d9cd10e875ddcefc6e0a0f26d254778addf4d2"
)


def _base_schedule(
    manifest_cases: tuple[ManifestCase, ...],
) -> list[tuple[ManifestCase, int]]:
    schedule = [(case, 1) for case in manifest_cases]
    schedule.extend(
        (case, 2) for case in manifest_cases if case.category == "answerable_sql"
    )
    return schedule


def _attempt_succeeded(attempt: dict[str, Any]) -> bool:
    return attempt["error_class"] is None


def _targeted_cases(
    manifest_cases: tuple[ManifestCase, ...], attempts: list[dict[str, Any]]
) -> list[tuple[ManifestCase, int]]:
    selected: list[tuple[ManifestCase, int]] = []
    for manifest_case in manifest_cases:
        items = [item for item in attempts if item["case_id"] == manifest_case.case_id]
        if manifest_case.category == "answerable_sql":
            scheduled = [item for item in items if item["attempt"] in {1, 2}]
            if len(scheduled) != 4:
                continue
            provider_outcomes = {
                provider: [
                    (item["actual_terminal"], _attempt_succeeded(item))
                    for item in sorted(
                        [value for value in scheduled if value["provider"] == provider],
                        key=lambda value: int(value["attempt"]),
                    )
                ]
                for provider in ("openai", "groq")
            }
            per_provider_disagreement = any(
                len(set(outcomes)) > 1 for outcomes in provider_outcomes.values()
            )
            paired_disagreement = any(
                provider_outcomes["openai"][index] != provider_outcomes["groq"][index]
                for index in range(2)
            )
            material_failure = any(
                item["error_class"]
                in {
                    "incorrect_result",
                    "sql_policy_rejection",
                    "wrong_terminal_behavior",
                }
                for item in scheduled
            )
            if per_provider_disagreement or paired_disagreement or material_failure:
                selected.append((manifest_case, 3))
        else:
            first = [item for item in items if item["attempt"] == 1]
            if len(first) != 2:
                continue
            outcomes = {
                (item["actual_terminal"], _attempt_succeeded(item)) for item in first
            }
            if len(outcomes) > 1 or any(not _attempt_succeeded(item) for item in first):
                selected.append((manifest_case, 2))
        if len(selected) == 3:
            break
    return selected


def _run_provider_attempt(
    database: ReadOnlyDatabase,
    generators: dict[ProviderName, OpenAIComparisonGenerator | GroqComparisonGenerator],
    provider: ProviderName,
    manifest_case: ManifestCase,
    *,
    attempt_number: int,
    provider_order: int,
    as_of: date,
    pacer: RequestPacer,
    budget: TokenBudget,
) -> dict[str, Any]:
    cases = _case_lookup()
    if provider == "groq":
        if not budget.can_start_next():
            raise RuntimeError("local Groq token budget blocks the next request")
        slot, record = _call_once(
            pacer,
            lambda: _run_attempt(
                database,
                generators[provider],
                provider,
                manifest_case,
                cases[manifest_case.case_id],
                attempt=attempt_number,
                provider_order=provider_order,
                as_of=as_of,
            ),
        )
        scheduled_start_utc = slot.scheduled_start_utc
        intentional_wait_ms = slot.intentional_wait_ms
        accounted_tokens, token_usage_estimated = budget.account(
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
        )
    else:
        scheduled_start_utc = datetime.now(UTC).isoformat()
        intentional_wait_ms = 0
        record = _run_attempt(
            database,
            generators[provider],
            provider,
            manifest_case,
            cases[manifest_case.case_id],
            attempt=attempt_number,
            provider_order=provider_order,
            as_of=as_of,
        )
        accounted_tokens = (
            record.input_tokens + record.output_tokens
            if record.input_tokens is not None and record.output_tokens is not None
            else None
        )
        token_usage_estimated = False
    total_tokens = (
        record.input_tokens + record.output_tokens
        if record.input_tokens is not None and record.output_tokens is not None
        else None
    )
    return {
        "case_id": record.case_id,
        "category": record.category,
        "provider": record.provider,
        "model": record.model,
        "attempt": record.attempt,
        "provider_order": record.provider_order,
        "scheduled_start_utc": scheduled_start_utc,
        "intentional_wait_ms": intentional_wait_ms,
        "latency_ms": record.latency_ms,
        "expected_terminal": record.expected_terminal,
        "actual_terminal": record.actual_terminal,
        "decision_status": record.decision_status,
        "structured_output_valid": record.structured_output_valid,
        "generated_sql": record.generated_sql,
        "sql_policy_accepted": record.sql_policy_accepted,
        "execution_succeeded": record.execution_succeeded,
        "answer_invariant_passed": record.answer_invariant_passed,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "total_tokens": total_tokens,
        "token_usage_estimated": token_usage_estimated,
        "accounted_tokens": accounted_tokens,
        "error_class": record.error_class,
        "safe_rate_limit_metadata": {
            "remaining_tokens_per_minute": None,
            "reset_seconds": None,
        },
        "notes": record.notes,
    }


def _warmup(
    database: ReadOnlyDatabase,
    generators: dict[ProviderName, OpenAIComparisonGenerator | GroqComparisonGenerator],
    warmup_question: str,
    *,
    as_of: date,
    pacer: RequestPacer,
    budget: TokenBudget,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for provider in ("openai", "groq"):
        if provider == "groq":
            if not budget.can_start_next():
                raise RuntimeError("local Groq token budget blocks warmup")
            slot, result = _call_once(
                pacer,
                lambda generator=generators[provider]: answer_question(
                    database, generator, warmup_question, as_of=as_of
                ),
            )
            scheduled_start_utc = slot.scheduled_start_utc
            intentional_wait_ms = slot.intentional_wait_ms
        else:
            scheduled_start_utc = datetime.now(UTC).isoformat()
            intentional_wait_ms = 0
            result = answer_question(
                database, generators[provider], warmup_question, as_of=as_of
            )
        observation = generators[provider].last_observation or ProviderObservation(
            latency_ms=0,
            input_tokens=None,
            output_tokens=None,
            error_class="unknown",
        )
        total_tokens = (
            observation.input_tokens + observation.output_tokens
            if observation.input_tokens is not None
            and observation.output_tokens is not None
            else None
        )
        if provider == "groq":
            accounted_tokens, estimated = budget.account(
                input_tokens=observation.input_tokens,
                output_tokens=observation.output_tokens,
            )
        else:
            accounted_tokens = total_tokens
            estimated = False
        record = {
            "provider": provider,
            "model": OPENAI_MODEL if provider == "openai" else GROQ_MODEL,
            "scheduled_start_utc": scheduled_start_utc,
            "intentional_wait_ms": intentional_wait_ms,
            "latency_ms": observation.latency_ms,
            "actual_terminal": result.terminal_state.value,
            "input_tokens": observation.input_tokens,
            "output_tokens": observation.output_tokens,
            "total_tokens": total_tokens,
            "token_usage_estimated": estimated,
            "accounted_tokens": accounted_tokens,
            "error_class": observation.error_class,
            "notes": (
                [f"provider_error_{observation.error_subtype}"]
                if observation.error_subtype is not None
                else []
            ),
            "scored": False,
        }
        records.append(record)
        groq_rate_limited = (
            provider == "groq" and observation.error_subtype == "http_429_rate_limit"
        )
        if (
            result.terminal_state
            in {
                TerminalState.PROVIDER_UNAVAILABLE,
                TerminalState.INVALID_MODEL_OUTPUT,
                TerminalState.INTERNAL_ERROR,
            }
            and not groq_rate_limited
        ):
            raise RuntimeError(f"{provider} warmup did not return valid output")
    return records


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _provider_metrics(
    attempts: list[dict[str, Any]], provider: ProviderName
) -> dict[str, Any]:
    items = [item for item in attempts if item["provider"] == provider]
    answerable = [item for item in items if item["category"] == "answerable_sql"]
    behavior = [item for item in items if item["category"] == "behavior"]
    completed = [item for item in answerable if item["structured_output_valid"]]
    generated = [item for item in completed if item["generated_sql"] is not None]
    stable_details: dict[str, str] = {}
    for case_id in sorted({str(item["case_id"]) for item in answerable}):
        first_two = sorted(
            [
                item
                for item in answerable
                if item["case_id"] == case_id and item["attempt"] in {1, 2}
            ],
            key=lambda item: int(item["attempt"]),
        )
        passes = sum(_attempt_succeeded(item) for item in first_two)
        if len(first_two) == 2 and passes == 2:
            outcome = "passed_both"
        elif len(first_two) == 2 and passes == 0:
            outcome = "failed_both"
        else:
            outcome = "inconsistent"
        if any(
            item["case_id"] == case_id and item["attempt"] == 3 for item in answerable
        ):
            outcome += ";targeted_third"
        stable_details[case_id] = outcome
    behavior_ids = sorted({str(item["case_id"]) for item in behavior})
    latencies = [int(item["latency_ms"]) for item in completed]
    token_totals = [
        int(item["total_tokens"])
        for item in completed
        if item["total_tokens"] is not None
    ]
    return {
        "completed_answerable_correct": sum(
            _attempt_succeeded(item) for item in completed
        ),
        "completed_answerable_total": len(completed),
        "stable_answerable_passes": sum(
            value.startswith("passed_both") for value in stable_details.values()
        ),
        "stable_answerable_total": len(stable_details),
        "stable_details": stable_details,
        "structured_output_valid_rate": _rate(
            sum(bool(item["structured_output_valid"]) for item in items), len(items)
        ),
        "sql_policy_acceptance_rate": _rate(
            sum(bool(item["sql_policy_accepted"]) for item in generated),
            len(generated),
        ),
        "policy_rejection_count": sum(
            item["error_class"] == "sql_policy_rejection" for item in answerable
        ),
        "incorrect_result_count": sum(
            item["error_class"] == "incorrect_result" for item in answerable
        ),
        "wrong_terminal_count": sum(
            item["error_class"] == "wrong_terminal_behavior" for item in answerable
        ),
        "behavior_passes": sum(
            all(
                _attempt_succeeded(item)
                for item in behavior
                if item["case_id"] == case_id
            )
            for case_id in behavior_ids
        ),
        "behavior_total": len(behavior_ids),
        "end_to_end_successes": sum(_attempt_succeeded(item) for item in items),
        "scheduled_calls": len(items),
        "http_429_count": sum(
            "provider_error_http_429_rate_limit" in item["notes"] for item in items
        ),
        "timeout_count": sum(item["error_class"] == "timeout" for item in items),
        "other_transport_error_count": sum(
            item["error_class"] == "provider_transport"
            and "provider_error_http_429_rate_limit" not in item["notes"]
            for item in items
        ),
        "latency_sample_size": len(latencies),
        "median_api_latency_ms": (
            round(statistics.median(latencies)) if latencies else None
        ),
        "p95_api_latency_ms": (
            _sample_percentile(latencies, 0.95) if latencies else None
        ),
        "minimum_api_latency_ms": min(latencies) if latencies else None,
        "maximum_api_latency_ms": max(latencies) if latencies else None,
        "median_total_tokens": (
            round(statistics.median(token_totals)) if token_totals else None
        ),
    }


def _paired_latency(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [item for item in attempts if item["category"] == "answerable_sql"]
    keys = sorted({(str(item["case_id"]), int(item["attempt"])) for item in answerable})
    pairs = []
    for key in keys:
        items = [
            item
            for item in answerable
            if (item["case_id"], item["attempt"]) == key
            and item["structured_output_valid"]
        ]
        if len(items) == 2:
            pairs.append(items)
    result: dict[str, Any] = {"sample_size": len(pairs)}
    for provider in ("openai", "groq"):
        latencies = [
            int(
                next(item for item in pair if item["provider"] == provider)[
                    "latency_ms"
                ]
            )
            for pair in pairs
        ]
        result[provider] = {
            "median_ms": round(statistics.median(latencies)) if latencies else None,
            "p95_ms": _sample_percentile(latencies, 0.95) if latencies else None,
        }
    return result


def _recommendation(metrics: dict[str, Any], paired: dict[str, Any]) -> dict[str, Any]:
    openai = metrics["openai"]
    groq = metrics["groq"]
    openai_median = paired["openai"]["median_ms"]
    groq_median = paired["groq"]["median_ms"]
    reduction = (
        round((openai_median - groq_median) / openai_median * 100, 1)
        if openai_median and groq_median is not None
        else None
    )
    quality_ok = (
        _rate(
            groq["completed_answerable_correct"],
            groq["completed_answerable_total"],
        )
        >= _rate(
            openai["completed_answerable_correct"],
            openai["completed_answerable_total"],
        )
        and groq["stable_answerable_passes"] >= openai["stable_answerable_passes"]
        and groq["structured_output_valid_rate"]
        >= openai["structured_output_valid_rate"]
        and groq["sql_policy_acceptance_rate"] >= openai["sql_policy_acceptance_rate"]
        and groq["behavior_passes"] >= openai["behavior_passes"]
    )
    reliability_ok = _rate(
        groq["end_to_end_successes"], groq["scheduled_calls"]
    ) >= _rate(openai["end_to_end_successes"], openai["scheduled_calls"])
    latency_ok = reduction is not None and reduction >= 50
    if quality_ok and reliability_ok and latency_ok:
        decision = "recommend_groq_for_review"
        reason = (
            "Groq matched or exceeded OpenAI on the frozen quality and "
            "reliability gates while reducing paired median API latency by "
            f"{reduction}%. The product default remains unchanged pending review."
        )
    elif not quality_ok or not reliability_ok:
        decision = "keep_openai"
        reason = (
            "Groq did not match OpenAI on every conservative quality or "
            "reliability gate, so latency cannot justify a switch."
        )
    else:
        decision = "inconclusive_more_data_needed"
        reason = (
            "Quality and reliability did not justify rejection, but the required "
            "latency improvement was not established."
        )
    return {
        "decision": decision,
        "reason": reason,
        "paired_median_latency_reduction_percent": reduction,
        "default_provider_changed": False,
    }


def _payload(
    *,
    status: str,
    configuration: dict[str, Any],
    warmups: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    budget: TokenBudget,
    daily_tokens_available: int,
    targeted_cases: list[str],
    monotonic_started: float,
    wall_started: datetime,
) -> dict[str, Any]:
    metrics = {
        provider: _provider_metrics(attempts, provider)
        for provider in ("openai", "groq")
    }
    paired = _paired_latency(attempts)
    total_wait_ms = sum(
        int(item["intentional_wait_ms"]) for item in [*warmups, *attempts]
    )
    return {
        "status": status,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "configuration": {
            **configuration,
            "run_type": "paired prompt version 2 comparison with paced Groq",
            "openai_baseline_reused": False,
            "pacing_seconds": PACING_SECONDS,
            "groq_limits": {
                "requests_per_minute": 30,
                "requests_per_day": 1000,
                "tokens_per_minute": 8000,
                "tokens_per_day": DAILY_TOKEN_LIMIT,
            },
            "daily_tokens_available_at_start": daily_tokens_available,
            "daily_capacity_source": "user confirmed Groq dashboard reset",
            "maximum_groq_live_calls": MAXIMUM_LIVE_CALLS,
            "maximum_groq_evaluation_tokens": MAXIMUM_EVALUATION_TOKENS,
            "groq_daily_token_reserve": TOKEN_RESERVE,
        },
        "warmups": warmups,
        "attempts": attempts,
        "metrics": metrics,
        "paired_latency": paired,
        "token_accounting": {
            "groq_actual_returned_tokens": budget.actual_tokens,
            "groq_estimated_tokens_for_missing_usage": budget.estimated_tokens,
            "groq_accounted_total_tokens": budget.accounted_tokens,
            "groq_remaining_from_confirmed_start": (
                daily_tokens_available - budget.accounted_tokens
            ),
            "estimates_present": budget.estimated_tokens > 0,
        },
        "run_counts": {
            "warmup_calls_per_provider": 1 if warmups else 0,
            "scored_calls_per_provider": len(attempts) // 2,
            "targeted_cases": targeted_cases,
            "targeted_calls_per_provider": len(targeted_cases),
            "total_live_calls": len(warmups) + len(attempts),
        },
        "timing": {
            "total_intentional_wait_minutes": round(total_wait_ms / 60_000, 3),
            "total_monotonic_active_minutes": round(
                (time.monotonic() - monotonic_started) / 60, 3
            ),
            "total_wall_clock_minutes": round(
                (datetime.now(UTC) - wall_started).total_seconds() / 60, 3
            ),
        },
        "recommendation": (
            _recommendation(metrics, paired) if status == "complete" else None
        ),
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite result report: {path.name}")
    config = payload["configuration"]
    metrics = payload["metrics"]
    paired = payload["paired_latency"]
    tokens = payload["token_accounting"]
    counts = payload["run_counts"]
    timing = payload["timing"]
    recommendation = payload["recommendation"]
    lines = [
        "# Prompt version 2 paired model comparison",
        "",
        "## Method",
        "",
        "Both models used the same prompt version 2, metadata, strict decision "
        "schema, cases, database, SQL policy, execution path, and rendering. "
        "Calls were sequential with no retries or repair. Groq request starts "
        "were at least 65 seconds apart; OpenAI calls ran within that schedule.",
        "",
        f"- source commit: `{config['source_commit']}`",
        f"- prompt SHA-256: `{config['prompt_hash']}`",
        f"- schema SHA-256: `{config['schema_hash']}`",
        f"- case set SHA-256: `{config['case_set_hash']}`",
        f"- database fingerprint: `{config['database_logical_fingerprint']}`",
        "- Groq quota: 30 RPM, 1,000 RPD, 8,000 TPM, 200,000 TPD",
        f"- Groq daily tokens confirmed at start: "
        f"{config['daily_tokens_available_at_start']:,}",
        f"- scored calls per provider: {counts['scored_calls_per_provider']}",
        f"- targeted cases: {', '.join(counts['targeted_cases']) or 'none'}",
        "",
        "## Results",
        "",
        "| metric | GPT-5 mini | Groq GPT-OSS 120B |",
        "|---|---:|---:|",
    ]
    for label, key, denominator in (
        (
            "completed answerable",
            "completed_answerable_correct",
            "completed_answerable_total",
        ),
        ("stable answerable", "stable_answerable_passes", "stable_answerable_total"),
        ("behavior", "behavior_passes", "behavior_total"),
        ("end to end", "end_to_end_successes", "scheduled_calls"),
    ):
        lines.append(
            f"| {label} | {metrics['openai'][key]}/{metrics['openai'][denominator]} "
            f"| {metrics['groq'][key]}/{metrics['groq'][denominator]} |"
        )
    lines.extend(
        [
            f"| structured output valid | "
            f"{metrics['openai']['structured_output_valid_rate']:.1%} | "
            f"{metrics['groq']['structured_output_valid_rate']:.1%} |",
            f"| SQL policy accepted | "
            f"{metrics['openai']['sql_policy_acceptance_rate']:.1%} | "
            f"{metrics['groq']['sql_policy_acceptance_rate']:.1%} |",
            "",
            "## Paired API latency",
            "",
            f"- paired answerable sample: {paired['sample_size']}",
            f"- OpenAI median / p95: {paired['openai']['median_ms']} / "
            f"{paired['openai']['p95_ms']} ms",
            f"- Groq median / p95: {paired['groq']['median_ms']} / "
            f"{paired['groq']['p95_ms']} ms",
            f"- paired median reduction: "
            f"{recommendation['paired_median_latency_reduction_percent']}%",
            "",
            "Intentional pacing wait is excluded from API latency.",
            "",
            "## Groq quota accounting",
            "",
            f"- actual returned tokens: {tokens['groq_actual_returned_tokens']:,}",
            f"- estimated missing usage: "
            f"{tokens['groq_estimated_tokens_for_missing_usage']:,}",
            f"- accounted total: {tokens['groq_accounted_total_tokens']:,}",
            f"- remaining from confirmed start: "
            f"{tokens['groq_remaining_from_confirmed_start']:,}",
            f"- intentional wait: {timing['total_intentional_wait_minutes']} minutes",
            f"- wall clock: {timing['total_wall_clock_minutes']} minutes",
            "",
            "## Stable case detail",
            "",
        ]
    )
    for case_id in sorted(metrics["openai"]["stable_details"]):
        lines.append(
            f"- `{case_id}`: OpenAI "
            f"{metrics['openai']['stable_details'][case_id]}, Groq "
            f"{metrics['groq']['stable_details'][case_id]}"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "This is a small repeated evaluation on one deterministic dataset. "
            "The quota compliant schedule measures API latency separately from "
            "throughput and does not add a product rate limiter.",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--daily-tokens-available-at-start", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        _refuse_existing_artifacts((args.json_output, args.markdown_output))
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 2
    if not (
        MINIMUM_STARTING_TOKENS
        <= args.daily_tokens_available_at_start
        <= DAILY_TOKEN_LIMIT
    ):
        print(
            "confirmed Groq capacity must be between 150000 and 200000",
            file=sys.stderr,
        )
        return 2
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not openai_key or not groq_key:
        print("OPENAI_API_KEY and GROQ_API_KEY are required", file=sys.stderr)
        return 2
    git_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=_REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if git_status:
        print("live comparison requires a clean frozen worktree", file=sys.stderr)
        return 2
    for logger_name in ("openai", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)

    manifest_raw, manifest_cases = _load_manifest()
    as_of = date.fromisoformat(manifest_raw["as_of"])
    database_path = (
        Path(tempfile.mkdtemp(prefix="bse-v2-comparison-")) / "comparison.db"
    )
    build_result = build_database(database_path)
    generators: dict[
        ProviderName, OpenAIComparisonGenerator | GroqComparisonGenerator
    ] = {
        "openai": OpenAIComparisonGenerator(api_key=openai_key),
        "groq": GroqComparisonGenerator(api_key=groq_key),
    }
    pacer = RequestPacer()
    budget = TokenBudget(available_tokens=args.daily_tokens_available_at_start)
    attempts: list[dict[str, Any]] = []
    targeted_case_ids: list[str] = []
    monotonic_started = time.monotonic()
    wall_started = datetime.now(UTC)

    with open_readonly_database(database_path) as database:
        configuration = _configuration(
            manifest_raw, build_result.logical_content_fingerprint, database
        )
        for key, expected in EXPECTED_HASHES.items():
            if configuration[key] != expected:
                print(f"frozen {key} changed; refusing live calls", file=sys.stderr)
                return 2
        if (
            configuration["database_logical_fingerprint"]
            != EXPECTED_DATABASE_FINGERPRINT
        ):
            print("database fingerprint changed; refusing live calls", file=sys.stderr)
            return 2
        warmup_case = _case_lookup()[manifest_raw["warmup_case_id"]]
        warmups = _warmup(
            database,
            generators,
            warmup_case.question,
            as_of=as_of,
            pacer=pacer,
            budget=budget,
        )
        _write_json(
            args.json_output,
            _payload(
                status="running",
                configuration=configuration,
                warmups=warmups,
                attempts=attempts,
                budget=budget,
                daily_tokens_available=args.daily_tokens_available_at_start,
                targeted_cases=targeted_case_ids,
                monotonic_started=monotonic_started,
                wall_started=wall_started,
            ),
            first_write=True,
        )
        case_indexes = {
            case.case_id: index for index, case in enumerate(manifest_cases)
        }
        for manifest_case, attempt_number in _base_schedule(manifest_cases):
            if not budget.can_start_next():
                print(
                    "local Groq token budget stopped the base schedule",
                    file=sys.stderr,
                )
                return 3
            for order, provider in enumerate(
                _provider_order(case_indexes[manifest_case.case_id], attempt_number),
                start=1,
            ):
                attempts.append(
                    _run_provider_attempt(
                        database,
                        generators,
                        provider,
                        manifest_case,
                        attempt_number=attempt_number,
                        provider_order=order,
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
                        warmups=warmups,
                        attempts=attempts,
                        budget=budget,
                        daily_tokens_available=args.daily_tokens_available_at_start,
                        targeted_cases=targeted_case_ids,
                        monotonic_started=monotonic_started,
                        wall_started=wall_started,
                    ),
                    first_write=False,
                )
        for manifest_case, attempt_number in _targeted_cases(manifest_cases, attempts):
            if not budget.can_start_next():
                break
            targeted_case_ids.append(manifest_case.case_id)
            for order, provider in enumerate(
                _provider_order(case_indexes[manifest_case.case_id], attempt_number),
                start=1,
            ):
                attempts.append(
                    _run_provider_attempt(
                        database,
                        generators,
                        provider,
                        manifest_case,
                        attempt_number=attempt_number,
                        provider_order=order,
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
                        warmups=warmups,
                        attempts=attempts,
                        budget=budget,
                        daily_tokens_available=args.daily_tokens_available_at_start,
                        targeted_cases=targeted_case_ids,
                        monotonic_started=monotonic_started,
                        wall_started=wall_started,
                    ),
                    first_write=False,
                )

    final_payload = _payload(
        status="complete",
        configuration=configuration,
        warmups=warmups,
        attempts=attempts,
        budget=budget,
        daily_tokens_available=args.daily_tokens_available_at_start,
        targeted_cases=targeted_case_ids,
        monotonic_started=monotonic_started,
        wall_started=wall_started,
    )
    _write_json(args.json_output, final_payload, first_write=False)
    _write_markdown(args.markdown_output, final_payload)
    print(
        json.dumps(
            {
                "status": "complete",
                "scored_calls_per_provider": len(attempts) // 2,
                "groq_accounted_tokens": budget.accounted_tokens,
                "recommendation": final_payload["recommendation"]["decision"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
