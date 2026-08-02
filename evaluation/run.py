"""Run the compact evaluation set against the real end-to-end flow.

Usage:
    uv run python evaluation/run.py [--db PATH] [--live]

Default mode uses a fake generator that returns each case's reference
model response verbatim, evaluating the real SQL policy, execution
boundary, and rendering — not the model's own SQL-writing ability.
``--live`` instead sends each question to the real OpenAI adapter and
evaluates the model's actual answer; it requires ``OPENAI_API_KEY`` and
network access.

A fresh temporary seeded database is built for the run unless ``--db``
names an existing one. Not part of the shipped package and not
pytest-discovered; this is a separate explicit command, per this
project's offline-test invariant.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from cases import CASES, EvalCase, Tier

from bse_nlq.db.build import build_database
from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database
from bse_nlq.prompt.models import BuiltPrompt
from bse_nlq.service import QueryResult, TerminalState, answer_question

_REJECTED_STATES = frozenset({TerminalState.INVALID_SQL, TerminalState.QUERY_REJECTED})

_TIER_LABELS: dict[Tier, str] = {
    Tier.ANSWERABLE: "Answerable SQL questions",
    Tier.BEHAVIORAL: "Behavioral cases",
    Tier.FAULT_INJECTION: "Synthetic fault-injection cases",
}


class _ReferenceGenerator:
    """Returns one case's canned reference response verbatim."""

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, prompt: BuiltPrompt) -> str:
        return self._response


@dataclass(frozen=True, slots=True)
class EvalOutcome:
    case: EvalCase
    result: QueryResult
    latency_seconds: float
    passed: bool
    provider: str
    model: str
    # False only for a FAULT_INJECTION-tier case run in --live mode: a live
    # model is not expected to deliberately misbehave, so this is recorded
    # but excluded from tier pass/fail tallies, not scored as a failure.
    applicable: bool = True


def _validation_result(result: QueryResult) -> str:
    if result.terminal_state in _REJECTED_STATES:
        return f"rejected ({result.terminal_state.value})"
    if result.generated_sql is not None:
        return "passed"
    return "not applicable (no SQL generated)"


def _execution_result(result: QueryResult) -> str:
    if result.terminal_state is TerminalState.ANSWERED:
        row_count = (
            len(result.raw_result.rows) if result.raw_result is not None else "?"
        )
        return f"executed successfully ({row_count} row(s))"
    if result.terminal_state is TerminalState.ANSWERED_EMPTY:
        return "executed successfully (0 rows)"
    if result.terminal_state in (
        TerminalState.EXECUTION_LIMIT_EXCEEDED,
        TerminalState.EXECUTION_ERROR,
    ):
        return f"execution failed ({result.terminal_state.value})"
    return "not applicable (not executed)"


def _rendered_answer_invariant(result: QueryResult) -> str:
    if result.terminal_state in (TerminalState.ANSWERED, TerminalState.ANSWERED_EMPTY):
        return result.answer or ""
    if result.terminal_state is TerminalState.CLARIFICATION_REQUIRED:
        return f"clarification text present: {bool(result.message)}"
    if result.terminal_state is TerminalState.UNSUPPORTED:
        return f"explanation text present: {bool(result.message)}"
    return "n/a"


def _run_case(database: ReadOnlyDatabase, case: EvalCase, *, live: bool) -> EvalOutcome:
    if live:
        from bse_nlq.provider_openai import DEFAULT_MODEL, OpenAIRawGenerator

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        generator = OpenAIRawGenerator(api_key=api_key)
        provider, model = "openai", DEFAULT_MODEL
    else:
        generator = _ReferenceGenerator(case.model_response)
        provider, model = "reference (mocked)", "n/a"

    start = time.perf_counter()
    result = answer_question(database, generator, case.question)
    latency = time.perf_counter() - start

    acceptable_states = {case.expected_terminal_state}
    if live:
        acceptable_states |= case.acceptable_live_states
    passed = result.terminal_state in acceptable_states
    if passed and case.expected_answer_contains is not None and not live:
        passed = bool(result.answer) and case.expected_answer_contains in result.answer

    applicable = not (live and case.tier is Tier.FAULT_INJECTION)

    return EvalOutcome(
        case=case,
        result=result,
        latency_seconds=latency,
        passed=passed,
        provider=provider,
        model=model,
        applicable=applicable,
    )


def _tier_outcomes(outcomes: list[EvalOutcome], tier: Tier) -> list[EvalOutcome]:
    return [outcome for outcome in outcomes if outcome.case.tier is tier]


