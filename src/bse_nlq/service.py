"""QueryService: orchestrates question -> terminal result.

question -> deterministic prompt -> one model generation -> ModelDecision
validation -> SQL validation -> controlled execution -> deterministic
rendering -> terminal result.

Terminal states are the frozen contract from
``docs/planning/architecture-workshop.local.md`` (D-007 §18), minus
``result_truncated``: this application's execution boundary (U3) hard-rejects
row/column overflow rather than truncating, so that state is unreachable by
design and intentionally omitted rather than added unused.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from bse_nlq.db.errors import ExecutionErrorReason, SqlExecutionError
from bse_nlq.db.execution import RawQueryResult, execute_validated_sql
from bse_nlq.db.runtime import ReadOnlyDatabase
from bse_nlq.decision.errors import InvalidModelOutputError
from bse_nlq.decision.models import DecisionStatus
from bse_nlq.generator import (
    ProviderUnavailableError,
    RawModelGenerator,
    decide_from_raw_generator,
)
from bse_nlq.prompt import PromptInput, build_prompt
from bse_nlq.sql_policy import InvalidSqlError, SqlRejectedError, validate_sql


class TerminalState(StrEnum):
    """Frozen application outcome categories (D-007 §18)."""

    ANSWERED = "answered"
    ANSWERED_EMPTY = "answered_empty"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    QUERY_REJECTED = "query_rejected"
    INVALID_SQL = "invalid_sql"
    EXECUTION_LIMIT_EXCEEDED = "execution_limit_exceeded"
    EXECUTION_ERROR = "execution_error"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Immutable terminal outcome of one ``answer_question`` call.

    ``generated_sql`` is populated whenever the model produced SQL, even if
    it was later rejected or failed to execute. ``executed_sql`` is populated
    only once the SQL was submitted to SQLite for execution (regardless of
    whether execution ultimately succeeded), and is always byte-for-byte
    identical to ``generated_sql`` — this application never rewrites SQL.
    ``message`` carries the clarification/explanation/error text for
    non-answered states. ``answer`` carries the rendered text for answered
    states.
    """

    terminal_state: TerminalState
    generated_sql: str | None = None
    executed_sql: str | None = None
    message: str | None = None
    answer: str | None = None
    raw_result: RawQueryResult | None = None


_EXECUTION_LIMIT_REASONS = frozenset(
    {
        ExecutionErrorReason.ROW_LIMIT_EXCEEDED,
        ExecutionErrorReason.COLUMN_LIMIT_EXCEEDED,
        ExecutionErrorReason.EXECUTION_BUDGET_EXCEEDED,
    }
)


def answer_question(
    database: ReadOnlyDatabase,
    generator: RawModelGenerator,
    question: str,
    *,
    as_of: date | None = None,
) -> QueryResult:
    """Answer one question end to end; never raises for expected failures.

    Exactly one semantic model-generation attempt is made (no retry, no
    repair loop). Unexpected exceptions are caught only at this outermost
    boundary and mapped to ``internal_error`` (D-007 §17); everything more
    specific is handled by its own typed exception below.
    """
    try:
        return _answer_question(database, generator, question, as_of=as_of)
    except Exception:
        return QueryResult(terminal_state=TerminalState.INTERNAL_ERROR)


def _answer_question(
    database: ReadOnlyDatabase,
    generator: RawModelGenerator,
    question: str,
    *,
    as_of: date | None,
) -> QueryResult:
    # Package-private connection reuse: the same open, already-reconciled
    # connection the runtime factory owns is what prompt introspection reads
    # from, so QueryService (like bse_nlq.db.execution) is a trusted internal
    # caller of this non-public accessor rather than an external consumer.
    prompt_input = PromptInput(
        question=question,
        metadata=database.metadata,
        connection=database._connection,
        as_of=as_of,
    )
    built_prompt = build_prompt(prompt_input)

    try:
        decision = decide_from_raw_generator(generator, built_prompt)
    except ProviderUnavailableError:
        return QueryResult(terminal_state=TerminalState.PROVIDER_UNAVAILABLE)
    except InvalidModelOutputError:
        return QueryResult(terminal_state=TerminalState.INVALID_MODEL_OUTPUT)

    if decision.status is DecisionStatus.CLARIFICATION_REQUIRED:
        return QueryResult(
            terminal_state=TerminalState.CLARIFICATION_REQUIRED,
            message=decision.clarification,
        )
    if decision.status is DecisionStatus.UNSUPPORTED:
        return QueryResult(
            terminal_state=TerminalState.UNSUPPORTED,
            message=decision.explanation,
        )

    generated_sql = decision.sql
    assert generated_sql is not None  # guaranteed by ModelDecision invariants

    try:
        validated = validate_sql(
            generated_sql,
            physical_tables=database.physical_tables,
            physical_columns=database.physical_columns,
            prompt_visible_columns=database.prompt_visible_columns,
        )
    except InvalidSqlError:
        return QueryResult(
            terminal_state=TerminalState.INVALID_SQL,
            generated_sql=generated_sql,
        )
    except SqlRejectedError as error:
        return QueryResult(
            terminal_state=TerminalState.QUERY_REJECTED,
            generated_sql=generated_sql,
            message=str(error),
        )

    try:
        raw_result = execute_validated_sql(database, validated)
    except SqlExecutionError as error:
        if error.reason in _EXECUTION_LIMIT_REASONS:
            state = TerminalState.EXECUTION_LIMIT_EXCEEDED
        elif error.reason is ExecutionErrorReason.AUTHORIZATION_DENIED:
            # Statically validated SQL should never be authorizer-denied; if
            # it happens, that is an internal policy inconsistency, not a
            # user-facing execution problem.
            return QueryResult(terminal_state=TerminalState.INTERNAL_ERROR)
        else:
            state = TerminalState.EXECUTION_ERROR
        return QueryResult(
            terminal_state=state,
            generated_sql=generated_sql,
            executed_sql=validated.original_sql,
        )

    terminal_state = (
        TerminalState.ANSWERED if raw_result.rows else TerminalState.ANSWERED_EMPTY
    )
    return QueryResult(
        terminal_state=terminal_state,
        generated_sql=generated_sql,
        executed_sql=validated.original_sql,
        answer=render_result(raw_result),
        raw_result=raw_result,
    )


def render_result(raw_result: RawQueryResult) -> str:
    """Deterministic text rendering for an executed result.

    Supported forms only: empty result, a single scalar (currency when the
    column name ends in the project's established ``_cents`` convention,
    otherwise a plain number or string), one aggregate row (multiple
    columns), and multiple ranked/labeled rows rendered as a small table.
    No semantic type inference or narrative generation is performed; a
    column not ending in ``_cents`` is rendered as its raw value, never a
    guessed unit.
    """
    if not raw_result.rows:
        return "No results found."
    if len(raw_result.rows) == 1:
        row = raw_result.rows[0]
        if len(row) == 1:
            return _format_value(raw_result.columns[0], row[0])
        return ", ".join(
            f"{column}: {_format_value(column, value)}"
            for column, value in zip(raw_result.columns, row, strict=True)
        )
    lines = [" | ".join(raw_result.columns)]
    for row in raw_result.rows:
        lines.append(
            " | ".join(
                _format_value(column, value)
                for column, value in zip(raw_result.columns, row, strict=True)
            )
        )
    return "\n".join(lines)


def _format_value(column: str, value: object) -> str:
    if value is None:
        return "NULL"
    if column.endswith("_cents") and isinstance(value, int):
        return f"${value / 100:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


__all__ = [
    "QueryResult",
    "TerminalState",
    "answer_question",
    "render_result",
]
