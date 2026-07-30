"""Shared helpers for ModelDecision unit tests (not a pytest plugin)."""

from __future__ import annotations

import json


def decision_json(
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
        },
        ensure_ascii=False,
    )
