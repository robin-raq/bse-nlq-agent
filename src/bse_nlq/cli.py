"""``bse-nlq`` CLI: a thin wrapper around QueryService.

    bse-nlq ask "Which events generated the most revenue?"
    bse-nlq ask   # interactive: pick an example or type your own

The CLI owns argument parsing, database-path resolution, provider wiring,
and terminal-output rendering only; all orchestration is QueryService's
(D-008: CLI only, one service for every mode). Does not log API keys, full
prompts, raw provider responses, questions, raw SQL, or query rows by
default; the generated/executed SQL is deliberate user-facing output, shown
because the product asks for transparency, not a diagnostic.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from bse_nlq.db.errors import DatabaseRuntimeError
from bse_nlq.db.runtime import open_readonly_database
from bse_nlq.provider_openai import OpenAIRawGenerator
from bse_nlq.service import QueryResult, TerminalState, answer_question

_DEFAULT_DB_PATH = Path("bse_nlq.db")

_SUCCESS_STATES = frozenset({TerminalState.ANSWERED, TerminalState.ANSWERED_EMPTY})

# Curated reviewer happy-path examples (PRD + evaluation answerable cases).
EXAMPLE_QUESTIONS: tuple[str, ...] = (
    "Show me the top 5 event categories by total revenue.",
    "How many events are still scheduled?",
    "How many tickets have been sold in total?",
    "What is the average ticket price?",
    "Which event generated the most revenue?",
    "How many tickets were sold for events at Ironworks Music Hall?",
    "What is our total gross ticket revenue?",
    "How much gross revenue came from events in February 2026?",
)

_MESSAGES: dict[TerminalState, str] = {
    TerminalState.INVALID_MODEL_OUTPUT: (
        "The model returned a response the application could not use."
    ),
    TerminalState.QUERY_REJECTED: (
        "The application blocked this query before execution."
    ),
    TerminalState.INVALID_SQL: "The generated SQL could not be parsed.",
    TerminalState.EXECUTION_LIMIT_EXCEEDED: (
        "The application stopped this query for exceeding its execution budget."
    ),
    TerminalState.EXECUTION_ERROR: "The query could not be executed.",
    TerminalState.PROVIDER_UNAVAILABLE: (
        "The model provider is currently unavailable. Please try again."
    ),
    TerminalState.INTERNAL_ERROR: "An internal error occurred.",
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bse-nlq")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask = subparsers.add_parser(
        "ask",
        help=(
            "Ask a plain-English question about the ticketing data. "
            "Omit the question to pick from examples or type your own."
        ),
    )
    ask.add_argument(
        "question",
        nargs="?",
        default=None,
        help="Question to answer. Omit for the interactive example menu.",
    )
    ask.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to the SQLite database ($BSE_NLQ_DB, else ./bse_nlq.db).",
    )
    return parser


def render_cli_output(result: QueryResult) -> str:
    """Deterministic terminal rendering for one QueryResult."""
    lines: list[str] = []
    if result.terminal_state in _SUCCESS_STATES:
        lines.append(result.answer or "")
    elif result.terminal_state is TerminalState.CLARIFICATION_REQUIRED:
        lines.append(f"Clarification needed: {result.message}")
    elif result.terminal_state is TerminalState.UNSUPPORTED:
        lines.append(f"Unsupported question: {result.message}")
    else:
        lines.append(_MESSAGES[result.terminal_state])

    if result.executed_sql is not None:
        lines.append("")
        lines.append("Executed SQL:")
        lines.append(result.executed_sql)
    elif result.generated_sql is not None:
        lines.append("")
        lines.append("Generated SQL — not executed:")
        lines.append(result.generated_sql)
    return "\n".join(lines)


def _resolve_database_path(cli_value: Path | None) -> Path:
    if cli_value is not None:
        return cli_value
    env_value = os.environ.get("BSE_NLQ_DB", "").strip()
    return Path(env_value) if env_value else _DEFAULT_DB_PATH


def _require_api_key() -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        return api_key
    print(
        "OPENAI_API_KEY is not set. See README.md for setup.",
        file=sys.stderr,
    )
    print(
        "Without a key, you can still run the offline demo: "
        "uv run python evaluation/run.py",
        file=sys.stderr,
    )
    return None


def _ask_once(
    *,
    database_path: Path,
    api_key: str,
    question: str,
) -> tuple[int, QueryResult | None]:
    try:
        with open_readonly_database(database_path) as database:
            generator = OpenAIRawGenerator(api_key=api_key)
            result = answer_question(database, generator, question)
    except DatabaseRuntimeError as error:
        print(f"Could not open database: {error}", file=sys.stderr)
        return 2, None

    print(render_cli_output(result))
    return (0 if result.terminal_state in _SUCCESS_STATES else 1), result


def _prompt_menu(examples: tuple[str, ...]) -> str | None:
    """Return a question, or None when the user quits."""
    print()
    print("BSE NLQ — pick an example or type your own")
    print()
    for index, question in enumerate(examples, start=1):
        print(f"  {index}. {question}")
    print("  0. Type your own question")
    print("  q. Quit")
    print()

    while True:
        choice = input("Choice: ").strip()
        if choice.lower() in {"q", "quit", "exit"}:
            return None
        if choice == "0":
            custom = input("Your question: ").strip()
            if custom:
                return custom
            print("Empty question; try again or choose q to quit.")
            continue
        if choice.isdigit():
            number = int(choice)
            if 1 <= number <= len(examples):
                return examples[number - 1]
        print(f"Enter 1-{len(examples)}, 0 for a custom question, or q to quit.")


def run_interactive(
    *,
    database_path: Path,
    api_key: str,
    examples: tuple[str, ...] = EXAMPLE_QUESTIONS,
) -> int:
    """Menu loop: choose an example, type a custom question, or quit."""
    print(f"Database: {database_path}")
    print("Each turn makes one live model call. Press q at the menu to exit.")
    exit_code = 0
    while True:
        question = _prompt_menu(examples)
        if question is None:
            return exit_code
        print()
        print(f"> {question}")
        print()
        code, _ = _ask_once(
            database_path=database_path,
            api_key=api_key,
            question=question,
        )
        if code == 2:
            return 2
        exit_code = code


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    api_key = _require_api_key()
    if api_key is None:
        return 2

    database_path = _resolve_database_path(args.db)
    if args.question is None:
        return run_interactive(database_path=database_path, api_key=api_key)

    code, _ = _ask_once(
        database_path=database_path,
        api_key=api_key,
        question=args.question,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
