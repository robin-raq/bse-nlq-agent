"""Immutable validated SQL model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidatedSql:
    """SQL that passed the current static policy checks.

    ``original_sql`` is the caller input after outer whitespace trimming only.
    Later execution must run ``original_sql``, never ``normalized_sql``.
    ``normalized_sql`` is a deterministic SQLGlot SQLite rendering used only for
    fingerprinting and comparison. ``referenced_tables`` holds canonical
    physical table names after Slice 3 authorization. Column and function
    collections may remain empty until later slices.
    """

    original_sql: str
    normalized_sql: str
    fingerprint: str
    referenced_tables: frozenset[str]
    referenced_columns: frozenset[tuple[str, str]]
    referenced_functions: frozenset[str]
