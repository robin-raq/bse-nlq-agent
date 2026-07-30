"""Render physical schema facts from SQLite introspection."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from bse_nlq.metadata.models import APPLICATION_TABLES
from bse_nlq.metadata.reconcile import PROMPT_EXCLUDED_COLUMNS

_APP_TABLE_FILTER = (
    "SELECT name FROM sqlite_master "
    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
    "ORDER BY name"
)


@dataclass(frozen=True, slots=True)
class _ColumnInfo:
    cid: int
    name: str
    type: str
    notnull: int
    pk: int
    hidden: int


def render_physical_schema(connection: sqlite3.Connection) -> str:
    """Render application tables, columns, generated columns, and FKs.

    Ordering is deterministic and independent of incidental SQLite row order.
    Prompt-excluded columns (currently ``orders.order_ref``) are omitted from
    the model-facing structural section.
    """
    tables = _application_tables(connection)
    lines: list[str] = ["## Physical schema", ""]
    for table in APPLICATION_TABLES:
        if table not in tables:
            continue
        lines.append(f"### {table}")
        for column in _ordered_columns(connection, table):
            if (table, column.name) in PROMPT_EXCLUDED_COLUMNS:
                continue
            lines.append(_format_column(column))
        lines.append("")

    lines.append("### Primary keys")
    for table in APPLICATION_TABLES:
        if table not in tables:
            continue
        pk_cols = [
            column.name
            for column in _ordered_columns(connection, table)
            if column.pk > 0 and (table, column.name) not in PROMPT_EXCLUDED_COLUMNS
        ]
        if pk_cols:
            lines.append(f"- {table}: {', '.join(pk_cols)}")
    lines.append("")

    lines.append("### Foreign keys")
    for edge in _ordered_foreign_keys(connection):
        lines.append(f"- {edge[0]}.{edge[1]} -> {edge[2]}.{edge[3]}")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _application_tables(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute(_APP_TABLE_FILTER)}


def _ordered_columns(connection: sqlite3.Connection, table: str) -> list[_ColumnInfo]:
    rows = connection.execute(f"PRAGMA table_xinfo({table})").fetchall()
    # cid order is the physical declaration order; sort explicitly by cid.
    ordered = sorted(rows, key=lambda row: int(row[0]))
    return [
        _ColumnInfo(
            cid=int(row[0]),
            name=str(row[1]),
            type=str(row[2]),
            notnull=int(row[3]),
            pk=int(row[5]),
            hidden=int(row[6]),
        )
        for row in ordered
    ]


def _format_column(column: _ColumnInfo) -> str:
    parts: list[str] = [f"- {column.name}: {column.type or 'ANY'}"]
    flags: list[str] = []
    if column.pk > 0:
        flags.append("PRIMARY KEY")
    if column.notnull == 1 and column.pk == 0:
        flags.append("NOT NULL")
    # hidden == 3 => GENERATED ALWAYS AS ... STORED
    if column.hidden == 3:
        flags.append("GENERATED STORED")
    if flags:
        parts.append(f" ({', '.join(flags)})")
    return "".join(parts)


def _ordered_foreign_keys(
    connection: sqlite3.Connection,
) -> Sequence[tuple[str, str, str, str]]:
    edges: list[tuple[str, str, str, str]] = []
    for table in APPLICATION_TABLES:
        rows = connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        # Sort by FK id then seq for stable multi-column keys.
        for row in sorted(rows, key=lambda item: (int(item[0]), int(item[1]))):
            edges.append((table, str(row[3]), str(row[2]), str(row[4])))
    return tuple(sorted(edges, key=lambda edge: (edge[0], edge[1], edge[2], edge[3])))
