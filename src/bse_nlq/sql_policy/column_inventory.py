"""Canonical physical and prompt-visible column inventories for SQL policy.

Slice 4A validates and canonicalizes caller-supplied column inventories against
``physical_tables``. It does not bind SQL columns, authorize references, or
populate ``referenced_columns``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from bse_nlq.sql_policy.scope_policy import (
    build_physical_table_lookup,
    fold_sqlite_identifier,
)


@dataclass(frozen=True, slots=True)
class CanonicalColumnInventory:
    """Immutable canonical column inventories for later binding slices.

    ``physical_by_identity`` maps ``(fold(table), fold(column))`` to the
    canonical ``(table, column)`` spelling from the inventories.
    ``visible_identities`` holds the folded identities that are prompt-visible.
    Public ``ValidatedSql`` does not expose this model.
    """

    physical_by_identity: Mapping[tuple[str, str], tuple[str, str]]
    visible_identities: frozenset[tuple[str, str]]
    physical_columns: frozenset[tuple[str, str]]
    prompt_visible_columns: frozenset[tuple[str, str]]


def canonicalize_column_inventories(
    *,
    physical_tables: frozenset[str],
    physical_columns: frozenset[tuple[str, str]],
    prompt_visible_columns: frozenset[tuple[str, str]],
) -> CanonicalColumnInventory:
    """Validate and canonicalize column inventories.

    Raises ``TypeError`` for input-contract violations. Does not raise
    ``SqlRejectedError``: inventory defects are programmer/input failures.
    """
    table_lookup = build_physical_table_lookup(physical_tables)
    physical_pairs = _require_column_pairs("physical_columns", physical_columns)
    visible_pairs = _require_column_pairs(
        "prompt_visible_columns", prompt_visible_columns
    )

    physical_by_identity: dict[tuple[str, str], tuple[str, str]] = {}
    canonical_physical: set[tuple[str, str]] = set()
    for table, column in physical_pairs:
        canonical_table = _resolve_table(
            table, table_lookup=table_lookup, inventory_name="physical_columns"
        )
        identity = (
            fold_sqlite_identifier(canonical_table),
            fold_sqlite_identifier(column),
        )
        canonical_pair = (canonical_table, column)
        existing = physical_by_identity.get(identity)
        if existing is not None:
            raise TypeError(
                "physical_columns contains case-fold collisions under "
                "SQLite-compatible identifier matching"
            )
        physical_by_identity[identity] = canonical_pair
        canonical_physical.add(canonical_pair)

    visible_identities: set[tuple[str, str]] = set()
    canonical_visible: set[tuple[str, str]] = set()
    for table, column in visible_pairs:
        canonical_table = _resolve_table(
            table,
            table_lookup=table_lookup,
            inventory_name="prompt_visible_columns",
        )
        identity = (
            fold_sqlite_identifier(canonical_table),
            fold_sqlite_identifier(column),
        )
        physical_pair = physical_by_identity.get(identity)
        if physical_pair is None:
            raise TypeError(
                "prompt_visible_columns must resolve to existing "
                "physical_columns identities"
            )
        if identity in visible_identities:
            raise TypeError(
                "prompt_visible_columns contains case-fold collisions under "
                "SQLite-compatible identifier matching"
            )
        visible_identities.add(identity)
        canonical_visible.add(physical_pair)

    return CanonicalColumnInventory(
        physical_by_identity=MappingProxyType(dict(physical_by_identity)),
        visible_identities=frozenset(visible_identities),
        physical_columns=frozenset(canonical_physical),
        prompt_visible_columns=frozenset(canonical_visible),
    )


def _require_column_pairs(name: str, value: object) -> frozenset[tuple[str, str]]:
    if not isinstance(value, frozenset):
        raise TypeError(f"{name} must be frozenset[tuple[str, str]]")
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError(f"{name} must contain (table, column) str pairs")
        table, column = item
        if not isinstance(table, str) or not isinstance(column, str):
            raise TypeError(f"{name} must contain (table, column) str pairs")
        if (
            table == ""
            or column == ""
            or table.strip() != table
            or column.strip() != column
        ):
            raise TypeError(
                f"{name} entries must be nonempty and free of "
                "leading/trailing whitespace"
            )
    return value


def _resolve_table(
    table: str,
    *,
    table_lookup: dict[str, str],
    inventory_name: str,
) -> str:
    canonical = table_lookup.get(fold_sqlite_identifier(table))
    if canonical is None:
        raise TypeError(f"{inventory_name} references unknown physical table: {table}")
    return canonical
