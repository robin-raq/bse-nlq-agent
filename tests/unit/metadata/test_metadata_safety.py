"""Leak checks and static safety scans for the metadata sidecar."""

from __future__ import annotations

import json
import re
import sqlite3

import pytest

from bse_nlq.metadata import load_semantic_metadata, read_packaged_metadata_text

# Seed-specific literals and evaluation anchors that must not leak into the
# model-facing sidecar. Patterns are deliberately specific to avoid rejecting
# legitimate semantic vocabulary.
_FORBIDDEN_LITERAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai provider", re.compile(r"\bopenai\b", re.IGNORECASE)),
    ("groq provider", re.compile(r"\bgroq\b", re.IGNORECASE)),
    ("api key material", re.compile(r"api[_-]?key|sk-[A-Za-z0-9]{10,}", re.IGNORECASE)),
    ("anchor labels", re.compile(r"\bA(?:1[0-4]|[1-9])\b")),
    ("seed event name", re.compile(r"Harbor Kings|Lantern Parade|Ironworks New Year")),
    ("seed venue name", re.compile(r"Kings Harbor Arena|Tidewater Amphitheater")),
    ("seed order ref", re.compile(r"ORD-\d{5}")),
    ("reconciliation total", re.compile(r"\b(?:7270000|810000|6460000)\b")),
    (
        "sql repair instruction",
        re.compile(
            r"repair\s+sql|fallback\s+sql|retry\s+the\s+model",
            re.IGNORECASE,
        ),
    ),
    (
        "runtime model switch",
        re.compile(
            r"switch\s+provider|failover|model\s+selector",
            re.IGNORECASE,
        ),
    ),
    ("individual tickets table", re.compile(r'"tickets"\s*:')),
    ("customer entity table", re.compile(r'"customers?"\s*:')),
    ("fee entity table", re.compile(r'"fees"\s*:')),
    (
        "pending status value",
        re.compile(r"\bstatus[^\n]{0,40}\bpending\b", re.IGNORECASE),
    ),
    ("postponed status value", re.compile(r"\bpostponed\b", re.IGNORECASE)),
    ("failed order status", re.compile(r"\bfailed\b", re.IGNORECASE)),
    (
        "silent revenue default",
        re.compile(
            r"default\s+to\s+(?:gross|net)\s+(?:ticket\s+)?revenue",
            re.IGNORECASE,
        ),
    ),
    (
        "silent sold-out default",
        re.compile(
            r"default\s+to\s+(?:ever|currently)\s+sold\s+out",
            re.IGNORECASE,
        ),
    ),
)


def test_packaged_metadata_has_no_forbidden_leaks() -> None:
    text = read_packaged_metadata_text()
    for label, pattern in _FORBIDDEN_LITERAL_PATTERNS:
        match = pattern.search(text)
        assert match is None, f"forbidden leak ({label}): {match.group(0)!r}"


def test_face_value_never_described_as_revenue_input(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    face = metadata.column("ticket_tiers", "face_value_cents")
    assert "never_revenue" in face.roles
    assert "revenue_input" not in face.roles
    for metric in metadata.metrics.values():
        assert "face_value" not in metric.expression


def test_no_silent_default_instructions(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    for policy in metadata.clarifications.values():
        assert policy.silent_default_forbidden is True
    unsupported = metadata.unsupported
    assert all(policy.invent_default_forbidden for policy in unsupported.values())


def test_no_seed_anchor_answers_in_structured_fields(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    blob = json.dumps(
        {
            "metrics": {
                key.value: {
                    "description": metric.description,
                    "expression": metric.expression,
                    "notes": list(metric.notes),
                }
                for key, metric in metadata.metrics.items()
            },
            "tables": {
                name: {
                    "description": table.description,
                    "notes": list(table.notes),
                    "columns": {
                        col.name: {
                            "description": col.description,
                            "notes": list(col.notes),
                        }
                        for col in table.columns.values()
                    },
                }
                for name, table in metadata.tables.items()
            },
        }
    )
    assert "1,700,000" not in blob
    assert "1700000" not in blob
    assert "E11" not in blob
    assert "A13" not in blob


def test_metadata_does_not_invent_customer_or_fee_tables(
    seeded_connection: sqlite3.Connection,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    assert "customers" not in metadata.tables
    assert "fees" not in metadata.tables
    assert "tickets" not in metadata.tables


@pytest.mark.parametrize(
    "needle",
    ["pending", "postponed", "failed"],
)
def test_status_domains_exclude_rejected_values(
    seeded_connection: sqlite3.Connection,
    needle: str,
) -> None:
    metadata = load_semantic_metadata(seeded_connection)
    event_status = metadata.column("events", "status").description.lower()
    order_status = metadata.column("orders", "status").description.lower()
    assert needle not in event_status
    assert needle not in order_status
