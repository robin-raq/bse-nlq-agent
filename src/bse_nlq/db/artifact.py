"""Read-only validation and logical fingerprinting for built SQLite artifacts.

This module is not a query service. It exists so the persistent builder can
fail closed before atomically publishing a database file.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from types import MappingProxyType

from bse_nlq.db.errors import DatabaseBuildError
from bse_nlq.db.seed_data import EXPECTED_ROW_COUNTS, TOTAL_SEED_ROWS

APPLICATION_TABLES: tuple[str, ...] = (
    "venues",
    "events",
    "ticket_tiers",
    "orders",
    "order_items",
    "refunds",
)

APPROVED_INDEXES: MappingProxyType[str, str] = MappingProxyType(
    {
        "idx_events_event_date": "events",
        "idx_events_venue_id": "events",
        "idx_events_category": "events",
        "idx_events_status": "events",
        "idx_ticket_tiers_event_id": "ticket_tiers",
        "idx_order_items_tier_id": "order_items",
        "idx_order_items_order_id": "order_items",
        "idx_orders_purchased_at": "orders",
        "idx_orders_status": "orders",
        "idx_refunds_order_item_id": "refunds",
    }
)

_PRIMARY_KEY_COLUMNS: MappingProxyType[str, str] = MappingProxyType(
    {
        "venues": "venue_id",
        "events": "event_id",
        "ticket_tiers": "tier_id",
        "orders": "order_id",
        "order_items": "order_item_id",
        "refunds": "refund_id",
    }
)

_HIDDEN_GENERATED_STORED = 3

_GROSS_BASE = """
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
"""

_COMPLETED_REFUNDED = """
SELECT COALESCE(SUM(r.refund_amount_cents), 0)
FROM refunds r
JOIN order_items oi ON oi.order_item_id = r.order_item_id
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
"""

_INVARIANT_QUERIES: tuple[tuple[str, str], ...] = (
    (
        "I-1",
        """
SELECT oi.order_item_id
FROM order_items oi
LEFT JOIN (
    SELECT order_item_id, SUM(refund_amount_cents) AS refunded_cents
    FROM refunds
    GROUP BY order_item_id
) r ON r.order_item_id = oi.order_item_id
WHERE COALESCE(r.refunded_cents, 0) > oi.line_gross_cents
""",
    ),
    (
        "I-2",
        """
SELECT oi.order_item_id
FROM order_items oi
LEFT JOIN (
    SELECT order_item_id, SUM(refunded_qty) AS refunded_qty
    FROM refunds
    GROUP BY order_item_id
) r ON r.order_item_id = oi.order_item_id
WHERE COALESCE(r.refunded_qty, 0) > oi.quantity
""",
    ),
    (
        "I-3",
        """
SELECT e.event_id
FROM events e
JOIN venues v ON v.venue_id = e.venue_id
WHERE e.capacity > v.capacity
""",
    ),
    (
        "I-4",
        """
SELECT DISTINCT o.order_id, e.event_id
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
JOIN events e ON e.event_id = tt.event_id
WHERE o.purchased_at >= e.start_local
""",
    ),
    (
        "I-5",
        """
SELECT r.refund_id
FROM refunds r
JOIN order_items oi ON oi.order_item_id = r.order_item_id
JOIN orders o ON o.order_id = oi.order_id
WHERE r.refunded_at <= o.purchased_at
""",
    ),
    (
        "I-6",
        """
SELECT oi.order_item_id
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
JOIN events e ON e.event_id = tt.event_id AND e.status = 'cancelled'
LEFT JOIN (
    SELECT order_item_id,
           SUM(refunded_qty) AS refunded_qty,
           SUM(refund_amount_cents) AS refunded_cents
    FROM refunds
    GROUP BY order_item_id
) r ON r.order_item_id = oi.order_item_id
WHERE COALESCE(r.refunded_qty, 0) != oi.quantity
   OR COALESCE(r.refunded_cents, 0) != oi.line_gross_cents
""",
    ),
    (
        "I-7",
        """
SELECT oi.order_id
FROM order_items oi
JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
GROUP BY oi.order_id
HAVING COUNT(DISTINCT tt.event_id) != 1
""",
    ),
    (
        "I-8",
        """
