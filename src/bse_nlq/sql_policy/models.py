"""Immutable validated SQL model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidatedSql:
    """SQL that passed the current static policy checks.

    ``original_sql`` is the caller input after outer whitespace trimming only.
    Later execution must run ``original_sql``, never ``normalized_sql``.
    ``normalized_sql`` is a deterministic SQLGlot SQLite rendering used only for
    fingerprinting and comparison. Referenced-object collections may be empty
    until later slices extract them.
    """

    original_sql: str
    normalized_sql: str
    fingerprint: str
    referenced_tables: frozenset[str]
    referenced_columns: frozenset[tuple[str, str]]
    referenced_functions: frozenset[str]
