"""Run the frozen GPT-5 mini and Groq GPT-OSS comparison.

Usage from the repository root:

    uv run python evaluation/model_comparison/compare_models.py \
      --json-output evaluation/model_comparison/results/comparison-YYYY-MM-DD.json \
      --markdown-output evaluation/model_comparison/results/comparison-YYYY-MM-DD.md

The command requires both provider keys. It makes sequential live calls with
no retries and writes only sanitized application-level evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from bse_nlq.db.build import build_database  # noqa: E402
from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database  # noqa: E402
from bse_nlq.decision import model_decision_json_schema_text  # noqa: E402
from bse_nlq.prompt import PromptInput, build_prompt  # noqa: E402
from bse_nlq.service import QueryResult, TerminalState, answer_question  # noqa: E402
from evaluation.cases import CASES, EvalCase  # noqa: E402
from evaluation.model_comparison.providers import (  # noqa: E402
    GROQ_BASE_URL,
    GROQ_MODEL,
    OPENAI_MODEL,
    REQUEST_TIMEOUT_SECONDS,
    GroqComparisonGenerator,
    OpenAIComparisonGenerator,
    ProviderObservation,
)

Category = Literal["answerable_sql", "behavior", "fault_injection"]
ProviderName = Literal["openai", "groq"]

_MANIFEST_PATH = Path(__file__).with_name("manifest.json")
_SAFE_FAILURE_CATEGORIES = frozenset(
    {
        "provider_transport",
        "timeout",
        "invalid_structured_output",
        "wrong_terminal_behavior",
        "sql_policy_rejection",
        "sql_execution",
        "incorrect_result",
        "rendering",
        "evaluation_harness",
        "unknown",
    }
)


@dataclass(frozen=True, slots=True)
class ManifestCase:
    case_id: str
    category: Category
    expected_terminal: tuple[str, ...]
    invariant: str


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    case_id: str
    category: Category
    provider: ProviderName
    model: str
    attempt: int
    provider_order: int
    expected_terminal: list[str]
    actual_terminal: str
    decision_status: str | None
    structured_output_valid: bool
    generated_sql: str | None
    sql_policy_accepted: bool
    execution_succeeded: bool
    answer_invariant_passed: bool
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    error_class: str | None
    notes: list[str]


def _load_manifest() -> tuple[dict[str, Any], tuple[ManifestCase, ...]]:
    raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = tuple(
        ManifestCase(
            case_id=item["case_id"],
            category=item["category"],
            expected_terminal=tuple(item["expected_terminal"]),
            invariant=item["invariant"],
        )
        for item in raw["cases"]
    )
    if any(case.category == "fault_injection" for case in cases):
        raise ValueError("fault_injection cases are not live eligible")
    known = {case.case_id for case in CASES}
    if {case.case_id for case in cases} - known:
        raise ValueError("comparison manifest contains an unknown evaluation case")
    return raw, cases


def _case_lookup() -> dict[str, EvalCase]:
    return {case.case_id: case for case in CASES}


def _provider_order(case_index: int, attempt: int) -> tuple[ProviderName, ProviderName]:
    if (case_index + attempt - 1) % 2 == 0:
        return ("openai", "groq")
    return ("groq", "openai")


def _run_attempt(
    database: ReadOnlyDatabase,
    generator: OpenAIComparisonGenerator | GroqComparisonGenerator,
    provider: ProviderName,
    manifest_case: ManifestCase,
    eval_case: EvalCase,
    *,
    attempt: int,
    provider_order: int,
    as_of: date,
) -> AttemptRecord:
    result = answer_question(
        database,
        generator,
        eval_case.question,
        as_of=as_of,
    )
    observation = generator.last_observation or ProviderObservation(
        latency_ms=0,
        input_tokens=None,
        output_tokens=None,
        error_class="unknown",
    )
    invariant_passed = _invariant_passed(manifest_case.invariant, result)
    expected = result.terminal_state.value in manifest_case.expected_terminal
    pipeline_passed = expected and invariant_passed
    policy_accepted = bool(result.generated_sql) and result.terminal_state not in {
        TerminalState.INVALID_SQL,
        TerminalState.QUERY_REJECTED,
    }
    execution_succeeded = result.terminal_state in {
        TerminalState.ANSWERED,
        TerminalState.ANSWERED_EMPTY,
    }
    structured_valid = result.terminal_state not in {
        TerminalState.INVALID_MODEL_OUTPUT,
        TerminalState.PROVIDER_UNAVAILABLE,
        TerminalState.INTERNAL_ERROR,
    }
    error_class = None if pipeline_passed else _failure_category(result, observation)
    notes: list[str] = []
    if result.generated_sql is not None and result.executed_sql is not None:
        if result.generated_sql != result.executed_sql:
            notes.append("generated_executed_sql_mismatch")
            invariant_passed = False
            error_class = "evaluation_harness"
    return AttemptRecord(
        case_id=manifest_case.case_id,
        category=manifest_case.category,
        provider=provider,
        model=OPENAI_MODEL if provider == "openai" else GROQ_MODEL,
        attempt=attempt,
        provider_order=provider_order,
        expected_terminal=list(manifest_case.expected_terminal),
        actual_terminal=result.terminal_state.value,
        decision_status=_decision_status(result),
        structured_output_valid=structured_valid,
        generated_sql=result.generated_sql,
        sql_policy_accepted=policy_accepted,
        execution_succeeded=execution_succeeded,
        answer_invariant_passed=invariant_passed,
        latency_ms=observation.latency_ms,
        input_tokens=observation.input_tokens,
        output_tokens=observation.output_tokens,
        error_class=error_class,
        notes=notes,
    )


def _decision_status(result: QueryResult) -> str | None:
    if result.terminal_state is TerminalState.CLARIFICATION_REQUIRED:
        return "clarification_required"
    if result.terminal_state is TerminalState.UNSUPPORTED:
        return "unsupported"
    if result.generated_sql is not None:
        return "sql_generated"
    return None


def _failure_category(result: QueryResult, observation: ProviderObservation) -> str:
    if observation.error_class in {"provider_transport", "timeout"}:
        return observation.error_class
    if result.terminal_state is TerminalState.INVALID_MODEL_OUTPUT:
        return "invalid_structured_output"
    if result.terminal_state in {
        TerminalState.QUERY_REJECTED,
        TerminalState.INVALID_SQL,
    }:
        return "sql_policy_rejection"
    if result.terminal_state in {
        TerminalState.EXECUTION_ERROR,
        TerminalState.EXECUTION_LIMIT_EXCEEDED,
    }:
        return "sql_execution"
    if result.terminal_state in {TerminalState.ANSWERED, TerminalState.ANSWERED_EMPTY}:
        return "incorrect_result"
    if result.terminal_state in {
        TerminalState.CLARIFICATION_REQUIRED,
        TerminalState.UNSUPPORTED,
    }:
        return "wrong_terminal_behavior"
    return "unknown"


def _invariant_passed(invariant: str, result: QueryResult) -> bool:
    raw = result.raw_result
    scalar_values = {
        "scalar_4": 4,
        "scalar_957": 957,
        "scalar_7597": 7597,
        "scalar_300": 300,
        "scalar_7270000": 7_270_000,
        "scalar_1400000": 1_400_000,
    }
    if invariant in scalar_values:
        return raw is not None and raw.rows == ((scalar_values[invariant],),)
    if invariant == "top_event_gross":
        if raw is None or len(raw.rows) != 1:
            return False
        has_name = "Marsh Hollow Family Field Day" in raw.rows[0]
        disclosed = any(
            "gross" in column.lower() and "revenue" in column.lower()
            for column in raw.columns
        )
        return has_name and disclosed
    if invariant == "top_venue_net":
        return (
            raw is not None
            and len(raw.rows) == 1
            and "Kings Harbor Arena" in raw.rows[0]
        )
    if invariant == "clarifies_metric_period_baseline":
        text = (result.message or "").lower()
        metric = any(word in text for word in ("metric", "revenue", "tickets"))
        period = any(word in text for word in ("period", "time", "date", "range"))
        baseline = any(
            word in text for word in ("baseline", "comparison", "compare", "against")
        )
        return (
            result.terminal_state is TerminalState.CLARIFICATION_REQUIRED
            and metric
            and period
            and baseline
        )
    if invariant == "refuses_current_time":
        text = (result.message or "").lower()
        return result.terminal_state is TerminalState.UNSUPPORTED and (
            "time" in text or "current" in text
        )
    if invariant == "nothing_executed":
        return result.executed_sql is None and result.raw_result is None
    if invariant == "empty_answer":
        return (
            result.terminal_state is TerminalState.ANSWERED_EMPTY
            and raw is not None
            and raw.rows == ()
            and result.answer == "No results found."
        )
    raise ValueError(f"unknown comparison invariant: {invariant}")


def _attempt_passed(attempt: AttemptRecord) -> bool:
    return attempt.error_class is None


def _provider_metrics(
    attempts: list[AttemptRecord], provider: ProviderName, answerable_count: int
) -> dict[str, Any]:
    provider_attempts = [item for item in attempts if item.provider == provider]
    answerable = [
        item for item in provider_attempts if item.category == "answerable_sql"
    ]
    behavior = [item for item in provider_attempts if item.category == "behavior"]
    first = [item for item in answerable if item.attempt == 1]
    stable_count = sum(
        1
        for case_id in {item.case_id for item in answerable}
        if len([item for item in answerable if item.case_id == case_id]) == 3
        and all(_attempt_passed(item) for item in answerable if item.case_id == case_id)
    )
    behavior_case_ids = {item.case_id for item in behavior}
    behavior_pass_count = sum(
        1
        for case_id in behavior_case_ids
        if all(_attempt_passed(item) for item in behavior if item.case_id == case_id)
    )
    latencies = [item.latency_ms for item in answerable]
    inputs = [item.input_tokens for item in answerable if item.input_tokens is not None]
    outputs = [
        item.output_tokens for item in answerable if item.output_tokens is not None
    ]
    total = len(answerable)
    first_passes = sum(_attempt_passed(item) for item in first)
    return {
        "first_attempt_answerable": f"{first_passes}/{answerable_count}",
        "stable_answerable": f"{stable_count}/{answerable_count}",
        "correct_attempts": f"{sum(_attempt_passed(i) for i in answerable)}/{total}",
        "structured_output_valid_rate": _rate(
            sum(item.structured_output_valid for item in answerable), total
        ),
        "policy_acceptance_rate": _rate(
            sum(item.sql_policy_accepted for item in answerable), total
        ),
        "execution_success_rate": _rate(
            sum(item.execution_succeeded for item in answerable), total
        ),
        "answer_invariant_pass_rate": _rate(
            sum(item.answer_invariant_passed for item in answerable), total
        ),
        "behavior_passes": f"{behavior_pass_count}/{len(behavior_case_ids)}",
        "median_latency_ms": round(statistics.median(latencies)) if latencies else 0,
        "p95_latency_ms": _sample_percentile(latencies, 0.95),
        "minimum_latency_ms": min(latencies) if latencies else 0,
        "maximum_latency_ms": max(latencies) if latencies else 0,
        "median_input_tokens": round(statistics.median(inputs)) if inputs else None,
        "median_output_tokens": round(statistics.median(outputs)) if outputs else None,
    }


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _sample_percentile(values: list[int], quantile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def _disagreements(attempts: list[AttemptRecord]) -> list[dict[str, str]]:
    disagreements: list[dict[str, str]] = []
    case_attempts = {(item.case_id, item.attempt) for item in attempts}
    for case_id, attempt_number in sorted(case_attempts):
        paired = [
            item
            for item in attempts
            if item.case_id == case_id and item.attempt == attempt_number
        ]
        if len(paired) != 2:
            continue
        openai = next(item for item in paired if item.provider == "openai")
        groq = next(item for item in paired if item.provider == "groq")
        openai_outcome = (
            f"{openai.actual_terminal}:{'pass' if _attempt_passed(openai) else 'fail'}"
        )
        groq_outcome = (
            f"{groq.actual_terminal}:{'pass' if _attempt_passed(groq) else 'fail'}"
        )
        if openai_outcome != groq_outcome:
            disagreements.append(
                {
                    "case_id": case_id,
                    "openai_outcome": openai_outcome,
                    "groq_outcome": groq_outcome,
                    "assessment": f"attempt {attempt_number} outcomes differed",
                }
            )
    return disagreements


def _recommendation(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    openai = metrics["openai"]
    groq = metrics["groq"]
    openai_median = openai["median_latency_ms"]
    groq_median = groq["median_latency_ms"]
    reduction = (
        round((openai_median - groq_median) / openai_median * 100, 1)
        if openai_median
        else None
    )
    equal_first = openai["first_attempt_answerable"] == groq["first_attempt_answerable"]
    equal_stable = openai["stable_answerable"] == groq["stable_answerable"]
    reliability_ok = (
        groq["structured_output_valid_rate"] >= openai["structured_output_valid_rate"]
        and groq["policy_acceptance_rate"] >= openai["policy_acceptance_rate"]
        and groq["behavior_passes"] == openai["behavior_passes"]
    )
    latency_ok = reduction is not None and reduction >= 50
    p95_ok = groq["p95_latency_ms"] < openai["p95_latency_ms"]
    if equal_first and equal_stable and reliability_ok and latency_ok and p95_ok:
        decision = "recommend_groq_for_review"
        reason = (
            "Groq matched GPT-5 mini on answerable and behavioral reliability "
            f"and reduced median latency by {reduction}%. The product default "
            "remains unchanged."
        )
    elif not equal_first or not equal_stable or not reliability_ok:
        decision = "keep_openai"
        reason = (
            "Groq did not match GPT-5 mini on the conservative correctness or "
            "reliability gates, so latency cannot justify a switch."
        )
    else:
        decision = "inconclusive_more_data_needed"
        reason = (
            "Correctness did not justify rejection, but the required median and "
            "p95 latency improvement was not established in this small sample."
        )
    return {
        "decision": decision,
        "reason": reason,
        "latency_reduction_percent": reduction,
        "default_provider_changed": False,
    }


def _configuration(
    manifest_raw: dict[str, Any], database_fingerprint: str, database: ReadOnlyDatabase
) -> dict[str, Any]:
    cases_by_id = _case_lookup()
    warmup = cases_by_id[manifest_raw["warmup_case_id"]]
    as_of = date.fromisoformat(manifest_raw["as_of"])
    prompt = build_prompt(
        PromptInput(
            question=warmup.question,
            metadata=database.metadata,
            connection=database._connection,
            as_of=as_of,
        )
    )
    canonical_manifest = json.dumps(
        manifest_raw["cases"], sort_keys=True, separators=(",", ":")
    ).encode()
    return {
        "source_commit": _git("rev-parse", "HEAD"),
        "python_version": platform.python_version(),
        "uv_version": _command_version("uv", "--version"),
        "as_of": manifest_raw["as_of"],
        "prompt_hash": _sha256(prompt.canonical_bytes()),
        "prompt_hash_scope": "full warm-up prompt for case count",
        "schema_hash": _sha256(model_decision_json_schema_text().encode()),
        "database_logical_fingerprint": database_fingerprint,
        "case_set_hash": _sha256(canonical_manifest),
        "warmup_excluded": True,
        "p95_method": "nearest-rank sample percentile",
        "models": {
            "openai": {
                "provider": "OpenAI",
                "model": OPENAI_MODEL,
                "settings": {
                    "api": "Responses",
                    "strict_json_schema": True,
                    "temperature": "omitted (unsupported for this path)",
                    "max_retries": 0,
                    "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
                },
            },
            "groq": {
                "provider": "Groq",
                "model": GROQ_MODEL,
                "settings": {
                    "api": "OpenAI-compatible Chat Completions",
                    "base_url": GROQ_BASE_URL,
                    "strict_json_schema": True,
                    "temperature": 0,
                    "max_retries": 0,
                    "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
                },
            },
        },
    }


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=_REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _command_version(*args: str) -> str:
    return subprocess.run(
        list(args), check=True, capture_output=True, text=True
    ).stdout.strip()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, payload: dict[str, Any], *, first_write: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if first_write:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _report_payload(
    configuration: dict[str, Any],
    attempts: list[AttemptRecord],
    manifest_cases: tuple[ManifestCase, ...],
    *,
    status: str,
) -> dict[str, Any]:
    serialized_attempts = [asdict(item) for item in attempts]
    answerable_count = sum(case.category == "answerable_sql" for case in manifest_cases)
    metrics = {
        provider: _provider_metrics(attempts, provider, answerable_count)
        for provider in ("openai", "groq")
    }
    failures = [
        {
            "provider": item.provider,
            "case_id": item.case_id,
            "attempt": item.attempt,
            "category": item.error_class,
            "summary": "sanitized comparison failure",
        }
        for item in attempts
        if item.error_class is not None
    ]
    assert all(item["category"] in _SAFE_FAILURE_CATEGORIES for item in failures)
    return {
        "status": status,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "configuration": configuration,
        "attempts": serialized_attempts,
        "metrics": metrics,
        "disagreements": _disagreements(attempts),
        "failures": failures,
        "recommendation": _recommendation(metrics) if status == "complete" else None,
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite result report: {path.name}")
    configuration = payload["configuration"]
    metrics = payload["metrics"]
    lines = [
        "# GPT-5 mini and Groq GPT-OSS 120B comparison",
        "",
        "## Objective",
        "",
        "Compare correctness, safe behavior, structured output reliability, "
        "and provider request latency without changing the product default.",
        "",
        "## Frozen experiment configuration",
        "",
        f"- source commit: `{configuration['source_commit']}`",
        f"- Python: `{configuration['python_version']}`",
        f"- uv: `{configuration['uv_version']}`",
        f"- prompt SHA-256: `{configuration['prompt_hash']}`",
        f"- schema SHA-256: `{configuration['schema_hash']}`",
        "- database logical SHA-256: "
        f"`{configuration['database_logical_fingerprint']}`",
        f"- case set SHA-256: `{configuration['case_set_hash']}`",
        "- one excluded warm-up per provider, one semantic generation per "
        "attempt, no retries, no repair",
        "- provider calls were sequential and provider order alternated by "
        "case and attempt",
        "",
        "## Case taxonomy",
        "",
        "Eight answerable SQL cases were each run three times per provider. "
        "Four behavioral cases were run once, with two extra attempts only "
        "when the first pair disagreed or differed from the expected behavior. "
        "The malformed-output fault injection remained offline and did not "
        "enter live percentages.",
        "",
        "## Aggregate results",
        "",
        "| provider | first attempt | stable cases | correct attempts | "
        "structured valid | policy accepted | behavior |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for provider in ("openai", "groq"):
        item = metrics[provider]
        aggregate_row = (
            f"| {provider} | {item['first_attempt_answerable']} | "
            f"{item['stable_answerable']} | {item['correct_attempts']} | "
            f"{item['structured_output_valid_rate']:.1%} | "
            f"{item['policy_acceptance_rate']:.1%} | "
            f"{item['behavior_passes']} |"
        )
        lines.append(aggregate_row)
    lines.extend(["", "## Per-case disagreements", ""])
    if payload["disagreements"]:
        for item in payload["disagreements"]:
            lines.append(
                f"- `{item['case_id']}`: OpenAI `{item['openai_outcome']}`, "
                f"Groq `{item['groq_outcome']}` ({item['assessment']})."
            )
    else:
        lines.append("None.")
    lines.extend(["", "## Failure classification", ""])
    if payload["failures"]:
        for item in payload["failures"]:
            lines.append(
                f"- {item['provider']} `{item['case_id']}` attempt "
                f"{item['attempt']}: `{item['category']}`."
            )
    else:
        lines.append("No failed attempts.")
    lines.extend(
        [
            "",
            "## Latency comparison",
            "",
            "| provider | median ms | p95 ms | min ms | max ms |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for provider in ("openai", "groq"):
        item = metrics[provider]
        lines.append(
            f"| {provider} | {item['median_latency_ms']} | "
            f"{item['p95_latency_ms']} | {item['minimum_latency_ms']} | "
            f"{item['maximum_latency_ms']} |"
        )
    lines.extend(
        [
            "",
            "The p95 is the nearest-rank sample percentile over all answerable "
            "provider requests. Warm-ups are excluded.",
            "",
            "## Token comparison",
            "",
            "| provider | median input tokens | median output tokens |",
            "|---|---:|---:|",
        ]
    )
    for provider in ("openai", "groq"):
        item = metrics[provider]
        lines.append(
            f"| {provider} | {item['median_input_tokens']} | "
            f"{item['median_output_tokens']} |"
        )
    recommendation = payload["recommendation"]
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "This is a deliberately small paired experiment on one "
            "deterministic dataset and one machine. It supports a review "
            "recommendation, not a claim of statistical significance or an "
            "automatic product switch. GPT-5 mini Responses omits temperature "
            "while Groq uses temperature 0 because the provider controls are "
            "not identical.",
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


def _warmup(
    database: ReadOnlyDatabase,
    generators: dict[ProviderName, OpenAIComparisonGenerator | GroqComparisonGenerator],
    warmup_case: EvalCase,
    as_of: date,
) -> None:
    for provider in ("openai", "groq"):
        result = answer_question(
            database, generators[provider], warmup_case.question, as_of=as_of
        )
        if result.terminal_state is TerminalState.PROVIDER_UNAVAILABLE:
            raise RuntimeError(f"{provider} warm-up was unavailable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.json_output.exists() or args.markdown_output.exists():
        print("refusing to overwrite an existing comparison artifact", file=sys.stderr)
        return 2
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not openai_key or not groq_key:
        print("both OPENAI_API_KEY and GROQ_API_KEY are required", file=sys.stderr)
        return 2
    if _git("status", "--porcelain"):
        print("live comparison requires a clean frozen worktree", file=sys.stderr)
        return 2
    for logger_name in ("openai", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)

    manifest_raw, manifest_cases = _load_manifest()
    as_of = date.fromisoformat(manifest_raw["as_of"])
    cases_by_id = _case_lookup()
    if args.db is None:
        database_path = (
            Path(tempfile.mkdtemp(prefix="bse-model-comparison-")) / "comparison.db"
        )
        build_result = build_database(database_path)
        database_fingerprint = build_result.logical_content_fingerprint
    else:
        database_path = args.db
        with open_readonly_database(database_path) as fingerprint_database:
            from bse_nlq.db.artifact import compute_logical_content_fingerprint

            database_fingerprint = compute_logical_content_fingerprint(
                fingerprint_database._connection
            )

    generators: dict[
        ProviderName, OpenAIComparisonGenerator | GroqComparisonGenerator
    ] = {
        "openai": OpenAIComparisonGenerator(api_key=openai_key),
        "groq": GroqComparisonGenerator(api_key=groq_key),
    }
    attempts: list[AttemptRecord] = []
    with open_readonly_database(database_path) as database:
        configuration = _configuration(manifest_raw, database_fingerprint, database)
        warmup_case = cases_by_id[manifest_raw["warmup_case_id"]]
        _warmup(database, generators, warmup_case, as_of)

        payload = _report_payload(
            configuration, attempts, manifest_cases, status="running"
        )
        _write_json(args.json_output, payload, first_write=True)

        for case_index, manifest_case in enumerate(manifest_cases):
            eval_case = cases_by_id[manifest_case.case_id]
            for order, provider in enumerate(_provider_order(case_index, 1), start=1):
                attempts.append(
                    _run_attempt(
                        database,
                        generators[provider],
                        provider,
                        manifest_case,
                        eval_case,
                        attempt=1,
                        provider_order=order,
                        as_of=as_of,
                    )
                )
                _write_json(
                    args.json_output,
                    _report_payload(
                        configuration, attempts, manifest_cases, status="running"
                    ),
                    first_write=False,
                )

        for case_index, manifest_case in enumerate(manifest_cases):
            if manifest_case.category != "answerable_sql":
                continue
            eval_case = cases_by_id[manifest_case.case_id]
            for attempt_number in (2, 3):
                for order, provider in enumerate(
                    _provider_order(case_index, attempt_number), start=1
                ):
                    attempts.append(
                        _run_attempt(
                            database,
                            generators[provider],
                            provider,
                            manifest_case,
                            eval_case,
                            attempt=attempt_number,
                            provider_order=order,
                            as_of=as_of,
                        )
                    )
                    _write_json(
                        args.json_output,
                        _report_payload(
                            configuration, attempts, manifest_cases, status="running"
                        ),
                        first_write=False,
                    )

        for case_index, manifest_case in enumerate(manifest_cases):
            if manifest_case.category != "behavior":
                continue
            first_pair = [
                item
                for item in attempts
                if item.case_id == manifest_case.case_id and item.attempt == 1
            ]
            disputed = (
                len(first_pair) != 2
                or any(not _attempt_passed(item) for item in first_pair)
                or len({item.actual_terminal for item in first_pair}) > 1
            )
            if not disputed:
                continue
            eval_case = cases_by_id[manifest_case.case_id]
            for attempt_number in (2, 3):
                for order, provider in enumerate(
                    _provider_order(case_index, attempt_number), start=1
                ):
                    attempts.append(
                        _run_attempt(
                            database,
                            generators[provider],
                            provider,
                            manifest_case,
                            eval_case,
                            attempt=attempt_number,
                            provider_order=order,
                            as_of=as_of,
                        )
                    )
                    _write_json(
                        args.json_output,
                        _report_payload(
                            configuration, attempts, manifest_cases, status="running"
                        ),
                        first_write=False,
                    )

    final_payload = _report_payload(
        configuration, attempts, manifest_cases, status="complete"
    )
    _write_json(args.json_output, final_payload, first_write=False)
    _write_markdown(args.markdown_output, final_payload)
    print(
        json.dumps(
            {
                "status": "complete",
                "json_output": args.json_output.name,
                "markdown_output": args.markdown_output.name,
                "recommendation": final_payload["recommendation"]["decision"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