SELECT e.event_id
FROM events e
LEFT JOIN (
    SELECT tt.event_id, SUM(oi.quantity) AS tickets_sold
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
    GROUP BY tt.event_id
) s ON s.event_id = e.event_id
WHERE COALESCE(s.tickets_sold, 0) > e.capacity
""",
    ),
)

_A13 = """
SELECT e.name AS event_name
FROM events e
JOIN (
    SELECT tt.event_id, SUM(oi.quantity) AS tickets_sold
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
    GROUP BY tt.event_id
) s ON s.event_id = e.event_id
WHERE s.tickets_sold >= e.capacity
ORDER BY e.event_id
"""

_A14 = """
WITH line_refunds AS (
    SELECT r.order_item_id, SUM(r.refunded_qty) AS refunded_qty
    FROM refunds r
    JOIN order_items oi ON oi.order_item_id = r.order_item_id
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    GROUP BY r.order_item_id
),
sold AS (
    SELECT tt.event_id,
           SUM(oi.quantity) AS tickets_sold,
           COALESCE(SUM(lr.refunded_qty), 0) AS refunded_qty
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    JOIN ticket_tiers tt ON tt.tier_id = oi.tier_id
    LEFT JOIN line_refunds lr ON lr.order_item_id = oi.order_item_id
    GROUP BY tt.event_id
)
SELECT e.name AS event_name
FROM events e
JOIN sold s ON s.event_id = e.event_id
WHERE (s.tickets_sold - s.refunded_qty) >= e.capacity
ORDER BY e.event_id
"""


def validate_built_database(
    connection: sqlite3.Connection,
) -> MappingProxyType[str, int]:
    """Validate a fully built temporary database before publication.

    Raises ``DatabaseBuildError`` when any structural, integrity, invariant, or
    reconciliation check fails. Returns immutable exact row counts on success.
    """
    if connection.in_transaction:
        raise DatabaseBuildError("built database must not remain in a transaction")

    fk = connection.execute("PRAGMA foreign_keys").fetchone()
    if fk is None or fk[0] != 1:
        raise DatabaseBuildError(
            "PRAGMA foreign_keys must be enabled during validation"
        )

    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise DatabaseBuildError("PRAGMA foreign_key_check reported violations")

    integrity = connection.execute("PRAGMA integrity_check").fetchone()
    if integrity is None or integrity[0] != "ok":
        raise DatabaseBuildError("PRAGMA integrity_check did not return ok")

    tables = _object_names(connection, "table")
    if tables != set(APPLICATION_TABLES):
        raise DatabaseBuildError(
            f"application table inventory mismatch: {sorted(tables)}"
        )

    if _object_names(connection, "view"):
        raise DatabaseBuildError("application views are not permitted")
    if _object_names(connection, "trigger"):
        raise DatabaseBuildError("triggers are not permitted")

    indexes = _object_names(connection, "index")
    if indexes != set(APPROVED_INDEXES):
        raise DatabaseBuildError(
            f"approved index inventory mismatch: {sorted(indexes)}"
        )
    for index_name, table in APPROVED_INDEXES.items():
        row = connection.execute(
            "SELECT tbl_name FROM sqlite_master WHERE type = 'index' AND name = ?",
            (index_name,),
        ).fetchone()
        if row is None or row[0] != table:
            raise DatabaseBuildError(f"index {index_name} is not bound to {table}")

    _require_generated_column(connection, "events", "event_date")
    _require_generated_column(connection, "order_items", "line_gross_cents")

    counts: dict[str, int] = {}
    for table in APPLICATION_TABLES:
        count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        assert count is not None
        counts[table] = int(count[0])
    if counts != dict(EXPECTED_ROW_COUNTS):
        raise DatabaseBuildError(f"row counts mismatch: {counts}")
    if sum(counts.values()) != TOTAL_SEED_ROWS:
        raise DatabaseBuildError("total seed row count is not 109")

    for label, sql in _INVARIANT_QUERIES:
        if connection.execute(sql).fetchall():
            raise DatabaseBuildError(f"invariant {label} reported violations")

    gross = connection.execute(
        f"SELECT SUM(oi.line_gross_cents) {_GROSS_BASE}"
    ).fetchone()
    refunded = connection.execute(_COMPLETED_REFUNDED).fetchone()
    tickets = connection.execute(f"SELECT SUM(oi.quantity) {_GROSS_BASE}").fetchone()
    assert gross is not None and refunded is not None and tickets is not None
    if gross[0] != 7_270_000:
        raise DatabaseBuildError("gross ticket revenue mismatch")
    if refunded[0] != 810_000:
        raise DatabaseBuildError("refunded ticket revenue mismatch")
    if gross[0] - refunded[0] != 6_460_000:
        raise DatabaseBuildError("net ticket revenue mismatch")
    if tickets[0] != 957:
        raise DatabaseBuildError("tickets sold mismatch")

    a13 = connection.execute(_A13).fetchall()
    if a13 != [("Harbor Kings Preview Showcase",)]:
        raise DatabaseBuildError("A13 artifact check failed")
    if connection.execute(_A14).fetchall():
        raise DatabaseBuildError("A14 artifact check failed")

    return MappingProxyType(dict(counts))


def compute_logical_content_fingerprint(connection: sqlite3.Connection) -> str:
    """Return a SHA-256 digest of canonical schema SQL and row content.

    The fingerprint excludes filesystem paths, timestamps, connection identity,
    and other machine-local metadata. It is the cross-environment reproducibility
    contract; SQLite file bytes are not claimed to be portable.
    """
    payload = {
        "schema_objects": _canonical_schema_objects(connection),
        "tables": _canonical_table_payload(connection),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _object_names(connection: sqlite3.Connection, kind: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
        (kind,),
    )
    return {row[0] for row in rows}


def _require_generated_column(
    connection: sqlite3.Connection, table: str, column: str
) -> None:
    columns = {
        row[1]: row[6] for row in connection.execute(f"PRAGMA table_xinfo({table})")
    }
    if columns.get(column) != _HIDDEN_GENERATED_STORED:
        raise DatabaseBuildError(f"{table}.{column} must be a STORED generated column")


def _canonical_schema_objects(connection: sqlite3.Connection) -> list[dict[str, str]]:
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    objects: list[dict[str, str]] = []
    for type_, name, tbl_name, sql in rows:
        objects.append(
            {
                "type": type_,
                "name": name,
                "tbl_name": tbl_name,
                "sql": "" if sql is None else " ".join(sql.split()),
            }
        )
    return objects


def _canonical_table_payload(
    connection: sqlite3.Connection,
) -> dict[str, dict[str, object]]:
    payload: dict[str, dict[str, object]] = {}
    for table in APPLICATION_TABLES:
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        pk = _PRIMARY_KEY_COLUMNS[table]
        quoted_columns = ", ".join(columns)
        rows = connection.execute(
            f"SELECT {quoted_columns} FROM {table} ORDER BY {pk}"
        ).fetchall()
        payload[table] = {
            "columns": columns,
            "rows": [list(row) for row in rows],
        }
    return payload
