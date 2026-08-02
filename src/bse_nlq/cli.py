"""``bse-nlq`` CLI: a thin wrapper around QueryService.

    bse-nlq ask "Which events generated the most revenue?"

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
        "ask", help="Ask a plain-English question about the ticketing data."
    )
    ask.add_argument("question")
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

    if result.generated_sql is not None:
        label = (
            "Executed SQL"
            if result.executed_sql is not None
            else "Generated SQL — not executed"
        )
        lines.append("")
        lines.append(f"{label}:")
        lines.append(result.generated_sql)
    return "\n".join(lines)


def _resolve_database_path(cli_value: Path | None) -> Path:
    if cli_value is not None:
        return cli_value
    env_value = os.environ.get("BSE_NLQ_DB", "").strip()
    return Path(env_value) if env_value else _DEFAULT_DB_PATH


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print(
            "OPENAI_API_KEY is not set. See README.md for setup.",
            file=sys.stderr,
        )
        return 2

    database_path = _resolve_database_path(args.db)
    try:
        with open_readonly_database(database_path) as database:
            generator = OpenAIRawGenerator(api_key=api_key)
            result = answer_question(database, generator, args.question)
    except DatabaseRuntimeError as error:
        print(f"Could not open database: {error}", file=sys.stderr)
        return 2

    print(render_cli_output(result))
    return 0 if result.terminal_state in _SUCCESS_STATES else 1


if __name__ == "__main__":
    raise SystemExit(main())