def _print_report(outcomes: list[EvalOutcome], *, live: bool) -> None:
    mode = "LIVE (real OpenAI model)" if live else "REFERENCE (mocked, pipeline-only)"
    print(f"Evaluation mode: {mode}")
    print(
        f"{'case':<28} {'tier':<11} {'expected':<22} {'actual':<22} "
        f"{'pass':<5} {'ms':>8}"
    )
    for outcome in outcomes:
        status = (
            "N/A" if not outcome.applicable else ("PASS" if outcome.passed else "FAIL")
        )
        print(
            f"{outcome.case.case_id:<28} "
            f"{outcome.case.tier.value:<11} "
            f"{outcome.case.expected_terminal_state.value:<22} "
            f"{outcome.result.terminal_state.value:<22} "
            f"{status:<5} "
            f"{outcome.latency_seconds * 1000:>8.1f}"
        )
    print()
    for tier in Tier:
        tier_outcomes = [o for o in _tier_outcomes(outcomes, tier) if o.applicable]
        if not tier_outcomes:
            skipped = len(_tier_outcomes(outcomes, tier))
            if skipped:
                print(f"{_TIER_LABELS[tier]}: {skipped} recorded, not scored live.")
            continue
        passed_count = sum(1 for outcome in tier_outcomes if outcome.passed)
        print(f"{_TIER_LABELS[tier]}: {passed_count}/{len(tier_outcomes)} passed.")
    for outcome in outcomes:
        if outcome.applicable and not outcome.passed:
            print(
                f"FAIL {outcome.case.case_id}: expected "
                f"{outcome.case.expected_terminal_state.value}, got "
                f"{outcome.result.terminal_state.value}, "
                f"answer={outcome.result.answer!r}"
            )


def _write_markdown_report(
    outcomes: list[EvalOutcome], *, path: Path, live: bool
) -> None:
    mode = "LIVE (real OpenAI model)" if live else "REFERENCE (mocked, pipeline-only)"
    lines = [
        "# Evaluation Run",
        "",
        f"Mode: {mode}",
        "",
    ]
    for tier in Tier:
        tier_outcomes = [o for o in _tier_outcomes(outcomes, tier) if o.applicable]
        if not tier_outcomes:
            skipped = len(_tier_outcomes(outcomes, tier))
            if skipped:
                lines.append(
                    f"- {_TIER_LABELS[tier]}: {skipped} recorded, not scored live."
                )
            continue
        passed_count = sum(1 for outcome in tier_outcomes if outcome.passed)
        lines.append(
            f"- {_TIER_LABELS[tier]}: {passed_count}/{len(tier_outcomes)} passed"
        )
    lines.append("")
    lines.append(
        "| case | tier | question | expected | actual | pass | provider/model | "
        "validation | execution | latency (ms) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for outcome in outcomes:
        result = outcome.result
        status = (
            "N/A" if not outcome.applicable else ("PASS" if outcome.passed else "FAIL")
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    outcome.case.case_id,
                    outcome.case.tier.value,
                    outcome.case.question.replace("|", "\\|"),
                    outcome.case.expected_terminal_state.value,
                    result.terminal_state.value,
                    status,
                    f"{outcome.provider}/{outcome.model}",
                    _validation_result(result),
                    _execution_result(result),
                    f"{outcome.latency_seconds * 1000:.1f}",
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("## Per-case detail")
    for outcome in outcomes:
        result = outcome.result
        lines.append("")
        lines.append(f"### {outcome.case.case_id}")
        lines.append(f"- tier: {outcome.case.tier.value}")
        lines.append(f"- question: {outcome.case.question}")
        lines.append(
            f"- expected terminal state: {outcome.case.expected_terminal_state.value}"
        )
        lines.append(f"- actual terminal state: {result.terminal_state.value}")
        status = (
            "N/A (not scored live)"
            if not outcome.applicable
            else ("PASS" if outcome.passed else "FAIL")
        )
        lines.append(f"- pass/fail: {status}")
        lines.append(f"- provider/model: {outcome.provider}/{outcome.model}")
        lines.append(f"- latency: {outcome.latency_seconds * 1000:.1f} ms")
        lines.append(f"- generated SQL: {result.generated_sql or 'none'}")
        lines.append(f"- validation result: {_validation_result(result)}")
        lines.append(f"- execution result: {_execution_result(result)}")
        lines.append(
            f"- rendered-answer invariant: {_rendered_answer_invariant(result)}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.live and not os.environ.get("OPENAI_API_KEY", "").strip():
        print("--live requires OPENAI_API_KEY to be set.", file=sys.stderr)
        return 2

    if args.db is not None:
        database_path = args.db
    else:
        database_path = Path(tempfile.mkdtemp()) / "eval.db"
        build_database(database_path)

    with open_readonly_database(database_path) as database:
        outcomes = [_run_case(database, case, live=args.live) for case in CASES]

    _print_report(outcomes, live=args.live)

    report_path = args.report
    if report_path is None and args.live:
        report_path = Path(__file__).resolve().parent / "results_live.md"
    if report_path is not None:
        _write_markdown_report(outcomes, path=report_path, live=args.live)
        print(f"\nReport written to {report_path}")

    return 0 if all(o.passed for o in outcomes if o.applicable) else 1


if __name__ == "__main__":
    raise SystemExit(main())
