"""Physical schema rendering from SQLite introspection."""

from __future__ import annotations

from bse_nlq.metadata.models import APPLICATION_TABLES
from bse_nlq.prompt.schema_render import render_physical_schema


def test_renders_six_application_tables_in_frozen_order(connection) -> None:
    text = render_physical_schema(connection)
    positions = [text.index(f"### {table}") for table in APPLICATION_TABLES]
    assert positions == sorted(positions)
    for table in APPLICATION_TABLES:
        assert text.count(f"### {table}") == 1


def test_includes_generated_columns_and_foreign_keys(connection) -> None:
    text = render_physical_schema(connection)
    assert "event_date" in text
    assert "GENERATED STORED" in text
    assert "line_gross_cents" in text
    assert "events.venue_id -> venues.venue_id" in text
    assert "ticket_tiers.event_id -> events.event_id" in text
    assert "order_items.order_id -> orders.order_id" in text
    assert "order_items.tier_id -> ticket_tiers.tier_id" in text
    assert "refunds.order_item_id -> order_items.order_item_id" in text


def test_excludes_sqlite_internal_tables_and_order_ref(connection) -> None:
    text = render_physical_schema(connection)
    assert "sqlite_master" not in text
    assert "sqlite_sequence" not in text
    assert "order_ref" not in text


def test_does_not_include_seed_rows_or_create_table(seeded_connection) -> None:
    text = render_physical_schema(seeded_connection)
    assert "CREATE TABLE" not in text
    assert "Barclays" not in text
    assert "ORD-" not in text


def test_column_order_is_deterministic_across_connections() -> None:
    import sqlite3

    from bse_nlq.db.schema import apply_schema

    texts: list[str] = []
    for _ in range(3):
        conn = sqlite3.connect(":memory:")
        apply_schema(conn)
        texts.append(render_physical_schema(conn))
        conn.close()
    assert texts[0] == texts[1] == texts[2]
