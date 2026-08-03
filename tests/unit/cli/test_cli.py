"""``bse-nlq ask`` CLI: argument parsing, rendering, and safe-failure paths.

No test in this module makes a network call. A missing API key and a missing
database file are both caught before any provider is constructed, and the
successful-flow test monkeypatches ``OpenAIRawGenerator`` with a fake.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bse_nlq import cli
from bse_nlq.cli import EXAMPLE_QUESTIONS
from bse_nlq.db.build import build_database
from bse_nlq.prompt.models import BuiltPrompt
from bse_nlq.service import QueryResult, TerminalState


class _FakeGenerator:
    def __init__(self, *, api_key: str) -> None:
        assert api_key == "test-key"

    def complete(self, prompt: BuiltPrompt) -> str:
        return (
            '{"status": "sql_generated", '
            '"sql": "SELECT COUNT(*) AS total FROM events", '
            '"clarification": null, "explanation": null}'
        )


def test_build_arg_parser_parses_ask_question() -> None:
    args = cli.build_arg_parser().parse_args(["ask", "How many events?"])

    assert args.command == "ask"
    assert args.question == "How many events?"
    assert args.db is None


def test_build_arg_parser_allows_ask_without_question() -> None:
    args = cli.build_arg_parser().parse_args(["ask"])

    assert args.command == "ask"
    assert args.question is None


def test_build_arg_parser_accepts_db_override() -> None:
    args = cli.build_arg_parser().parse_args(["ask", "q", "--db", "/tmp/x.db"])

    assert args.db == Path("/tmp/x.db")


def test_missing_api_key_returns_error_without_network(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    code = cli.main(["ask", "How many events?"])

    assert code == 2
    err = capsys.readouterr().err
    assert "OPENAI_API_KEY" in err
    assert "evaluation/run.py" in err


def test_missing_database_returns_error_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    code = cli.main(["ask", "How many events?", "--db", str(tmp_path / "missing.db")])

    assert code == 2
    assert "database" in capsys.readouterr().err.lower()


def test_successful_ask_prints_answer_and_executed_sql(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(cli, "OpenAIRawGenerator", _FakeGenerator)
    destination = tmp_path / "app.db"
    build_database(destination)

    code = cli.main(["ask", "How many events?", "--db", str(destination)])

    out = capsys.readouterr().out
    assert code == 0
    assert "14" in out
    assert "Executed SQL:" in out
    assert "SELECT COUNT(*) AS total FROM events" in out


def test_interactive_menu_runs_selected_example(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(cli, "OpenAIRawGenerator", _FakeGenerator)
    destination = tmp_path / "app.db"
    build_database(destination)
    answers = iter(["1", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    code = cli.main(["ask", "--db", str(destination)])

    out = capsys.readouterr().out
    assert code == 0
    assert EXAMPLE_QUESTIONS[0] in out or "top 5 event categories" in out
    assert "Executed SQL:" in out


def test_interactive_custom_question_then_quit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(cli, "OpenAIRawGenerator", _FakeGenerator)
    destination = tmp_path / "app.db"
    build_database(destination)
    answers = iter(["0", "How many events?", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    code = cli.main(["ask", "--db", str(destination)])

    out = capsys.readouterr().out
    assert code == 0
    assert "How many events?" in out
    assert "14" in out


def test_prompt_menu_quits(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(["q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    assert cli._prompt_menu(cli.EXAMPLE_QUESTIONS) is None


def test_prompt_menu_selects_example(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(["2"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    assert cli._prompt_menu(cli.EXAMPLE_QUESTIONS) == EXAMPLE_QUESTIONS[1]


def test_prompt_menu_rejects_invalid_then_quits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter(["99", "", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    assert cli._prompt_menu(cli.EXAMPLE_QUESTIONS) is None
    err_or_out = capsys.readouterr().out
    assert "Enter 1-" in err_or_out


def test_prompt_menu_empty_custom_retries(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter(["0", "", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    assert cli._prompt_menu(cli.EXAMPLE_QUESTIONS) is None
    assert "Empty question" in capsys.readouterr().out


def test_render_answered_shows_executed_sql_label() -> None:
    result = QueryResult(
        terminal_state=TerminalState.ANSWERED,
        answer="14",
        generated_sql="SELECT COUNT(*) FROM events",
        executed_sql="SELECT COUNT(*) FROM events",
    )

    output = cli.render_cli_output(result)

    assert output.startswith("14")
    assert "Executed SQL:" in output
    assert "SELECT COUNT(*) FROM events" in output


def test_render_rejected_shows_not_executed_label() -> None:
    result = QueryResult(
        terminal_state=TerminalState.QUERY_REJECTED,
        generated_sql="SELECT order_ref FROM orders",
        executed_sql=None,
    )

    output = cli.render_cli_output(result)

    assert "blocked this query before execution" in output
    assert "Generated SQL — not executed:" in output
    assert "SELECT order_ref FROM orders" in output


def test_render_clarification_required() -> None:
    result = QueryResult(
        terminal_state=TerminalState.CLARIFICATION_REQUIRED,
        message="Gross or net revenue?",
    )

    output = cli.render_cli_output(result)

    assert "Clarification needed: Gross or net revenue?" == output


def test_render_unsupported() -> None:
    result = QueryResult(
        terminal_state=TerminalState.UNSUPPORTED,
        message="Requires current time.",
    )

    output = cli.render_cli_output(result)

    assert "Unsupported question: Requires current time." == output


def test_render_provider_unavailable_has_no_sql_section() -> None:
    result = QueryResult(terminal_state=TerminalState.PROVIDER_UNAVAILABLE)

    output = cli.render_cli_output(result)

    assert "provider is currently unavailable" in output
    assert "SQL" not in output


def test_render_internal_error() -> None:
    result = QueryResult(terminal_state=TerminalState.INTERNAL_ERROR)

    output = cli.render_cli_output(result)

    assert output == "An internal error occurred."
