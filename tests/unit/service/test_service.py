"""Mocked end-to-end QueryService: question -> terminal result.

Uses a fake ``RawModelGenerator`` against the real seeded database and the
real SQL policy / execution boundary, so only the model call is mocked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bse_nlq.db import execution as execution_module
from bse_nlq.db.build import build_database
from bse_nlq.db.runtime import ReadOnlyDatabase, open_readonly_database
from bse_nlq.generator import ProviderUnavailableError
from bse_nlq.prompt.models import BuiltPrompt
from bse_nlq.service import QueryResult, TerminalState, answer_question


class _FakeGenerator:
    """Returns one canned response (or raises) and counts calls."""

    def __init__(
        self, response: str | None = None, *, error: Exception | None = None
    ) -> None:
        self._response = response
        self._error = error
        self.call_count = 0

    def complete(self, prompt: BuiltPrompt) -> str:
        self.call_count += 1
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _decision_json(
    *,
    status: str,
    sql: str | None = None,
    clarification: str | None = None,
    explanation: str | None = None,
) -> str:
    return json.dumps(
        {
            "status": status,
            "sql": sql,
            "clarification": clarification,
            "explanation": explanation,
        }
    )


@pytest.fixture
def seeded_database(tmp_path: Path) -> ReadOnlyDatabase:
    destination = tmp_path / "app.db"
    build_database(destination)
    with open_readonly_database(destination) as database:
        yield database


def test_successful_scalar_answer(seeded_database: ReadOnlyDatabase) -> None:
    generator = _FakeGenerator(
        _decision_json(
            status="sql_generated", sql="SELECT COUNT(*) AS total FROM events"
        )
    )

    result = answer_question(seeded_database, generator, "How many events are there?")

    assert result.terminal_state is TerminalState.ANSWERED
    assert result.answer == "14"
    assert result.generated_sql == "SELECT COUNT(*) AS total FROM events"
    assert result.executed_sql == result.generated_sql
    assert generator.call_count == 1


def test_successful_currency_scalar_answer(seeded_database: ReadOnlyDatabase) -> None:
    sql = "SELECT SUM(oi.line_gross_cents) AS gross_revenue_cents FROM order_items oi"
    generator = _FakeGenerator(_decision_json(status="sql_generated", sql=sql))

    result = answer_question(seeded_database, generator, "What is total gross revenue?")

    assert result.terminal_state is TerminalState.ANSWERED
    assert result.answer is not None
    assert result.answer.startswith("$")


def test_successful_ranked_multi_row_answer(seeded_database: ReadOnlyDatabase) -> None:
    sql = "SELECT e.name AS event_name FROM events e ORDER BY e.event_id LIMIT 3"
    generator = _FakeGenerator(_decision_json(status="sql_generated", sql=sql))

    result = answer_question(seeded_database, generator, "List the first three events.")

    assert result.terminal_state is TerminalState.ANSWERED
    assert result.answer is not None
    assert len(result.answer.splitlines()) == 4  # header + 3 rows


def test_empty_result(seeded_database: ReadOnlyDatabase) -> None:
    sql = "SELECT e.event_id FROM events e WHERE e.event_id = -1"
    generator = _FakeGenerator(_decision_json(status="sql_generated", sql=sql))

    result = answer_question(seeded_database, generator, "Find event -1.")

    assert result.terminal_state is TerminalState.ANSWERED_EMPTY
    assert result.answer == "No results found."


def test_clarification_required(seeded_database: ReadOnlyDatabase) -> None:
    generator = _FakeGenerator(
        _decision_json(
            status="clarification_required",
            clarification="Do you mean gross or net revenue?",
        )
    )

    result = answer_question(seeded_database, generator, "How much revenue?")

    assert result.terminal_state is TerminalState.CLARIFICATION_REQUIRED
    assert result.message == "Do you mean gross or net revenue?"
    assert result.generated_sql is None


def test_unsupported_question(seeded_database: ReadOnlyDatabase) -> None:
    generator = _FakeGenerator(
        _decision_json(
            status="unsupported",
            explanation="This requires a current-time comparison as_of cannot answer.",
        )
    )

    result = answer_question(seeded_database, generator, "Has tonight's show started?")

    assert result.terminal_state is TerminalState.UNSUPPORTED
    assert result.message is not None
    assert result.generated_sql is None


def test_malformed_model_output(seeded_database: ReadOnlyDatabase) -> None:
    generator = _FakeGenerator("not valid json at all")

    result = answer_question(seeded_database, generator, "Anything.")

    assert result.terminal_state is TerminalState.INVALID_MODEL_OUTPUT
    assert result.generated_sql is None


def test_rejected_sql(seeded_database: ReadOnlyDatabase) -> None:
    generator = _FakeGenerator(
        _decision_json(status="sql_generated", sql="SELECT order_ref FROM orders")
    )

    result = answer_question(seeded_database, generator, "Show me order references.")

    assert result.terminal_state is TerminalState.QUERY_REJECTED
    assert result.generated_sql == "SELECT order_ref FROM orders"
    assert result.executed_sql is None


def test_unqualified_excluded_having_column_is_query_rejected(
    seeded_database: ReadOnlyDatabase,
) -> None:
    """Regression: unqualified HAVING exclusions fail closed at validation."""
    sql = "SELECT COUNT(*) FROM orders HAVING order_ref = 'secret'"
    generator = _FakeGenerator(_decision_json(status="sql_generated", sql=sql))

    result = answer_question(seeded_database, generator, "Count secret order refs.")

    assert result.terminal_state is TerminalState.QUERY_REJECTED
    assert result.generated_sql == sql
    assert result.executed_sql is None


def test_invalid_sql_parse_failure(seeded_database: ReadOnlyDatabase) -> None:
    generator = _FakeGenerator(
        _decision_json(status="sql_generated", sql="SELECT FROM WHERE !!!")
    )

    result = answer_question(seeded_database, generator, "Garbage.")

    assert result.terminal_state is TerminalState.INVALID_SQL
    assert result.executed_sql is None


def test_execution_limit_exceeded(
    monkeypatch: pytest.MonkeyPatch, seeded_database: ReadOnlyDatabase
) -> None:
    monkeypatch.setattr(execution_module, "_MAX_ROWS", 0)
    generator = _FakeGenerator(
        _decision_json(status="sql_generated", sql="SELECT event_id FROM events")
    )

    result = answer_question(seeded_database, generator, "List all event ids.")

    assert result.terminal_state is TerminalState.EXECUTION_LIMIT_EXCEEDED
    assert result.generated_sql is not None
    assert result.executed_sql == result.generated_sql


def test_unexpected_authorizer_denial_preserves_sql(
    monkeypatch: pytest.MonkeyPatch, seeded_database: ReadOnlyDatabase
) -> None:
    """Post-validation authorizer denial stays INTERNAL_ERROR but keeps SQL."""
    import bse_nlq.service as service_module
    from bse_nlq.db.errors import ExecutionErrorReason, SqlExecutionError

    sql = "SELECT COUNT(*) AS total FROM events"

    def _deny(_database: ReadOnlyDatabase, validated: object) -> object:
        raise SqlExecutionError(
            "denied",
            reason=ExecutionErrorReason.AUTHORIZATION_DENIED,
        )

    monkeypatch.setattr(service_module, "execute_validated_sql", _deny)
    generator = _FakeGenerator(_decision_json(status="sql_generated", sql=sql))

    result = answer_question(seeded_database, generator, "How many events?")

    assert result.terminal_state is TerminalState.INTERNAL_ERROR
    assert result.generated_sql == sql
    assert result.executed_sql == sql


def test_provider_unavailable(seeded_database: ReadOnlyDatabase) -> None:
    generator = _FakeGenerator(error=ProviderUnavailableError("transport failed"))

    result = answer_question(seeded_database, generator, "Anything.")

    assert result.terminal_state is TerminalState.PROVIDER_UNAVAILABLE
    assert generator.call_count == 1


def test_unexpected_generator_failure_maps_to_internal_error(
    seeded_database: ReadOnlyDatabase,
) -> None:
    generator = _FakeGenerator(error=RuntimeError("programming defect"))

    result = answer_question(seeded_database, generator, "Anything.")

    assert result.terminal_state is TerminalState.INTERNAL_ERROR


def test_exactly_one_generation_on_success(seeded_database: ReadOnlyDatabase) -> None:
    generator = _FakeGenerator(
        _decision_json(
            status="sql_generated", sql="SELECT COUNT(*) AS total FROM events"
        )
    )

    answer_question(seeded_database, generator, "How many events?")

    assert generator.call_count == 1


def test_query_result_is_immutable(seeded_database: ReadOnlyDatabase) -> None:
    generator = _FakeGenerator(
        _decision_json(
            status="sql_generated", sql="SELECT COUNT(*) AS total FROM events"
        )
    )

    result = answer_question(seeded_database, generator, "How many events?")

    assert isinstance(result, QueryResult)
    with pytest.raises(AttributeError):
        result.answer = "tampered"  # type: ignore[misc]
