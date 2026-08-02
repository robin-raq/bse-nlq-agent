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

from cases import CASES, EvalCase

from bse_nlq.db.build import build_database
from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database
from bse_nlq.prompt.models import BuiltPrompt
from bse_nlq.service import QueryResult, answer_question


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


def _run_case(database: ReadOnlyDatabase, case: EvalCase, *, live: bool) -> EvalOutcome:
    if live:
        from bse_nlq.provider_openai import OpenAIRawGenerator

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        generator = OpenAIRawGenerator(api_key=api_key)
        question = case.question
    else:
        generator = _ReferenceGenerator(case.model_response)
        question = case.question

    start = time.perf_counter()
    result = answer_question(database, generator, question)
    latency = time.perf_counter() - start

    passed = result.terminal_state is case.expected_terminal_state
    if passed and case.expected_answer_contains is not None and not live:
        passed = bool(result.answer) and case.expected_answer_contains in result.answer

    return EvalOutcome(case=case, result=result, latency_seconds=latency, passed=passed)


def _print_report(outcomes: list[EvalOutcome], *, live: bool) -> None:
    mode = "LIVE (real OpenAI model)" if live else "REFERENCE (mocked, pipeline-only)"
    print(f"Evaluation mode: {mode}")
    print(
        f"{'case':<28} {'category':<14} {'expected':<22} {'actual':<22} "
        f"{'pass':<5} {'ms':>8}"
    )
    for outcome in outcomes:
        print(
            f"{outcome.case.case_id:<28} "
            f"{outcome.case.category:<14} "
            f"{outcome.case.expected_terminal_state.value:<22} "
            f"{outcome.result.terminal_state.value:<22} "
            f"{'PASS' if outcome.passed else 'FAIL':<5} "
            f"{outcome.latency_seconds * 1000:>8.1f}"
        )
    passed_count = sum(1 for outcome in outcomes if outcome.passed)
    print(f"\n{passed_count}/{len(outcomes)} passed.")
    for outcome in outcomes:
        if not outcome.passed:
            print(
                f"FAIL {outcome.case.case_id}: expected "
                f"{outcome.case.expected_terminal_state.value}, got "
                f"{outcome.result.terminal_state.value}, "
                f"answer={outcome.result.answer!r}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--live", action="store_true")
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
    return 0 if all(outcome.passed for outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
